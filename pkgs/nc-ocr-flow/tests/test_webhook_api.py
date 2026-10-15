"""Tests for webhook_server queue endpoints: /status, /rescan, /scan-all.

Uses FastAPI TestClient with a stubbed _process_file and mocked WebDAV
(scan-all PROPFIND) — no Nextcloud or tesseract required.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
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
    # 0.4: Subject carries the stamp_version, input_sha256, source=current,
    # langs=rus+eng, per-engine api/ver, and the page ranges.
    subject = meta["subject"]
    assert subject.startswith("OCR ")
    assert f"stamp_version={ws.STAMP_VERSION}" in subject
    assert "source=current" in subject
    assert "langs=rus+eng" in subject
    assert "input_sha256=" in subject
    assert "auto:api=" in subject
    assert "auto:ver=" in subject
    assert "tesseract_pages=1-4" in subject
    assert "vlm_pages=5-6,10" in subject
    # 0.4 also writes a custom XMP property under our private namespace —
    # see :func:`_stamp_metadata`. This is the field the durable
    # ``_already_stamped_by_us`` check reads.
    assert f"stamp_version={ws.STAMP_VERSION}" in meta["keywords"]


def test_stamp_writes_durable_xmp_property(tmp_path):
    """The 0.4 stamp must carry a custom XMP property that survives a
    pikepdf re-save (the storage-layer behaviour Nextcloud uses).

    The previous stamp used ``Producer`` only, and ``Producer`` is
    rewritten by Nextcloud's storage layer on every WebDAV PUT — two
    files were re-OCR'd 17+ times in a single day before this fix.
    XMP under a custom namespace is not regenerated by pikepdf (we
    verified empirically), so the new marker is the durable one.
    """
    fitz = pytest.importorskip("fitz")
    pikepdf = pytest.importorskip("pikepdf")

    pdf = tmp_path / "t.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf))
    doc.close()

    ws._stamp_metadata(
        pdf, engine="google", vlm_pages=[0], tess_pages=[0],
    )

    # Read the XMP packet that _stamp_metadata wrote and confirm it
    # carries our private-namespace stamp.
    with fitz.open(str(pdf)) as d:
        xml_xref = d.xref_xml_metadata()
        assert xml_xref, "no XMP stream after stamping"
        raw = d.xref_stream(xml_xref) or b""
    props = ws._parse_xmp_stamp(raw)
    assert props.get("stamp") == ws.STAMP_VERSION
    assert props.get("engine") == "google"

    # Round-trip through pikepdf (NC's storage layer uses pikepdf on
    # every WebDAV PUT). The marker MUST survive.
    re_saved = tmp_path / "t_resaved.pdf"
    with pikepdf.open(str(pdf)) as p:
        p.save(str(re_saved))
    with fitz.open(str(re_saved)) as d:
        xml_xref = d.xref_xml_metadata()
        raw2 = d.xref_stream(xml_xref) or b""
    props2 = ws._parse_xmp_stamp(raw2)
    assert props2.get("stamp") == ws.STAMP_VERSION, (
        "XMP stamp must survive pikepdf re-save; got %r" % (props2,)
    )


def test_already_stamped_requires_current_version(tmp_path):
    """A pre-0.4 stamp (or absent stamp) must NOT be considered stamped.

    The 0.3 parser silently returned zero text on a long stretch of
    runs, so any stamp it produced is untrustworthy. The user-decided
    migration policy is a one-time re-OCR of everything stamped before
    this fix: any stamp whose version does not match
    :data:`STAMP_VERSION` must yield ``False`` from
    :func:`_already_stamped_by_us`.
    """
    fitz = pytest.importorskip("fitz")

    pdf = tmp_path / "t.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf))
    doc.close()

    # 1. No stamp at all → False.
    assert ws._already_stamped_by_us(pdf) is False

    # 2. Hand-write a 0.3-era stamp (Producer-only) and confirm we
    #    still do NOT consider it stamped.
    with fitz.open(str(pdf)) as d:
        d.set_metadata({
            "producer": "nc-ocr-flow 0.3 (engine=google)",
            "subject": "OCR legacy stamp",
        })
        d.saveIncr()
    assert ws._already_stamped_by_us(pdf) is False, (
        "0.3 Producer stamp must NOT count as a current stamp"
    )

    # 3. Subject carries an older stamp_version (e.g. 0.3) → False.
    with fitz.open(str(pdf)) as d:
        d.set_metadata({
            "producer": "other", "subject": "OCR stamp_version=0.3"
        })
        d.saveIncr()
    assert ws._already_stamped_by_us(pdf) is False

    # 4. Hand-write a current XMP stamp → True.
    with fitz.open(str(pdf)) as d:
        d.set_xml_metadata(ws._build_stamp_xmp("google", "v1", "v1"))
        d.saveIncr()
    assert ws._already_stamped_by_us(pdf) is True


def test_xmp_stamp_round_trip_parser_safe():
    """The XMP parser must accept a stamp we emit and reject garbage.

    Also pins the parser to ignore unknown attributes / other rdf:
    Description blocks — only attributes under our private namespace
    count as a stamp.
    """
    xml = ws._build_stamp_xmp("google", "v1", "v1")
    props = ws._parse_xmp_stamp(xml)
    assert props.get("stamp") == ws.STAMP_VERSION
    assert props.get("engine") == "google"
    assert props.get("engine_api") == "v1"

    # Garbage in → empty out, no exception.
    assert ws._parse_xmp_stamp("") == {}
    assert ws._parse_xmp_stamp(b"<<not really xml>>") == {}
    assert ws._parse_xmp_stamp("<rdf:Description/>") == {}

    # A different-namespace description is ignored.
    other_ns = (
        '<?xml version="1.0"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:other="urn:test" rdf:about=""'
        ' other:stamp="0.4"/>'
        '</rdf:RDF>'
        '</x:xmpmeta>'
    )
    assert ws._parse_xmp_stamp(other_ns) == {}


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

    def fake_proc_with_blocks(pdf_path, engine=None):
        """Helper: stub process_pdf that returns a non-empty page_results,
        so it clears the ``_assert_ocr_produced_blocks`` zero-block gate
        introduced in this PR. Without this stub the old test kept
        returning ``ProcessResult(page_results=[])`` and now (correctly)
        trips the gate."""
        from nc_ocr_flow.ocr import ProcessResult
        from nc_ocr_flow.ocr_models import OcrBlock, OcrResult
        return ProcessResult(
            output_pdf=str(pdf_path),
            engine_used="google",
            page_results=[
                OcrResult(
                    blocks=[OcrBlock(
                        bbox=(10.0, 10.0, 100.0, 30.0),
                        text="stub-ocr-text",
                        confidence=0.95,
                        label="google-word",
                    )],
                    page_width=595.0, page_height=842.0,
                ),
            ],
        )

    calls = {"proc": []}

    def fake_proc(pdf_path, engine=None):
        calls["proc"].append((str(pdf_path), engine))
        return fake_proc_with_blocks(pdf_path, engine)

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
    """classifier says needs_ocr=False AND not stamped → ``born_digital_text_based``.

    No prior Google-stamp (the stamp check is monkeypatched False below),
    so the classifier decides the skip. The reason string recorded in the
    response must distinguish this branch from the ``stamped_good_by_us``
    branch — both used to be collapsed into ``born_digital_or_stamped_good``
    and the operator couldn't tell them apart on the panel. process_pdf MUST
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

    # Force the stamp check False so the test is unambiguously about the
    # classifier branch — the stamp branch is covered separately by
    # ``test_process_file_skip_reasons_distinguish_stamped_vs_born_digital``
    # below.
    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: False)
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
    # New contract (was ``born_digital_or_stamped_good``): the reason
    # recorded in the response must be the classifier branch, NOT the
    # stamp branch, so an operator can tell them apart on the panel.
    assert res.get("reason") == ws.SKIP_REASON_BORN_DIGITAL
    assert res.get("reason") != ws.SKIP_REASON_STAMPED_BY_US
    # Sanity: the legacy undifferentiated string is no longer emitted.
    assert res.get("reason") != ws.SKIP_REASON_LEGACY


