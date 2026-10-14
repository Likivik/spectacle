"""Tests for webhook_server queue endpoints: /status, /rescan, /scan-all.

Uses FastAPI TestClient with a stubbed _process_file and mocked WebDAV
(scan-all PROPFIND) — no Nextcloud or tesseract required.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Point jobstore at a writable directory BEFORE webhook_server is imported.
# ``webhook_server`` calls ``jobstore.init()`` at module load time; without
# this, the default /var/lib/nc-ocr/jobs.db path is unreadable in the test
# environment (the unit runs as the hermes user) and every ``file_put`` /
# ``claim_next`` silently no-ops, leaving the queue/processed/file tables
# empty. A fresh tmpdir per pytest process keeps the suite hermetic and
# parallel-safe.
os.environ.setdefault(
    "NC_OCR_STATE_DIR", tempfile.mkdtemp(prefix="ncocr-tests-")
)

# Snapshot the path we picked so the autouse fixture below can re-pin
# it after another test file in the suite (``test_jobstore.py``::
# ``test_db_path_resolution_env_precedence`` in particular) leaves the
# env var cleared.
_STATE_DIR = os.environ["NC_OCR_STATE_DIR"]


@pytest.fixture(autouse=True)
def _repin_state_dir():
    """Re-pin ``NC_OCR_STATE_DIR`` before every test in this file.

    ``test_db_path_resolution_env_precedence`` legitimately pops the env
    var between two ``_Env`` blocks. Without this re-pin the next
    ``jobstore.init()`` (after ``_reset_for_tests``) would resolve the
    DB path from ``/var/lib/nc-ocr`` and silently fall back to a
    permission-denied no-op state.
    """
    os.environ["NC_OCR_STATE_DIR"] = _STATE_DIR
    yield


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

import nc_ocr_flow.webhook_server as ws  # noqa: E402

SECRET = "test-secret"


def _drain(timeout: float = 10.0) -> None:
    """Wait until the SQLite queue has nothing queued or running.

    The work list used to be an in-process ``queue.Queue``; it is now the
    ``jobs`` table, so draining means polling the store instead of
    ``queue.join()``.
    """
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        s = ws.jobstore.stats()
        if not s.get("queued") and not s.get("running"):
            return
        time.sleep(0.05)
    raise AssertionError("SQLite queue did not drain within %.1fs" % timeout)


@pytest.fixture()
def client(monkeypatch):
    """TestClient with WEBHOOK_SECRET set and OCR worker stubbed."""
    monkeypatch.setattr(ws, "WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(ws, "NC_PASSWORD", "test-pass")

    # Empty the queue & history between tests. All durable state lives in
    # SQLite now, so a single reset covers jobs, files, processed, settings.
    ws.jobstore._reset_for_tests()

    # Stub out actual processing: instant success. ``force=None`` keeps
    # the stub signature compatible with both /webhook (force default)
    # and /rescan (force=True) call shapes.
    def fake_process(nc_path, node_id, engine="auto", force=None):
        return {"path": nc_path, "output": nc_path, "vlm_pages": []}

    # The real ``_webdav_stat`` waits ~4.5s for the live Nextcloud's
    # PROPFIND to settle before returning size/etag. There is no NC here,
    # and the size/etag it would record are only consulted by the panel
    # UI's "is this OCR still valid?" check — never by /status, /rescan,
    # /scan-all, or the worker's bookkeeping. Short-circuit so the worker
    # thread completes in milliseconds instead of racing the assertions
    # below.
    monkeypatch.setattr(ws, "_webdav_stat", lambda *a, **k: (None, None))

    with patch.object(ws, "_process_file", side_effect=fake_process):
        yield TestClient(ws.app)


def h():
    return {"X-Webhook-Secret": SECRET}


# --- /status ---------------------------------------------------------------

def test_fails_closed_when_secret_not_configured(monkeypatch):
    """An unset secret must refuse requests, not disable auth."""
    monkeypatch.setattr(ws, "WEBHOOK_SECRET", "")
    c = TestClient(ws.app)
    assert c.get("/status", headers=h()).status_code == 503
    assert c.post("/webhook", headers=h(), json={}).status_code == 503


def test_panel_is_not_frameable(client):
    """The /panel endpoint is local-only (defence-in-depth) and serves
    anti-frame headers — it asks for the webhook secret, so embedding
    it would be a phishing surface.

    Two contracts verified here:

      1. A non-local client (the default TestClient presents as
         host="testclient") is rejected with 403 — the local-only
         lockdown is the security fix.
      2. A loopback client gets 200 + the anti-frame headers that
         make embedding impossible in the first place (X-Frame-Options
         + CSP frame-ancestors 'none').
    """
    # 1) Non-local → 403 (the lockdown is the point of this assertion).
    r = client.get("/panel")
    assert r.status_code == 403

    # 2) Loopback → 200 + anti-frame headers. ``TestClient(client=...)``
    # overrides the ASGI scope's ``client`` tuple so ``request.client.host``
    # is the loopback the production check whitelists.
    local = TestClient(ws.app, client=("127.0.0.1", 5000))
    r2 = local.get("/panel")
    assert r2.status_code == 200
    assert r2.headers.get("X-Frame-Options") == "DENY"
    assert "frame-ancestors 'none'" in r2.headers.get(
        "Content-Security-Policy", ""
    )


def test_status_requires_secret(client):
    r = client.get("/status")
    assert r.status_code == 401


def test_status_empty(client):
    r = client.get("/status", headers=h())
    assert r.status_code == 200
    d = r.json()
    assert d["service"] == "nc-ocr-flow"
    assert d["queue_depth"] == 0
    assert d["queued"] == []
    assert d["running"] == []
    assert d["history"] == []


# --- /rescan ---------------------------------------------------------------

def test_rescan_requires_secret(client):
    r = client.post("/rescan", json={"path": "/likivik/files/a.pdf"})
    assert r.status_code == 401


def test_rescan_bad_ext(client):
    r = client.post("/rescan", json={"path": "/likivik/files/a.txt"}, headers=h())
    assert r.status_code == 422


def test_rescan_bad_engine(client):
    r = client.post(
        "/rescan",
        json={"path": "/likivik/files/a.pdf", "engine": "quantum"},
        headers=h(),
    )
    assert r.status_code == 422


def test_rescan_trashbin_rejected(client):
    r = client.post(
        "/rescan",
        json={"path": "/likivik/files_trashbin/a.pdf"},
        headers=h(),
    )
    assert r.status_code == 422


def test_rescan_enqueues(client):
    r = client.post(
        "/rescan",
        json={"path": "/likivik/files/Work/a.pdf", "engine": "minimax"},
        headers=h(),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "queued"
    assert d["engine"] == "minimax"
    assert d["job_id"] >= 1
    # Drain here so the worker finishes (and re-reads the freshly-reset
    # SQLite DB) before the next test's ``_reset_for_jobs_for_tests``
    # wipes the DB out from under a still-running _run_job. Without this
    # drain the next test sees ``spy.call_count == 2``: worker-A is
    # still mid-processing this test's job (writing to the orphan inode
    # of the unlinked DB) when worker-B picks up the next test's job.
    _drain()


def test_rescan_clears_processed_guard(client):
    """node_id in recently_processed → rescan re-enqueues (not skipped).

    Note: after the worker finishes the (stubbed) job it re-marks node 42 —
    so we assert the job actually went through the queue, not the final
    guard state.
    """
    ws._mark_processed(42)
    assert ws._is_recently_processed(42)

    with patch.object(ws, "_process_file", wraps=ws._process_file) as spy:
        client.post(
            "/rescan",
            json={"path": "/likivik/files/a.pdf", "node_id": 42},
            headers=h(),
        )
        _drain()
        # _process_file was called — the guard did not drop the job
        assert spy.call_count == 1


# --- /scan-all ---------------------------------------------------------------

def _propfind_xml(href_path: str) -> str:
    return (
        '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
        f"<d:response><d:href>/remote.php/dav/files/likivik/{href_path}</d:href>"
        "<d:propstat><d:prop><d:resourcetype/></d:prop></d:propstat>"
        "</d:response></d:multistatus>"
    )


def test_scan_all_requires_secret(client):
    r = client.post("/scan-all", json={"folder": ""})
    assert r.status_code == 401


def test_scan_all_bad_engine(client):
    r = client.post(
        "/scan-all", json={"folder": "", "engine": "nope"}, headers=h()
    )
    assert r.status_code == 422


def test_scan_all_enqueues_pdfs_skips_ocrd(client, monkeypatch):
    """PROPFIND returns 3 files: 2 PDFs + 1 txt. One PDF already done."""
    xml = _propfind_xml("Work/a.pdf") + _propfind_xml("Work/b.pdf") \
        + _propfind_xml("Work/c.txt")

    class FakeResp:
        text = xml
        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        ws.requests, "request", lambda *a, **k: FakeResp()
    )

    # Mark a.pdf as already OCR'd
    ws.jobstore.file_put({"path": "/likivik/files/Work/a.pdf", "status": "done"})

    r = client.post(
        "/scan-all",
        json={"folder": "Work", "engine": "google", "skip_ocrd": True},
        headers=h(),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "queued"
    assert d["enqueued"] == 1          # only b.pdf
    assert d["skipped_ocrd"] == 1      # a.pdf skipped

    # Worker already drained the queue (stub is instant): verify via the index
    _drain()
    done_paths = {p for p, m in ws.jobstore.file_all().items()
                  if m.get("status") == "done"}
    assert "/likivik/files/Work/b.pdf" in done_paths
    # a.pdf was marked done in the setup above (line 202). scan-all with
    # skip_ocrd=True only READS the file index to decide to skip the
    # enqueue — it does NOT touch the row for skipped files. So the
    # real contract is that a.pdf's status is preserved (still done),
    # not that it is absent. The previous assertion (a.pdf not in
    # done_paths) contradicted the very setup that made the skip test
    # possible and could never hold once file_put was wired up to
    # SQLite.
    assert "/likivik/files/Work/a.pdf" in done_paths


def test_scan_all_no_skip_when_disabled(client, monkeypatch):
    xml = _propfind_xml("Work/a.pdf")

    class FakeResp:
        text = xml
        def raise_for_status(self):
            pass

    monkeypatch.setattr(ws.requests, "request", lambda *a, **k: FakeResp())
    ws.jobstore.file_put({"path": "/likivik/files/Work/a.pdf", "status": "done"})

    r = client.post(
        "/scan-all",
        json={"folder": "Work", "skip_ocrd": False},
        headers=h(),
    )
    d = r.json()
    assert d["enqueued"] == 1
    assert d["skipped_ocrd"] == 0
    # Drain the queued job before the next test starts (see the
    # long-form comment in test_rescan_enqueues for the race we're
    # avoiding — same shape: an in-flight _run_job crossing the test
    # boundary survives a SQLite reset and re-claims a later job).
    _drain()


# --- metadata stamping -------------------------------------------------------

def test_stamp_metadata(tmp_path):
    fitz = pytest.importorskip("fitz")
    # Use the cached ``ws`` reference so the call lands on the same
    # module instance other tests in this suite have monkeypatched /
    # popped / re-imported (see test_process_file_* above).
    _stamp_metadata = ws._stamp_metadata

    pdf = tmp_path / "t.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf))
    doc.close()

    _stamp_metadata(
        pdf, engine="auto",
        vlm_pages=[4, 5, 9], tess_pages=[0, 1, 2, 3],
    )

    meta = fitz.open(str(pdf)).metadata
    assert meta["producer"].startswith("nc-ocr-flow")
    assert "engine=auto" in meta["producer"]
    # New 0.3 format: Subject carries input_sha256, source=current,
    # langs=rus+eng, per-engine api/ver, and the page ranges.
    subject = meta["subject"]
    assert subject.startswith("OCR ")
    assert "source=current" in subject
    assert "langs=rus+eng" in subject
    assert "input_sha256=" in subject
    assert "auto:api=" in subject
    assert "auto:ver=" in subject
    assert "tesseract_pages=1-4" in subject
    assert "vlm_pages=5-6,10" in subject
    assert "nc-ocr-flow" in meta["keywords"]


# --- worker → ocrd_paths bookkeeping ----------------------------------------

def test_worker_marks_ocrd(client):
    """After worker processes a job, its path is marked done in jobstore."""
    client.post(
        "/rescan", json={"path": "/likivik/files/x.pdf"}, headers=h()
    )
    _drain()  # wait for the worker to drain the SQLite queue
    assert (ws.jobstore.file_get("/likivik/files/x.pdf")
            or {}).get("status") == "done"


# --- born-digital / force-skip --------------------------------------------

def _build_pdf(path, *, with_text=True):
    """Create a minimal PDF at ``path`` (with or without text)."""
    import fitz
    doc = fitz.open()
    p = doc.new_page()
    if with_text:
        p.insert_text((72, 72), "Hello world born-digital text " * 4)
    doc.save(str(path))
    doc.close()


def test_process_file_force_bypasses_skip(monkeypatch, tmp_path):
    """force=True → process_pdf runs even when classify says no-need.

    With a born-digital text_based input and force=True, the skip
    decision must be bypassed and process_pdf must be invoked.
    """
    pdf = tmp_path / "x.pdf"
    _build_pdf(pdf, with_text=True)

    calls = {"proc": []}

    def fake_proc(pdf_path, engine=None):
        calls["proc"].append((str(pdf_path), engine))
        from nc_ocr_flow.ocr import ProcessResult
        return ProcessResult(output_pdf=str(pdf_path), engine_used="google")

    # classify returns needs_ocr=False → would normally skip.
    def fake_classify(_path):
        return {
            "needs_ocr": False,
            "pdf_type": "text_based",
            "confidence": 1.0,
            "has_encoding_issues": False,
        }

    # NB: keep all module access via the cached ``ws`` reference instead
    # of ``from nc_ocr_flow.webhook_server import _process_file`` — other
    # tests in this directory (test_ocr_logic.py's test_loop_prevention)
    # legitimately pop the webhook_server module from sys.modules and
    # re-import it. A bare ``from … import …`` would re-resolve the
    # module at call time and bypass the patches below (the freshly
    # imported module's ``process_pdf`` would then reach the real
    # Google engine and trip Application Default Credentials).
    monkeypatch.setattr(
        ws, "_webdav_download",
        lambda nc, dest: __import__("shutil").copy2(pdf, dest),
    )
    monkeypatch.setattr(ws, "_webdav_upload", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_stamp_metadata", lambda *a, **k: None)
    with patch.object(ws, "process_pdf", side_effect=fake_proc), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        res = ws._process_file("/likivik/files/x.pdf", node_id=1,
                               engine="google", force=True)

    # force=True bypassed the skip; process_pdf was called.
    assert calls["proc"], "force=True must invoke process_pdf even when classifier says skip"
    assert res.get("skipped") is not True
    assert res.get("path") == "/likivik/files/x.pdf"


def test_process_file_skips_born_digital(monkeypatch, tmp_path):
    """classifier says needs_ocr=False → _process_file returns skipped.

    No prior Google-stamp (file is fresh) → classifier decides →
    ``born_digital_or_stamped_good`` skip reason. process_pdf MUST
    not be called.
    """
    pdf = tmp_path / "y.pdf"
    _build_pdf(pdf, with_text=True)

    calls = {"proc": []}

    def fake_proc(pdf_path, engine=None):
        calls["proc"].append(str(pdf_path))
        from nc_ocr_flow.ocr import ProcessResult
        return ProcessResult(output_pdf=str(pdf_path), engine_used="google")

    def fake_classify(_path):
        return {
            "needs_ocr": False,
            "pdf_type": "text_based",
            "confidence": 1.0,
            "has_encoding_issues": False,
        }

    monkeypatch.setattr(ws, "_webdav_download",
                       lambda nc, dest: __import__("shutil").copy2(pdf, dest))
    monkeypatch.setattr(ws, "_webdav_upload", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_stamp_metadata", lambda *a, **k: None)
    with patch.object(ws, "process_pdf", side_effect=fake_proc), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        res = ws._process_file("/likivik/files/y.pdf", node_id=2,
                               engine="google", force=False)

    assert calls["proc"] == [], "process_pdf must NOT run when classifier says skip"
    assert res.get("skipped") is True
    assert res.get("reason") == "born_digital_or_stamped_good"


def test_process_file_bad_layer_reocr(monkeypatch, tmp_path):
    """classifier says needs_ocr=True → _process_file OCRs the file.

    Pathological input: a PDF whose classifier flags encoding issues
    (or is otherwise not text_based). _process_file must invoke
    process_pdf and return a non-skip result.
    """
    pdf = tmp_path / "z.pdf"
    _build_pdf(pdf, with_text=False)  # blank page — pdf-inspector calls it "scanned"

    calls = {"proc": []}

    def fake_proc(pdf_path, engine=None):
        calls["proc"].append((str(pdf_path), engine))
        from nc_ocr_flow.ocr import ProcessResult
        return ProcessResult(output_pdf=str(pdf_path), engine_used="google")

    def fake_classify(_path):
        return {
            "needs_ocr": True,
            "pdf_type": "scanned",
            "confidence": 0.95,
            "has_encoding_issues": False,
        }

    monkeypatch.setattr(ws, "_webdav_download",
                       lambda nc, dest: __import__("shutil").copy2(pdf, dest))
    monkeypatch.setattr(ws, "_webdav_upload", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_stamp_metadata", lambda *a, **k: None)
    with patch.object(ws, "process_pdf", side_effect=fake_proc), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        res = ws._process_file("/likivik/files/z.pdf", node_id=3,
                               engine="google", force=False)

    assert calls["proc"], "classifier said needs_ocr=True → process_pdf must run"
    assert res.get("skipped") is not True
    assert res.get("path") == "/likivik/files/z.pdf"
