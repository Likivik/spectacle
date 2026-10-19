"""Tests for the missed-webhook catch-up pass (restart window).

Background: Nextcloud dispatches a webhook on NodeCreated/NodeWritten. If
the service is mid-restart the dispatch dies with it and *nothing* records
the file — no index row exists, so neither ``reconcile_orphans`` (rows that
exist) nor ``reconcile_stale_files`` (rows that vanished) can see it.

``catch_up_missed_files()`` PROPFINDs ``getlastmod`` and enqueues only the
entries modified after the last webhook we received. These tests pin:

  * the watermark semantics (no watermark → no scan at all, because a
    fresh install must never mass-scan);
  * mtime filtering (older files are not re-enqueued);
  * the same done/in-flight guards the webhook uses;
  * the cap keeping the *newest* entries;
  * a failed PROPFIND leaving the watermark untouched.

Everything is mocked — no Nextcloud, no tesseract.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Point jobstore at a writable directory BEFORE webhook_server is imported
# (its module body calls jobstore.init()).
os.environ.setdefault("NC_OCR_STATE_DIR", tempfile.mkdtemp(prefix="ncocr-catchup-"))
_STATE_DIR = os.environ["NC_OCR_STATE_DIR"]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

import nc_ocr_flow.webhook_server as ws  # noqa: E402

SECRET = "test-secret"
#: Fixed "now" so mtime arithmetic is exact.
NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _repin_state_dir(monkeypatch):
    """Fresh DB per test: the watermark is durable state."""
    os.environ["NC_OCR_STATE_DIR"] = _STATE_DIR
    monkeypatch.setattr(ws, "WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(ws, "NC_PASSWORD", "test-pass")
    ws.jobstore._reset_for_tests()
    yield
    ws.jobstore._reset_for_tests()


def _xml(entries: list[tuple[str, str | None]]) -> str:
    """Build a DAV multistatus with the given (path, getlastmod) pairs."""
    parts = ['<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">']
    for path, lastmod in entries:
        parts.append(
            "<d:response>"
            f"<d:href>/remote.php/dav/files/likivik/{path}</d:href>"
            "<d:propstat><d:prop>"
            "<d:resourcetype/><d:getcontenttype>application/pdf</d:getcontenttype>"
            + (f"<d:getlastmod>{lastmod}</d:getlastmod>" if lastmod else "")
            + "</d:prop></d:propstat></d:response>"
        )
    parts.append("</d:multistatus>")
    return "".join(parts)


def _http_date(epoch: float) -> str:
    from email.utils import formatdate

    return formatdate(epoch, usegmt=True)


class _Resp:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ws.requests.HTTPError(f"{self.status_code}")


def _stub_propfind(monkeypatch, xml: str) -> list:
    calls: list = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return _Resp(xml)

    monkeypatch.setattr(ws.requests, "request", fake_request)
    return calls


def _watermark() -> float | None:
    return ws._catchup_watermark()


# --- watermark semantics ---------------------------------------------------


def test_no_watermark_never_scans(monkeypatch):
    """A fresh install has no watermark; a mass scan there would be a
    surprise re-OCR of the entire library."""
    calls = _stub_propfind(monkeypatch, _xml([("a.pdf", _http_date(NOW))]))

    out = ws.catch_up_missed_files(now=NOW)

    assert out["reason"] == "no_watermark"
    assert out["enqueued"] == 0
    assert calls == [], "PROPFIND must not happen without a watermark"


def test_enqueueing_webhook_advances_watermark():
    ws.jobstore._reset_for_tests()
    ws._mark_webhook_received(NOW)
    assert _watermark() == pytest.approx(NOW)


def test_disabled_by_env(monkeypatch):
    _stub_propfind(monkeypatch, _xml([]))
    ws._mark_webhook_received(NOW - 60)
    monkeypatch.setattr(ws, "_CATCHUP_ENABLED", False)

    out = ws.catch_up_missed_files(now=NOW)
    assert out["reason"] == "disabled"


# --- the actual catch-up ---------------------------------------------------


def test_enqueues_only_files_newer_than_watermark(monkeypatch):
    ws._mark_webhook_received(NOW - 600)
    _stub_propfind(monkeypatch, _xml([
        ("Work/old.pdf", _http_date(NOW - 7200)),   # before watermark
        ("Work/new.pdf", _http_date(NOW - 120)),    # after watermark
        ("Work/notes.txt", _http_date(NOW - 60)),   # unprocessable ext
    ]))

    with patch.object(ws, "_enqueue", return_value={"id": 1}) as enq:
        out = ws.catch_up_missed_files(now=NOW)

    assert out["enqueued"] == 1, out
    assert [c.args[0] for c in enq.call_args_list] == ["/likivik/files/Work/new.pdf"]
    # Watermark advanced to "now" only after a successful pass.
    assert _watermark() == pytest.approx(NOW)


def test_missing_lastmod_is_not_enqueued(monkeypatch):
    """A server that omits getlastmod gives us no proof the file is new."""
    ws._mark_webhook_received(NOW - 600)
    _stub_propfind(monkeypatch, _xml([("Work/no-mtime.pdf", None)]))

    with patch.object(ws, "_enqueue", return_value={"id": 1}) as enq:
        out = ws.catch_up_missed_files(now=NOW)

    assert out["enqueued"] == 0
    enq.assert_not_called()


def test_skips_already_done_and_in_flight(monkeypatch):
    ws._mark_webhook_received(NOW - 600)
    _stub_propfind(monkeypatch, _xml([
        ("Work/done.pdf", _http_date(NOW - 100)),
        ("Work/running.pdf", _http_date(NOW - 200)),
        ("Work/fresh.pdf", _http_date(NOW - 300)),
    ]))
    ws.jobstore.file_put({"path": "/likivik/files/Work/done.pdf", "status": "done"})
    ws.jobstore.file_put({"path": "/likivik/files/Work/running.pdf", "status": "queued"})
    monkeypatch.setattr(
        ws, "_path_in_flight",
        lambda p: p.endswith("/running.pdf"),
    )

    with patch.object(ws, "_enqueue", return_value={"id": 1}) as enq:
        out = ws.catch_up_missed_files(now=NOW)

    assert out["skipped_ocrd"] == 1
    assert out["skipped_in_flight"] == 1
    assert [c.args[0] for c in enq.call_args_list] == ["/likivik/files/Work/fresh.pdf"]


def test_cap_keeps_newest_first(monkeypatch):
    ws._mark_webhook_received(NOW - 600)
    _stub_propfind(monkeypatch, _xml([
        (f"Work/f{i}.pdf", _http_date(NOW - i * 10)) for i in range(1, 6)
    ]))
    monkeypatch.setattr(ws, "_CATCHUP_MAX", 2)

    with patch.object(ws, "_enqueue", return_value={"id": 1}) as enq:
        out = ws.catch_up_missed_files(now=NOW)

    assert out["enqueued"] == 2
    assert out["truncated"] == 3
    assert [c.args[0] for c in enq.call_args_list] == [
        "/likivik/files/Work/f1.pdf",
        "/likivik/files/Work/f2.pdf",
    ]


def test_old_watermark_is_clamped(monkeypatch):
    """A two-week outage must not turn into an unbounded scan."""
    ws._mark_webhook_received(NOW - 30 * 24 * 3600)
    _stub_propfind(monkeypatch, _xml([]))

    out = ws.catch_up_missed_files(now=NOW)

    assert out["since"] == pytest.approx(NOW - ws._CATCHUP_MAX_AGE)


def test_failed_propfind_keeps_watermark(monkeypatch):
    ws._mark_webhook_received(NOW - 600)

    def boom(*a, **k):
        raise ws.requests.ConnectionError("nc down")

    monkeypatch.setattr(ws.requests, "request", boom)

    out = ws.catch_up_missed_files(now=NOW)

    assert "propfind_failed" in out["reason"]
    assert out["enqueued"] == 0
    # Untouched → the next restart retries the same window.
    assert _watermark() == pytest.approx(NOW - 600)


# --- parsing ---------------------------------------------------------------


def test_parse_handles_prefixes_and_percent_encoding():
    xml = (
        '<?xml version="1.0"?><D:multistatus xmlns:D="DAV:">'
        "<D:response><D:href>/remote.php/dav/files/likivik/Work/a%20b.pdf</D:href>"
        f"<D:propstat><D:prop><D:getlastmod>{_http_date(NOW)}</D:getlastmod>"
        "</D:prop></D:propstat></D:response>"
        "</D:multistatus>"
    )
    entries = ws._parse_propfind_lastmods(xml)
    assert len(entries) == 1
    path, mtime = entries[0]
    assert path == "Work/a b.pdf"
    assert mtime == pytest.approx(NOW)


# --- endpoint --------------------------------------------------------------


def test_catch_up_endpoint_requires_secret():
    client = TestClient(ws.app)
    assert client.post("/catch-up").status_code == 401


def test_catch_up_endpoint_runs_pass(monkeypatch):
    client = TestClient(ws.app)
    ws._mark_webhook_received(NOW - 600)
    _stub_propfind(monkeypatch, _xml([("Work/x.pdf", _http_date(NOW - 30))]))

    with patch.object(ws, "_enqueue", return_value={"id": 1}):
        r = client.post("/catch-up", headers={"X-Webhook-Secret": SECRET})

    assert r.status_code == 200
    assert r.json()["enqueued"] == 1


def test_webhook_writes_watermark(monkeypatch):
    """Any delivered webhook proves liveness, even an ignored event."""
    client = TestClient(ws.app)
    ws.jobstore._reset_for_tests()
    body = {"event": {"class": "uninteresting", "node": {}}}

    r = client.post("/webhook", json=body, headers={"X-Webhook-Secret": SECRET})

    assert r.status_code == 200
    assert _watermark() is not None