def test_process_file_skip_reasons_distinguish_stamped_vs_born_digital(
    monkeypatch, tmp_path,
):
    """The two skip branches must produce DISTINCT reason strings.

    Pre-PR both branches collapsed into ``born_digital_or_stamped_good``,
    which made it impossible to tell "we already OCR'd this with Google"
    apart from "the classifier thinks this is born-digital". This test
    pins that contract: the stamp branch emits ``stamped_good_by_us`` and
    the classifier branch emits ``born_digital_text_based``, and the
    _legacy_ undifferentiated string is no longer emitted by either.
    """
    # --- Case 1: stamped by us → ``stamped_good_by_us`` -------------------
    pdf_stamped = tmp_path / "stamped.pdf"
    _build_pdf(pdf_stamped, with_text=True)

    def fake_classify_stamped(_path):
        # Classifier would ALSO say skip (text_based), but the stamp check
        # short-circuits before the classifier is consulted. We make the
        # classifier raise to prove the stamp branch doesn't depend on it.
        raise AssertionError("classify must not be called when stamp matches")

    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: True)
    monkeypatch.setattr(
        ws, "_webdav_download",
        lambda nc, dest: __import__("shutil").copy2(pdf_stamped, dest),
    )
    monkeypatch.setattr(ws, "_webdav_upload", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_stamp_metadata", lambda *a, **k: None)
    with patch.object(ws, "process_pdf") as proc_mock, \
         patch.object(ws, "classify_pdf", side_effect=fake_classify_stamped):
        res_stamped = ws._process_file(
            "/likivik/files/stamped.pdf", node_id=10,
            engine="google", force=False,
        )
    proc_mock.assert_not_called()
    assert res_stamped.get("skipped") is True
    assert res_stamped.get("reason") == ws.SKIP_REASON_STAMPED_BY_US
    assert res_stamped.get("reason") != ws.SKIP_REASON_BORN_DIGITAL
    assert res_stamped.get("reason") != ws.SKIP_REASON_LEGACY

    # --- Case 2: clean text_based, NOT stamped → ``born_digital_text_based``
    pdf_clean = tmp_path / "clean.pdf"
    _build_pdf(pdf_clean, with_text=True)

    def fake_classify_clean(_path):
        return {
            "needs_ocr": False,
            "pdf_type": "text_based",
            "confidence": 1.0,
            "has_encoding_issues": False,
        }

    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: False)
    monkeypatch.setattr(
        ws, "_webdav_download",
        lambda nc, dest: __import__("shutil").copy2(pdf_clean, dest),
    )
    monkeypatch.setattr(ws, "_webdav_upload", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_stamp_metadata", lambda *a, **k: None)
    with patch.object(ws, "process_pdf") as proc_mock, \
         patch.object(ws, "classify_pdf", side_effect=fake_classify_clean):
        res_clean = ws._process_file(
            "/likivik/files/clean.pdf", node_id=11,
            engine="google", force=False,
        )
    proc_mock.assert_not_called()
    assert res_clean.get("skipped") is True
    assert res_clean.get("reason") == ws.SKIP_REASON_BORN_DIGITAL
    assert res_clean.get("reason") != ws.SKIP_REASON_STAMPED_BY_US
    assert res_clean.get("reason") != ws.SKIP_REASON_LEGACY


def test_needs_ocr_decision_force_true_returns_true_none(monkeypatch, tmp_path):
    """Unit-level contract for ``_needs_ocr_decision``: ``force=True`` bypasses.

    The runtime skip behaviour is unchanged by the reason-split PR, but
    ``_needs_ocr_decision`` is now a ``(bool, str | None)`` pair. When
    ``force=True`` the function must return ``(True, None)`` — i.e. it
    does NOT report a skip reason, and the caller (``_process_file``) is
    not in the skip branch.

    We additionally assert that, even when both the stamp check and the
    classifier would otherwise say skip, ``force=True`` short-circuits
    before either is consulted — so the (True, None) return is robust
    to whatever upstream signals look like.
    """
    pdf = tmp_path / "any.pdf"
    _build_pdf(pdf, with_text=True)

    # Both short-circuit inputs would say skip — but ``force=True`` wins.
    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: True)

    def would_classify_skip(_path):
        raise AssertionError(
            "classify_pdf must NOT be consulted when force=True; the "
            "stamp check is the first branch and is bypassed by force"
        )

    with patch.object(ws, "classify_pdf", side_effect=would_classify_skip):
        needs_ocr, skip_reason = ws._needs_ocr_decision(pdf, force=True)

    assert needs_ocr is True, "force=True must always force OCR"
    assert skip_reason is None, (
        "force=True must not carry a skip reason — the function is in "
        "the 'OCR must run' branch, not the 'skip' branch"
    )


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
        from nc_ocr_flow.ocr_models import OcrBlock, OcrResult
        # Non-empty page_results — see _assert_ocr_produced_blocks gate.
        return ProcessResult(
            output_pdf=str(pdf_path),
            engine_used="google",
            page_results=[
                OcrResult(
                    blocks=[OcrBlock(
                        bbox=(10.0, 10.0, 100.0, 30.0),
                        text="stub-ocr-text",
                        confidence=0.95,
                        label="google-word",
                    )],
                    page_width=595.0, page_height=842.0,
                ),
            ],
        )

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


# --- zero-block OCR gate (regression: Google bbox-parser bug) ---------------
#
# Background: pre-PR the Google engine returned ProcessResult with
# page_results=[] on every successful-looking run (silent bbox-parser
# bug). The webhook then unconditionally stamped + uploaded, marking
# the file ``done`` forever. This test pins the second half of the fix:
# _process_file MUST raise before stamping / uploading on a zero-block
# google result, so the worker's existing except path records
# ``status=error`` and the file stays eligible for retry.


def test_process_file_zero_block_does_not_stamp_or_upload(monkeypatch, tmp_path):
    """google engine returns 0 blocks → gate raises, no upload, no stamp.

    Asserts all three behaviours in one go:
      1. ``_process_file`` raises ``RuntimeError`` (gate fires).
      2. ``_webdav_upload`` is never called.
      3. ``_stamp_metadata`` is never called.
      4. The error message names the file, the engine, and the block count
         so an operator triaging the panel can act on it.
    """
    pdf = tmp_path / "empty.pdf"
    _build_pdf(pdf, with_text=False)

    calls = {"upload": [], "stamp": []}

    monkeypatch.setattr(
        ws, "_webdav_download",
        lambda nc, dest: __import__("shutil").copy2(pdf, dest),
    )
    monkeypatch.setattr(
        ws, "_webdav_upload",
        lambda nc, dest, *a, **k: calls["upload"].append((nc, str(dest))),
    )
    monkeypatch.setattr(
        ws, "_stamp_metadata",
        lambda *a, **k: calls["stamp"].append(a),
    )

    def fake_proc_empty(pdf_path, engine=None):
        # The bug shape: a "successful" run whose page_results is empty.
        from nc_ocr_flow.ocr import ProcessResult
        return ProcessResult(
            output_pdf=str(pdf_path),
            engine_used="google",
            page_results=[],   # would have been empty pre-fix
        )

    def fake_classify(_path):
        return {
            "needs_ocr": True,
            "pdf_type": "scanned",
            "confidence": 0.95,
            "has_encoding_issues": False,
        }

    with patch.object(ws, "process_pdf", side_effect=fake_proc_empty), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        with pytest.raises(RuntimeError) as ei:
            ws._process_file(
                "/likivik/files/empty.pdf", node_id=42,
                engine="google", force=False,
            )

    # Gate fired with a message that an operator can actually triage on.
    msg = str(ei.value)
    assert "google" in msg, f"engine name missing from error: {msg!r}"
    assert "/likivik/files/empty.pdf" in msg, f"file path missing: {msg!r}"
    assert "0 blocks" in msg, f"block count missing: {msg!r}"

    # Stamp and upload must NOT have run — the file stays in-flight,
    # eligible for the next webhook or /rescan to retry it.
    assert calls["upload"] == [], (
        f"zero-block OCR must NOT trigger upload, got {calls['upload']!r}"
    )
    assert calls["stamp"] == [], (
        f"zero-block OCR must NOT trigger stamp, got {calls['stamp']!r}"
    )


def test_process_file_zero_block_image_branch_also_gates(monkeypatch, tmp_path):
    """Same gate, image branch (image → img2pdf → process_pdf → gates).

    The image branch builds a PDF from the image and then runs the same
    orchestrator; we stub the orchestrator to return an empty
    page_results and assert the same raise/upload/stamp invariants.
    """
    # Use any small image: a 100x100 white PNG via PIL.
    from PIL import Image
    img_path = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(img_path)

    calls = {"upload": [], "stamp": [], "delete": []}

    monkeypatch.setattr(
        ws, "_webdav_download",
        lambda nc, dest: __import__("shutil").copy2(img_path, dest),
    )
    monkeypatch.setattr(
        ws, "_webdav_upload",
        lambda nc, dest, *a, **k: calls["upload"].append((nc, str(dest))),
    )
    monkeypatch.setattr(
        ws, "_webdav_delete",
        lambda nc: calls["delete"].append(nc),
    )
    monkeypatch.setattr(
        ws, "_stamp_metadata",
        lambda *a, **k: calls["stamp"].append(a),
    )

    def fake_proc_empty(pdf_path, engine=None):
        from nc_ocr_flow.ocr import ProcessResult
        return ProcessResult(
            output_pdf=str(pdf_path),
            engine_used="google",
            page_results=[],
        )

    # Pretend the classifier says this image IS a document so we
    # reach the OCR branch. ``ws.classify`` is a module-level binding
    # imported from .classifier, so monkeypatch.setattr (not
    # patch.object) is the right tool here.
    monkeypatch.setattr(
        ws, "classify",
        lambda _path: SimpleNamespace(is_document=True, reason="ok"),
    )

    with patch.object(ws, "process_pdf", side_effect=fake_proc_empty):
        with pytest.raises(RuntimeError) as ei:
            ws._process_file(
                "/likivik/files/orig.png", node_id=7,
                engine="google", force=False,
            )

    assert "google" in str(ei.value)
    assert "/likivik/files/orig.png" in str(ei.value)

    assert calls["upload"] == [], (
        f"image-branch zero-block must NOT upload, got {calls['upload']!r}"
    )
    assert calls["stamp"] == [], (
        f"image-branch zero-block must NOT stamp, got {calls['stamp']!r}"
    )
    assert calls["delete"] == [], (
        f"image-branch zero-block must NOT delete the original, got "
        f"{calls['delete']!r}"
    )


def test_process_file_tesseract_engine_bypasses_gate(monkeypatch, tmp_path):
    """Tesseract writes the layer via ocrmypdf, leaving page_results=[].

    Counting blocks across page_results=[] would always raise; the
    gate explicitly exempts tesseract so existing flows keep working.
    This test pins the exemption.
    """
    pdf = tmp_path / "tess.pdf"
    _build_pdf(pdf, with_text=False)

    calls = {"upload": [], "stamp": []}

    monkeypatch.setattr(
        ws, "_webdav_download",
        lambda nc, dest: __import__("shutil").copy2(pdf, dest),
    )
    monkeypatch.setattr(
        ws, "_webdav_upload",
        lambda nc, dest, *a, **k: calls["upload"].append((nc, str(dest))),
    )
    monkeypatch.setattr(
        ws, "_stamp_metadata",
        lambda *a, **k: calls["stamp"].append(a),
    )

    def fake_proc_tess(pdf_path, engine=None):
        # Tesseract's actual ProcessResult shape: page_results=[],
        # tess_pages=[...]. The gate MUST NOT raise for this.
        from nc_ocr_flow.ocr import ProcessResult
        return ProcessResult(
            output_pdf=str(pdf_path),
            engine_used="tesseract",
            page_results=[],
            tess_pages=[0],
        )

    def fake_classify(_path):
        return {
            "needs_ocr": True,
            "pdf_type": "scanned",
            "confidence": 0.95,
            "has_encoding_issues": False,
        }

    with patch.object(ws, "process_pdf", side_effect=fake_proc_tess), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        # No raise expected — the tesseract exemption must hold.
        res = ws._process_file(
            "/likivik/files/tess.pdf", node_id=8,
            engine="tesseract", force=False,
        )

    assert res.get("skipped") is not True
    # Upload happens from the tempdir inside _process_file, not tmp_path;
    # verify the nc-side path matches and exactly one upload + one stamp ran.
    assert len(calls["upload"]) == 1
    nc_uploaded, _dest = calls["upload"][0]
    assert nc_uploaded == "/likivik/files/tess.pdf"
    assert len(calls["stamp"]) == 1, "tesseract success must stamp"


# --- folder-wide force on /scan-all -----------------------------------------

def test_scan_all_force_bypasses_skip_ocrd(client, monkeypatch):
    """``force=true`` must enqueue files even when ``status='done'``.

    This is the operator lever for \"the pre-0.4 stamp said done but the
    stamp is now untrustworthy — re-OCR the whole folder\". With
    ``skip_ocrd=true`` the file is skipped; with ``force=true`` it must
    be enqueued regardless.
    """
    xml = _propfind_xml("Work/a.pdf") + _propfind_xml("Work/b.pdf")

    class FakeResp:
        text = xml
        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        ws.requests, "request", lambda *a, **k: FakeResp()
    )
    # Mark both files as done — without force, /scan-all would skip both.
    ws.jobstore.file_put({"path": "/likivik/files/Work/a.pdf", "status": "done"})
    ws.jobstore.file_put({"path": "/likivik/files/Work/b.pdf", "status": "done"})

    # Baseline: no force → both skipped.
    r = client.post(
        "/scan-all",
        json={"folder": "Work", "skip_ocrd": True, "force": False},
        headers=h(),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["enqueued"] == 0, d
    assert d["skipped_ocrd"] == 2, d
    assert d["force"] is False
    _drain()

    # With force=true, both files must be re-enqueued despite being done.
    r = client.post(
        "/scan-all",
        json={"folder": "Work", "skip_ocrd": True, "force": True},
        headers=h(),
    )
    assert r.status_code == 200
    d = r.json()
    assert d["enqueued"] == 2, d
    assert d["skipped_ocrd"] == 0, d
    assert d["force"] is True
    _drain()


def test_scan_all_force_bypasses_path_in_flight(client, monkeypatch):
    """``force=true`` must enqueue files even if they're currently in-flight.

    Production scenario: a folder scan was started, the workers
    crashed mid-way, the file rows are stuck at ``status='queued'``,
    and the operator wants to retry the rest of the folder
    immediately rather than wait for the per-file 20-minute stale
    timeout. With ``force=true`` we trust the operator's intent and
    append a fresh job for every matched path; last writer wins when
    each job finishes.
    """
    xml = _propfind_xml("Work/stuck.pdf")

    class FakeResp:
        text = xml
        def raise_for_status(self):
            pass

    monkeypatch.setattr(ws.requests, "request", lambda *a, **k: FakeResp())
    ws.jobstore.file_put({
        "path": "/likivik/files/Work/stuck.pdf",
        "status": "queued",
    })

    r = client.post(
        "/scan-all",
        json={"folder": "Work", "force": False},
        headers=h(),
    )
    assert r.json()["enqueued"] == 0, "non-force must skip in-flight"
    _drain()

    r = client.post(
        "/scan-all",
        json={"folder": "Work", "force": True},
        headers=h(),
    )
    d = r.json()
    assert d["enqueued"] == 1, d
    assert d["forced_in_flight"] == 1, d
    assert d["force"] is True
    _drain()


def test_scan_all_default_behaviour_unchanged(client, monkeypatch):
    """The default ``force=false`` must preserve the pre-0.4 behaviour:
    skip_ocrd and in-flight checks both still apply.

    Regression guard: every existing field of the response (and the
    default for the new ``force`` field) must still match what /scan-all
    returned before this PR.
    """
    xml = _propfind_xml("Work/a.pdf")

    class FakeResp:
        text = xml
        def raise_for_status(self):
            pass

    monkeypatch.setattr(ws.requests, "request", lambda *a, **k: FakeResp())

    # Mark the file done — without force, must be skipped.
    ws.jobstore.file_put({"path": "/likivik/files/Work/a.pdf", "status": "done"})

    # Do NOT pass force at all — Pydantic default (False) must apply.
    r = client.post(
        "/scan-all",
        json={"folder": "Work", "skip_ocrd": True},
        headers=h(),
    )
    d = r.json()
    assert d["status"] == "queued"
    assert d["enqueued"] == 0
    assert d["skipped_ocrd"] == 1
    assert d["force"] is False
    assert d["forced_in_flight"] == 0
    _drain()


# --- orphan reconciler ------------------------------------------------------

def test_reconcile_recovers_orphan_queued_file():
    """A ``files.status='queued'`` row with no matching ``jobs`` row
    must be recovered: the reconciler inserts a fresh ``jobs`` row so
    a worker can pick the path up.

    This is the production-state fix for ``POST /scan-all
    {folder: \"Work/...\"} → enqueued=0`` while 11 files sit at
    ``status='queued'`` with no job rows.
    """
    path = "/likivik/files/Work/1-Afterglow/Сертификаты по Косметике/Наши/ПрофиМаркет/orphan.pdf"
    # Files row says queued; jobs table has nothing.
    ws.jobstore.file_put({"path": path, "status": "queued", "node_id": 0})
    assert ws.jobstore.orphaned_queued_paths() == [path]

    result = ws.reconcile_orphans()
    assert result["orphans_found"] == 1
    assert result["recovered"] == 1
    assert result["failed"] == 0
    assert path in result["paths"]

    # Now the orphan is gone — a matching jobs row exists. The
    # reconciler must NOT touch it on a second call (idempotent).
    assert ws.jobstore.orphaned_queued_paths() == []
    result2 = ws.reconcile_orphans()
    assert result2["orphans_found"] == 0
    assert result2["recovered"] == 0


def test_reconcile_does_not_disturb_running_job():
    """A genuinely running job (jobs row at 'running') MUST NOT be
    re-enqueued — the worker is mid-processing it.

    While a worker holds a job, ``files.status`` is still
    ``'queued'`` (we only write the terminal status when the worker
    finishes). The reconciler's NOT EXISTS join must therefore look at
    the ``jobs`` row's status, not the file row's status — exactly
    what the SQL below does.
    """
    path = "/likivik/files/Work/running.pdf"
    ws.jobstore.file_put({"path": path, "status": "queued", "node_id": 0})
    # Insert a jobs row in 'running' state for the same path.
    ws.jobstore.record_enqueue({
        "nc_path": path,
        "path": path,
        "node_id": 0,
        "engine": "google",
        "force": False,
        "status": "running",
    })

    assert ws.jobstore.orphaned_queued_paths() == [], (
        "running job must not be reported as orphan"
    )
    result = ws.reconcile_orphans()
    assert result["orphans_found"] == 0
    assert result["recovered"] == 0


def test_reconcile_does_not_disturb_queued_job():
    """A pending-but-not-yet-running job (jobs row at 'queued') MUST
    NOT be re-enqueued either — that would create a duplicate job.

    Same logic as the running case; tested separately because the
    SQL filter is on a literal status list, not on a comparison.
    """
    path = "/likivik/files/Work/pending.pdf"
    ws.jobstore.file_put({"path": path, "status": "queued", "node_id": 0})
    ws.jobstore.record_enqueue({
        "nc_path": path,
        "path": path,
        "node_id": 0,
        "engine": "google",
        "force": False,
        "status": "queued",
    })

    assert ws.jobstore.orphaned_queued_paths() == []
    result = ws.reconcile_orphans()
    assert result["orphans_found"] == 0


def test_reconcile_handles_multiple_orphans_in_one_call():
    """All orphans in one snapshot must be recovered by a single
    call — the operator should not have to hit the endpoint in a
    loop."""
    paths = [
        "/likivik/files/Work/a.pdf",
        "/likivik/files/Work/b.pdf",
        "/likivik/files/Work/Sub/c.pdf",
    ]
    for p in paths:
        ws.jobstore.file_put({"path": p, "status": "queued", "node_id": 0})
    # Plus a non-orphan (already done) — must be left alone.
    ws.jobstore.file_put({
        "path": "/likivik/files/Work/done.pdf", "status": "done", "node_id": 0,
    })

    result = ws.reconcile_orphans()
    assert sorted(result["paths"]) == sorted(paths)
    assert result["orphans_found"] == 3
    assert result["recovered"] == 3


def test_admin_reconcile_endpoint(client):
    """``POST /admin/reconcile-orphans`` is the operator's manual
    lever. It must require the webhook secret and call the same
    :func:`reconcile_orphans` function."""
    # No secret → 401.
    r = client.post("/admin/reconcile-orphans")
    assert r.status_code == 401

    # With secret → 200 + the same shape reconcile_orphans returns.
    ws.jobstore.file_put({
        "path": "/likivik/files/Work/orphan.pdf",
        "status": "queued", "node_id": 0,
    })
    r = client.post("/admin/reconcile-orphans", headers=h())
    assert r.status_code == 200
    d = r.json()
    assert d["orphans_found"] == 1
    assert d["recovered"] == 1
    assert "/likivik/files/Work/orphan.pdf" in d["paths"]


# --- image branch PDF collision ---------------------------------------------

def test_image_branch_refuses_to_overwrite_existing_pdf(monkeypatch, tmp_path):
    """The image branch must NOT silently replace an existing PDF with
    the freshly-OCR'd image-to-PDF. If the target path already has a
    PDF, we must skip with a distinct reason and leave the source
    image in place.
    """
    # Source: a real image on disk (we use the existing _image_to_pdf
    # path to write an actual PDF); Target: a pre-existing PDF on NC.
    from PIL import Image

    img_path = tmp_path / "Work" / "photo.jpg"
    img_path.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), color=(255, 0, 0)).save(img_path)
    nc_path = f"/{ws.NC_USER}/files/Work/photo.jpg"
    pdf_nc_path = f"/{ws.NC_USER}/files/Work/photo.pdf"

    monkeypatch.setattr(ws, "_propfind_size_etag",
                        lambda _p: (1234, "etag-mock"))

    calls = {"upload": [], "delete": []}

    def _fake_upload(nc_path_, src):
        calls["upload"].append(nc_path_)

    def _fake_delete(nc_path_):
        calls["delete"].append(nc_path_)

    monkeypatch.setattr(ws, "_webdav_upload", _fake_upload)
    monkeypatch.setattr(ws, "_webdav_delete", _fake_delete)

    # Stub the WebDAV GET to just copy our fixture image into the
    # tempdir _process_file will OCR from.
    def _fake_download(_nc_path, dest):
        import shutil
        shutil.copyfile(str(img_path), str(dest))

    monkeypatch.setattr(ws, "_webdav_download", _fake_download)

    # class stub that always says "yes, OCR me"
    class _Cls:
        is_document = True
        reason = "doc"

    monkeypatch.setattr(ws, "classify", lambda _p: _Cls())

    # The /tmp side: build a tiny PDF to feed process_pdf.
    import fitz  # noqa: F401  -- only used to construct fixture
    fake_out = tmp_path / "ocr_out.pdf"
    fitz_doc = fitz.open()
    fitz_doc.new_page(width=200, height=200)
    fitz_doc.save(str(fake_out))
    fitz_doc.close()

    monkeypatch.setattr(ws, "_image_to_pdf", lambda _p: fake_out)

    # process_pdf stub that returns a ProcessResult with one block on
    # one page so the zero-block guard doesn't fire.
    from nc_ocr_flow.ocr import ProcessResult
    from nc_ocr_flow.ocr_models import OcrBlock, OcrResult
    fake_result = ProcessResult(
        output_pdf=str(fake_out),
        engine_used="google",
        page_results=[OcrResult(
            blocks=[OcrBlock(bbox=(0, 0, 10, 10), text="hi",
                             confidence=0.9, label="text")],
            page_width=200, page_height=200,
        )],
        tess_pages=[],
        vlm_pages=[0],
    )
    monkeypatch.setattr(ws, "process_pdf", lambda *a, **k: fake_result)

    res = ws._process_file(nc_path, node_id=42, engine="google", force=False)
    assert res.get("skipped") is True, res
    assert res["reason"] == ws.SKIP_REASON_PDF_EXISTS, res
    assert res["existing_pdf"] == pdf_nc_path
    # Crucially: we did NOT upload or delete the source image.
    assert calls["upload"] == [], calls
    assert calls["delete"] == [], calls


def test_image_branch_proceeds_when_no_collision(monkeypatch, tmp_path):
    """Counter-test: when PROPFIND reports no existing PDF at the
    target path, the image branch must proceed exactly as before
    (upload + delete the source)."""
    from PIL import Image

    img_path = tmp_path / "Work" / "photo.jpg"
    img_path.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), color=(255, 0, 0)).save(img_path)
    nc_path = f"/{ws.NC_USER}/files/Work/photo.jpg"
    pdf_nc_path = f"/{ws.NC_USER}/files/Work/photo.pdf"

    # PROPFIND says no target PDF exists.
    monkeypatch.setattr(ws, "_propfind_size_etag",
                        lambda _p: (None, None))

    calls = {"upload": [], "delete": []}

    def _fake_upload(nc_path_, _src):
        calls["upload"].append(nc_path_)

    def _fake_delete(nc_path_):
        calls["delete"].append(nc_path_)

    monkeypatch.setattr(ws, "_webdav_upload", _fake_upload)
    monkeypatch.setattr(ws, "_webdav_delete", _fake_delete)

    # Stub the WebDAV GET to copy our fixture image into the tempdir.
    def _fake_download(_nc_path, dest):
        import shutil
        shutil.copyfile(str(img_path), str(dest))

    monkeypatch.setattr(ws, "_webdav_download", _fake_download)

    class _Cls:
        is_document = True
        reason = "doc"

    monkeypatch.setattr(ws, "classify", lambda _p: _Cls())

    import fitz
    fake_out = tmp_path / "ocr_out.pdf"
    fitz_doc = fitz.open()
    fitz_doc.new_page(width=200, height=200)
    fitz_doc.save(str(fake_out))
    fitz_doc.close()
    monkeypatch.setattr(ws, "_image_to_pdf", lambda _p: fake_out)

    from nc_ocr_flow.ocr import ProcessResult
    from nc_ocr_flow.ocr_models import OcrBlock, OcrResult
    fake_result = ProcessResult(
        output_pdf=str(fake_out),
        engine_used="google",
        page_results=[OcrResult(
            blocks=[OcrBlock(bbox=(0, 0, 10, 10), text="hi",
                             confidence=0.9, label="text")],
            page_width=200, page_height=200,
        )],
        tess_pages=[],
        vlm_pages=[0],
    )
    monkeypatch.setattr(ws, "process_pdf", lambda *a, **k: fake_result)

    res = ws._process_file(nc_path, node_id=42, engine="google", force=False)
    assert res.get("skipped") is not True, res
    assert calls["upload"] == [pdf_nc_path]
    assert calls["delete"] == [nc_path]
