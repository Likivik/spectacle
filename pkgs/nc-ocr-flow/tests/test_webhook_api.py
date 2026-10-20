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
import requests

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
    # C3: the PDF overwrite path uses atomic-replace; mock it as a
    # no-op so the test does not try to PUT to a real WebDAV server.
    monkeypatch.setattr(ws, "_webdav_replace_atomic", lambda *a, **k: None)
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
    # C3: the PDF overwrite path uses atomic-replace; mock it as a
    # no-op so the test does not try to PUT to a real WebDAV server.
    monkeypatch.setattr(ws, "_webdav_replace_atomic", lambda *a, **k: None)
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
    # C3: the PDF overwrite path uses atomic-replace; mock it as a
    # no-op so the test does not try to PUT to a real WebDAV server.
    monkeypatch.setattr(ws, "_webdav_replace_atomic", lambda *a, **k: None)
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

    monkeypatch.setattr(ws, "_list_dir_names", lambda _d: set())
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
    """Tesseract writes the layer via ocrmypdf; the gate (B4 fix) checks
    the produced PDF for a non-empty text layer instead of counting
    blocks across ``page_results=[]`` (which would always be zero for
    tesseract).

    The PDF used here is what a *successful* ocrmypdf run would leave:
    one page with extractable text. The gate must pass and the file
    must reach upload+stamp exactly once.
    """
    pdf = tmp_path / "tess.pdf"
    _build_pdf(pdf, with_text=True)

    calls = {"upload": [], "replace": [], "stamp": []}

    monkeypatch.setattr(
        ws, "_webdav_download",
        lambda nc, dest: __import__("shutil").copy2(pdf, dest),
    )
    monkeypatch.setattr(
        ws, "_webdav_upload",
        lambda nc, dest, *a, **k: calls["upload"].append((nc, str(dest))),
    )
    # C3: the PDF overwrite path goes through
    # ``_webdav_replace_atomic`` (sibling temp PUT + WebDAV MOVE). The
    # test is about whether the worker reaches the upload step at
    # all, so we mock the atomic helper too and assert it ran
    # exactly once with the expected nc path.
    monkeypatch.setattr(
        ws, "_webdav_replace_atomic",
        lambda nc, dest, *a, **k: calls["replace"].append((nc, str(dest))),
    )
    monkeypatch.setattr(
        ws, "_stamp_metadata",
        lambda *a, **k: calls["stamp"].append(a),
    )

    def fake_proc_tess(pdf_path, engine=None):
        # Tesseract's actual ProcessResult shape: page_results=[],
        # tess_pages=[...]. The text-layer gate (B4) opens
        # ``result.output_pdf`` and reads non-whitespace chars instead
        # of counting blocks across page_results=[]. The PDF at
        # ``pdf_path`` here carries text (built with with_text=True),
        # so the gate passes.
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
        # No raise expected — the tesseract text-layer gate passes for
        # a PDF with real text on it.
        res = ws._process_file(
            "/likivik/files/tess.pdf", node_id=8,
            engine="tesseract", force=False,
        )

    assert res.get("skipped") is not True
    # Upload happens from the tempdir inside _process_file, not tmp_path;
    # verify the nc-side path matches and exactly one upload + one stamp ran.
    # C3: the overwrite goes through _webdav_replace_atomic, not
    # _webdav_upload, so we assert on calls["replace"].
    assert len(calls["replace"]) == 1
    nc_uploaded, _dest = calls["replace"][0]
    assert nc_uploaded == "/likivik/files/tess.pdf"
    assert len(calls["stamp"]) == 1, "tesseract success must stamp"


def test_process_file_tesseract_empty_text_layer_raises(monkeypatch, tmp_path):
    """B4: a tesseract output PDF with NO text layer (or with one below
    MIN_TEXT_CHARS_PER_PAGE/page) must raise so the worker records
    ``status=error`` and the file is left UN-stamped and UN-uploaded.

    Pre-fix, an empty ocrmypdf result was silently accepted as
    ``done`` and overwritten the user's original — indistinguishable
    from success. The new text-layer gate prevents that.
    """
    pdf = tmp_path / "tess_blank.pdf"
    _build_pdf(pdf, with_text=False)  # blank page

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
        with pytest.raises(RuntimeError, match="empty/garbled text layer"):
            ws._process_file(
                "/likivik/files/tess_blank.pdf", node_id=9,
                engine="tesseract", force=False,
            )

    assert calls["upload"] == [], (
        "blank tesseract output must NOT be uploaded over the original"
    )
    assert calls["stamp"] == [], (
        "blank tesseract output must NOT be stamped as done"
    )


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

def test_image_branch_uses_next_free_name_on_collision(monkeypatch, tmp_path):
    """The image branch must NOT silently replace an existing PDF with
    the freshly-OCR'd image-to-PDF. If the target path is taken, it
    uploads as "name (1).pdf" instead — the user asked for an OCR of
    this image, not for a decision about somebody else's existing PDF.
    """
    # Source: a real image on disk (we use the existing _image_to_pdf
    # path to write an actual PDF); Target: a pre-existing PDF on NC.
    from PIL import Image

    img_path = tmp_path / "Work" / "photo.jpg"
    img_path.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), color=(255, 0, 0)).save(img_path)
    nc_path = f"/{ws.NC_USER}/files/Work/photo.jpg"
    pdf_nc_path = f"/{ws.NC_USER}/files/Work/photo.pdf"

    # photo.pdf is taken; photo(1).pdf is free.
    monkeypatch.setattr(ws, "_list_dir_names", lambda d: {"photo.pdf"})

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
    assert res.get("skipped") is not True, res
    # Uploaded to the next free name; the pre-existing photo.pdf is untouched.
    assert calls["upload"] == [f"/{ws.NC_USER}/files/Work/photo(1).pdf"], calls
    assert calls["delete"] == [nc_path], calls


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
    monkeypatch.setattr(ws, "_list_dir_names", lambda _d: set())

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


# --- B1: cost calc honours free tier ----------------------------------------

def test_vision_summary_cost_subtracts_free_units(monkeypatch):
    """B1: a 500-page run is below the 1000-page free tier → $0.00.

    Pre-fix the cost was ``pages * VISION_USD_PER_1000 / 1000`` which
    ignores the free tier entirely (500 pages → $0.75). Post-fix it's
    ``max(0, pages - VISION_FREE_UNITS) * VISION_USD_PER_1000 / 1000``
    so 500 pages round to $0.00 and 1500 pages round to $0.75 (one
    paid batch of 500).
    """
    # Avoid any real settings round-trips; provide only the keys the
    # summary actually consults.
    monkeypatch.setattr(ws.jobstore, "usage_month",
                        lambda *a, **k: {"jobs": 1, "pages": 500})
    monkeypatch.setattr(ws.jobstore, "settings_all", lambda: {})
    s = ws._vision_summary()
    assert s["cost_usd"] == 0.0
    assert s["pages_month"] == 500
    assert s["free_left"] == ws.VISION_FREE_UNITS - 500

    # 1500 pages: 500 paid pages, still under one Vision-paid dollar.
    monkeypatch.setattr(ws.jobstore, "usage_month",
                        lambda *a, **k: {"jobs": 1, "pages": 1500})
    s = ws._vision_summary()
    assert s["cost_usd"] == round(
        500 * ws.VISION_USD_PER_1000 / 1000, 4
    ), s


# --- B5: /webhook malformed body returns 400 --------------------------------

def test_webhook_malformed_json_returns_400(client):
    """B5: a non-JSON body must be 400, not 500. A 500 used to make
    Nextcloud's dispatcher retry-storm a healthy backend.

    Sending ``text/plain`` via TestClient: the handler must catch the
    JSON-decode error and return 400 with a clear detail.
    """
    r = client.post(
        "/webhook",
        headers={**h(), "Content-Type": "text/plain"},
        content=b"this is not json",
    )
    assert r.status_code == 400, r.text
    assert "invalid JSON body" in r.json().get("detail", "")


def test_webhook_empty_json_returns_400(client):
    """Empty body is also a 400 (still not parseable)."""
    r = client.post("/webhook", headers=h(), content=b"")
    assert r.status_code == 400


# --- B6: image-branch collision check runs BEFORE the OCR call --------------

def test_image_branch_collision_skips_before_process_pdf(monkeypatch, tmp_path):
    """B6: when a target PDF already exists, the image branch must
    refuse the work BEFORE calling process_pdf — saving a paid Vision
    round-trip and the GCS upload.

    Pre-fix the collision check happened AFTER process_pdf, so a
    refused conversion had already billed the user for one Vision
    call. This test asserts ``process_pdf`` is NOT called when the
    PROPFIND finds an existing PDF at the target path.
    """
    from PIL import Image

    img_path = tmp_path / "photo.jpg"
    Image.new("RGB", (64, 64), color=(255, 0, 0)).save(img_path)
    nc_path = f"/{ws.NC_USER}/files/photo.jpg"

    # PROPFIND says the target PDF exists (size > 0).
    monkeypatch.setattr(ws, "_propfind_size_etag",
                        lambda _p: (1024, '"abc"'))
    # Spy on process_pdf; it must NOT be called.
    calls = {"process_pdf": 0}

    def _spy_process_pdf(*a, **k):
        calls["process_pdf"] += 1
        raise AssertionError(
            "process_pdf must not run when the target PDF already exists"
        )

    def _fake_download(_nc_path, dest):
        import shutil
        shutil.copyfile(str(img_path), str(dest))

    monkeypatch.setattr(ws, "_webdav_download", _fake_download)
    monkeypatch.setattr(ws, "_webdav_upload",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("upload must not run")))
    monkeypatch.setattr(ws, "_webdav_delete",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("delete must not run")))
    monkeypatch.setattr(ws, "process_pdf", _spy_process_pdf)

    class _Cls:
        is_document = True
        reason = "doc"
    monkeypatch.setattr(ws, "classify", lambda _p: _Cls())

    res = ws._process_file(nc_path, node_id=42, engine="google", force=False)
    assert res.get("skipped") is True, res
    assert res["reason"] == ws.SKIP_REASON_PDF_EXISTS, res
    assert calls["process_pdf"] == 0, (
        "collision check must run BEFORE process_pdf to avoid a "
        "paid Vision call"
    )


# --- B7: counter reconciliation --------------------------------------------

def test_stats_includes_gone_and_errors_attempts(client, monkeypatch):
    """B7: /stats payload states its contract explicitly — ``errors``
    counts unique failed *paths*, ``gone`` counts unique paths whose
    file vanished from NC, and ``errors_attempts`` mirrors /jobs/stats
    so the two endpoints can never be read as contradictory.
    """
    # Seed the files table directly (one of each kind) — the production
    # bug was that ``errors`` counted paths whose files no longer
    # exist; we model exactly that.
    ws.jobstore.file_put({"path": "/likivik/files/gone.pdf",
                          "status": "gone", "reason": "file_removed",
                          "engine": None, "node_id": 0,
                          "size": None, "etag": None,
                          "mtime": None, "last_seen": None})
    ws.jobstore.file_put({"path": "/likivik/files/real_err.pdf",
                          "status": "error", "reason": None,
                          "engine": "google", "node_id": 0,
                          "size": None, "etag": None,
                          "mtime": None, "last_seen": None})

    r = client.get("/stats", headers=h())
    assert r.status_code == 200
    d = r.json()
    # The keys the bug report calls out must be present.
    for key in ("errors", "gone", "errors_attempts"):
        assert key in d, f"{key} missing from /stats payload"
    # gone.pdf is counted in ``gone``, NOT in ``errors``.
    assert d["gone"] == 1, d
    assert d["errors"] == 1, d
    assert d["errors_attempts"] >= 0  # jobs-table mirror; may be 0 here


def test_run_job_marks_404_as_gone(monkeypatch):
    """B7 (cont): when the WebDAV GET returns 404 (file deleted from
    Nextcloud between webhook and processing) the worker must record
    status='gone' with reason='file_removed', NOT status='error'.

    Pre-fix the file was permanently marked error, polluting the
    ``errors`` counter with paths that no longer exist on NC.
    """
    import requests as _req

    # Build a fake HTTPError with response.status_code == 404.
    fake_resp = type("R", (), {"status_code": 404})()
    err = _req.HTTPError("404 Not Found", response=fake_resp)

    job = {
        "id": 1, "path": "/likivik/files/missing.pdf",
        "nc_path": "/likivik/files/missing.pdf", "node_id": 42,
        "engine": "google", "force": False, "status": "running",
        "started": None, "created": None, "finished": None,
        "result": None, "error": None, "reason": None,
    }

    def _boom(*a, **k):
        raise err

    monkeypatch.setattr(ws, "_process_file", _boom)
    ws._run_job(job)
    assert job["status"] == "gone", job
    assert job["reason"] == "file_removed", job


def test_run_job_other_http_error_remains_error(monkeypatch):
    """B7 (counter-test): a 5xx or other HTTPError stays ``error`` —
    the gone-state is only for 404."""
    import requests as _req

    fake_resp = type("R", (), {"status_code": 503})()
    err = _req.HTTPError("503 Service Unavailable", response=fake_resp)
    job = {
        "id": 2, "path": "/likivik/files/x.pdf",
        "nc_path": "/likivik/files/x.pdf", "node_id": 0,
        "engine": "google", "force": False, "status": "running",
        "started": None, "created": None, "finished": None,
        "result": None, "error": None, "reason": None,
    }
    monkeypatch.setattr(ws, "_process_file", lambda *a, **k: (_ for _ in ()).throw(err))
    ws._run_job(job)
    assert job["status"] == "error", job


# --- B8: _enqueue is atomic for the same path -------------------------------

def test_enqueue_same_path_no_duplicate_when_inflight(monkeypatch):
    """B8: when a path is already in flight, a second _enqueue for the
    same path must NOT create a duplicate jobs row.

    This test stubs ``_run_job`` to a no-op so the worker can claim
    the job (which moves the row from ``queued`` to ``running``) but
    does not actually process it. That preserves the in-flight state
    long enough to make the assertion deterministic. The DB is
    reset at the start so leftover jobs from earlier tests don't
    race the new enqueue.
    """
    monkeypatch.setattr(ws, "_run_job", lambda _job: None)
    ws.jobstore._reset_for_tests()

    nc_path = "/likivik/files/a.pdf"
    job1 = ws._enqueue(nc_path, node_id=42)
    assert job1.get("id") is not None

    # Wait briefly for the worker to claim the first job (queued →
    # running).
    deadline = __import__("time").time() + 5.0
    while __import__("time").time() < deadline:
        if ws.jobstore.stats().get("running", 0) >= 1:
            break
        __import__("time").sleep(0.05)
    assert ws.jobstore.stats().get("running", 0) >= 1, (
        "worker should have claimed job1 by now"
    )

    inflight_before = (
        ws.jobstore.stats().get("queued", 0)
        + ws.jobstore.stats().get("running", 0)
    )
    total_before = ws.jobstore.stats().get("total", 0)

    # Second enqueue for the SAME path. With the B8 fix, the
    # per-path lock + _path_in_flight check sees files.status='queued'
    # and short-circuits before record_enqueue.
    ws._enqueue(nc_path, node_id=42)
    inflight_after = (
        ws.jobstore.stats().get("queued", 0)
        + ws.jobstore.stats().get("running", 0)
    )
    total_after = ws.jobstore.stats().get("total", 0)

    assert inflight_after == inflight_before, (
        f"second _enqueue must NOT insert a duplicate jobs row: "
        f"in-flight went from {inflight_before} to {inflight_after}"
    )
    assert total_after == total_before, (
        f"second _enqueue must NOT add a row: total went from "
        f"{total_before} to {total_after}"
    )


def test_enqueue_force_ignores_inflight_check(monkeypatch):
    """B1 audit: ``force=True`` does NOT bypass the in-flight gate.

    Before B1, ``/rescan?force=true`` could spawn a duplicate jobs
    row for a file the worker was already mid-flight on, billing
    Vision twice for the same file. The fix holds a per-path
    enqueue lock and re-checks ``in_flight_job_for_path`` once
    inside it; if a job is already queued or running for the
    path we return that existing job with ``status='already_running'``
    regardless of the caller's ``force`` bit. ``force`` still
    applies to the downstream born-digital / stamp / TTL guards
    in ``_process_file`` — only the in-flight gate is unconditional.

    Production shape this guards: the Nextcloud app's "Re-OCR
    anyway" is double-clicked, or ``/rescan`` races a /webhook
    handler. The previous behaviour inserted two rows and ran
    Vision twice; the B1 fix collapses both to one row.
    """
    monkeypatch.setattr(ws, "_run_job", lambda _job: None)
    ws.jobstore._reset_for_tests()
    nc_path = "/likivik/files/force.pdf"
    ws._enqueue(nc_path, node_id=10)
    # Wait for the worker to claim the first job (running).
    deadline = __import__("time").time() + 5.0
    while __import__("time").time() < deadline:
        if ws.jobstore.stats().get("running", 0) >= 1:
            break
        __import__("time").sleep(0.05)

    jobs_before = ws.jobstore.stats().get("total", 0)
    second = ws._enqueue(nc_path, node_id=10, force=True)
    jobs_after = ws.jobstore.stats().get("total", 0)
    # B1: force=True does NOT bypass the in-flight gate.
    assert jobs_after == jobs_before, (
        f"force=True must collapse to the existing in-flight job, "
        f"got {jobs_after - jobs_before} new rows (status={second.get('status')})"
    )
    assert second.get("status") == "already_running", (
        f"second force=True enqueue must report 'already_running', "
        f"got {second.get('status')!r}"
    )


# --- B9: PROPFIND parser accepts any namespace prefix -----------------------

def test_scan_all_accepts_non_d_prefix(monkeypatch, client):
    """B9: a PROPFIND body that uses ``D:`` (capital D) instead of
    ``d:`` must still produce enqueues — pre-fix the regex hard-coded
    ``<d:href>`` and silently dropped every entry."""
    fake_xml = (
        '<?xml version="1.0"?><D:multistatus xmlns:D="DAV:">'
        f"<D:response><D:href>/remote.php/dav/files/likivik/Documents/x.pdf</D:href>"
        "<D:propstat><D:prop><D:resourcetype/></D:prop></D:propstat>"
        "</D:response>"
        "<D:response><D:href>/remote.php/dav/files/likivik/Documents/y.png</D:href>"
        "<D:propstat><D:prop><D:resourcetype/></D:prop></D:propstat>"
        "</D:response>"
        "</D:multistatus>"
    )

    class _Resp:
        status_code = 207
        text = fake_xml
        def raise_for_status(self): pass

    monkeypatch.setattr(
        ws.requests, "request", lambda *a, **k: _Resp(),
    )
    monkeypatch.setattr(ws, "_path_in_flight", lambda _p: False)

    r = client.post("/scan-all", json={"folder": "Documents"}, headers=h())
    assert r.status_code == 200
    d = r.json()
    # Both x.pdf and y.png must be enqueued; pre-fix the regex matched
    # zero entries because the prefix was ``D:`` not ``d:``.
    assert d["enqueued"] == 2, d


def test_scan_all_accepts_no_prefix(monkeypatch, client):
    """B9 (edge): a response with no namespace prefix at all must
    still be parsed. Some Sabre/DAV setups emit unprefixed XML."""
    fake_xml = (
        '<?xml version="1.0"?><multistatus>'
        f"<response><href>/remote.php/dav/files/likivik/Documents/z.pdf</href>"
        "<propstat><prop><resourcetype/></prop></propstat>"
        "</response>"
        "</multistatus>"
    )

    class _Resp:
        status_code = 207
        text = fake_xml
        def raise_for_status(self): pass

    monkeypatch.setattr(
        ws.requests, "request", lambda *a, **k: _Resp(),
    )
    monkeypatch.setattr(ws, "_path_in_flight", lambda _p: False)

    r = client.post("/scan-all", json={"folder": "Documents"}, headers=h())
    assert r.status_code == 200
    d = r.json()
    assert d["enqueued"] == 1, d


# --- B10: _PROCESSED_TTL is configurable ------------------------------------

def test_processed_ttl_honours_settings_db(monkeypatch):
    """B10: an operator can change ``processed_ttl`` via the settings
    store and the next claim_job call uses the new value, with no
    restart required.
    """
    # Default value (no env, no DB override).
    monkeypatch.delenv("NC_OCR_PROCESSED_TTL", raising=False)
    ws.jobstore.setting_delete("NC_OCR_PROCESSED_TTL")
    assert ws._processed_ttl_seconds() == float(ws._DEFAULT_PROCESSED_TTL)

    # Setting via the DB row.
    ws.jobstore.setting_put("NC_OCR_PROCESSED_TTL", "12")
    assert ws._processed_ttl_seconds() == 12.0

    # Bad value falls back to default.
    ws.jobstore.setting_put("NC_OCR_PROCESSED_TTL", "not-a-number")
    assert ws._processed_ttl_seconds() == float(ws._DEFAULT_PROCESSED_TTL)

    # Cleanup so other tests aren't affected.
    ws.jobstore.setting_delete("NC_OCR_PROCESSED_TTL")


def test_processed_ttl_honours_env(monkeypatch):
    """B10 (env precedence): env wins over default but the DB row
    wins over env (per the spec's precedence table).
    """
    ws.jobstore.setting_delete("NC_OCR_PROCESSED_TTL")
    monkeypatch.setenv("NC_OCR_PROCESSED_TTL", "7")
    assert ws._processed_ttl_seconds() == 7.0

    ws.jobstore.setting_put("NC_OCR_PROCESSED_TTL", "42")
    # DB overrides env.
    assert ws._processed_ttl_seconds() == 42.0

    ws.jobstore.setting_delete("NC_OCR_PROCESSED_TTL")
    monkeypatch.delenv("NC_OCR_PROCESSED_TTL", raising=False)


def test_processed_ttl_setting_panel_zero_accepted(client):
    """B10: 0 is valid for the TTL setting (\"never dedup\") and must
    pass the floor check in ``/settings``."""
    r = client.post("/settings", json={"processed_ttl": 0}, headers=h())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["settings"]["processed_ttl"] == 0


def test_processed_ttl_setting_panel_floor_enforced(client):
    """B10: a negative value is rejected with 422; positive values
    round-trip cleanly."""
    r = client.post("/settings", json={"processed_ttl": -1}, headers=h())
    assert r.status_code == 422
    r = client.post("/settings", json={"processed_ttl": 600}, headers=h())
    assert r.status_code == 200
    assert r.json()["settings"]["processed_ttl"] == 600


# --- B3: _webdav_delete retries on 5xx --------------------------------------

def test_webdav_delete_retries_on_5xx(monkeypatch):
    """B3: when the WebDAV DELETE returns a 5xx, ``_webdav_delete``
    must retry — pre-fix ``raise_for_status`` ran OUTSIDE the retried
    closure so a 5xx on the final attempt escaped unretried and left
    both the source image and the new PDF in Nextcloud with the job
    marked ``error``.
    """
    import requests as _req

    responses = iter([
        _make_resp(503),
        _make_resp(502),
        _make_resp(204),
    ])
    sleeps: list[float] = []

    monkeypatch.setattr(ws.requests, "delete",
                        lambda *a, **k: next(responses))
    monkeypatch.setattr(ws.time, "sleep", lambda s: sleeps.append(s))

    # The retry helper backs off; we patch its base delay so the
    # test stays fast.
    ws._RETRY_BASE_DELAY = 0.0
    ws._webdav_delete("/likivik/files/x.pdf")
    # Two retries between three attempts → two sleeps recorded.
    assert len(sleeps) == 2, sleeps


def _make_resp(status_code):
    """Build a minimal ``requests.Response`` for the B3 test."""
    import requests as _req
    r = _req.Response()
    r.status_code = status_code
    return r


# --- B2: _vision_quota_once picks the dimension matching the engine region --

def test_pick_quota_dimension_matches_engine_region():
    """B2: the helper picks the dimension whose ``location`` matches
    the engine's NC_OCR_GOOGLE_LOCATION. Pre-fix the production code
    read ``dims[0]`` of the API response — whichever region came
    back first — and reported the wrong quota in /stats.
    """
    dims = [
        {"dimensions": {"location": "asia-east1"},
         "details": {"value": "100"}},
        {"dimensions": {"location": "us"},
         "details": {"value": "1800"}},
        {"dimensions": {"location": "eu"},
         "details": {"value": "900"}},
    ]
    # US default: must skip asia-east1 and eu, pick us.
    m = ws._pick_quota_dimension(dims, "US")
    assert m is not None
    assert m["details"]["value"] == "1800"

    # Lower-case on either side still matches (case-insensitive).
    m = ws._pick_quota_dimension(dims, "eu")
    assert m["details"]["value"] == "900"

    # Empty falls back to US.
    m = ws._pick_quota_dimension(dims, "")
    assert m["details"]["value"] == "1800"

    # No match → None; caller falls back to a conservative 1800
    # with a WARNING.
    m = ws._pick_quota_dimension(dims, "moon")
    assert m is None


def test_pick_quota_dimension_global_wildcard():
    """B2 (edge): NC_OCR_GOOGLE_LOCATION=GLOBAL accepts the first
    non-empty dimension (the wildcard bucket)."""
    dims = [
        {"dimensions": {"location": "eu"}, "details": {"value": "900"}},
    ]
    m = ws._pick_quota_dimension(dims, "GLOBAL")
    assert m is not None and m["details"]["value"] == "900"

    # Case-insensitive wildcard too.
    m = ws._pick_quota_dimension(dims, "global")
    assert m is not None and m["details"]["value"] == "900"


# ===========================================================================
# ocrfix2-srv-20261016 batch — robustness fixes
#   C1 multi-user safety, C2 image-delete failure, C3 atomic overwrite,
#   C5 stale-row reconcile, C6 bounded retry
# ===========================================================================


# --- C1: Multi-user safety ------------------------------------------------

def test_c1_path_user_extracts_nc_user():
    """C1 helper: ``/_<user>/files/<rel>`` → ``<user>``.

    The webhook and ``/scan-all`` both key their foreign-user check
    off :func:`webhook_server._path_user`; the rest of the boundary
    logic is a single ``!=`` against :data:`webhook_server.NC_USER`.
    A wrong extractor here would silently accept foreign-user
    paths and re-create the 401-storm the fix is meant to stop.
    """
    assert ws._path_user("/likivik/files/Documents/a.pdf") == "likivik"
    assert ws._path_user("/admin/files/Photos/img.jpg") == "admin"
    # Edge: empty / weird input.
    assert ws._path_user("") == ""
    assert ws._path_user("/") == ""


def test_c1_is_foreign_user_only_when_user_mismatches(monkeypatch):
    """C1: ``_is_foreign_user`` returns True ONLY for a user segment
    that does not match :data:`NC_USER`. The same user → False;
    a different user → True; an unparseable path → False (let
    downstream error out — never silently drop a real job).
    """
    monkeypatch.setattr(ws, "NC_USER", "likivik")
    assert ws._is_foreign_user("/likivik/files/a.pdf") is False
    assert ws._is_foreign_user("/admin/files/a.pdf") is True
    assert ws._is_foreign_user("/stranger/files/a.pdf") is True
    # Unparseable: no user segment → not "foreign" (let the URL
    # builder fall back to NC_USER and the existing error path
    # produce its usual error).
    assert ws._is_foreign_user("") is False
    assert ws._is_foreign_user("/") is False


def test_c1_webhook_foreign_user_records_and_returns_200(client):
    """C1: ``/webhook`` for a path owned by a different NC user
    must NOT touch WebDAV. Pre-fix this would 401, retry 3×, and
    record ``status=error`` for a file the service user can
    never reach. Post-fix it logs a warning, records the file
    with ``reason='foreign_user'``, and returns 200 so Nextcloud
    does not retry.
    """
    # The client fixture already stubbed ``_process_file``; we assert
    # it is NEVER called for a foreign-user path.
    nc_path = "/admin/files/Documents/secret.pdf"
    r = client.post(
        "/webhook",
        headers=h(),
        json={
            "event": {
                "class":
                    "OCP\\Files\\Events\\Node\\NodeCreatedEvent",
                "node": {"id": 999, "path": nc_path},
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ignored"
    assert body["reason"] == ws.REASON_FOREIGN_USER

    # The file row must exist in the per-file index with
    # ``reason='foreign_user'`` so the panel can show the operator
    # the real cause instead of an opaque ``error``.
    rec = ws.jobstore.file_get(nc_path)
    assert rec is not None
    assert rec["reason"] == ws.REASON_FOREIGN_USER
    assert rec["status"] == "skipped"


def test_c1_rescan_foreign_user_rejected_422(client, monkeypatch):
    """C1: ``/rescan`` is an operator action, not a Nextcloud
    retry. A foreign-user rescan returns 422 with a clear detail
    so the panel surfaces the refusal rather than queuing a job
    that will 401 and end as ``error``.
    """
    # NC_USER stays as the test default ("likivik"). A rescan for
    # a different user must be rejected.
    r = client.post(
        "/rescan",
        headers=h(),
        json={"path": "/admin/files/Documents/secret.pdf",
              "node_id": 0, "engine": "auto", "force": False},
    )
    assert r.status_code == 422, r.text
    assert "foreign" in r.json()["detail"].lower()


# --- C2: Image branch delete failure --------------------------------------

def test_c2_image_branch_delete_failed_records_reason(monkeypatch, tmp_path):
    """C2: when the image→PDF branch uploads the new PDF
    successfully but the WebDAV DELETE of the source image fails,
    the worker must:

      1. NOT mark the job ``status=error`` (the OCR work and the
         upload succeeded; only cleanup failed);
      2. propagate ``result.reason='image_delete_failed'`` to
         ``job['reason']`` so the panel shows the real cause;
      3. leave both files in place (no compensating delete or
         upload).
    """
    # Build a tiny placeholder PDF for the upload step.
    from pymupdf import Document
    out = tmp_path / "img.pdf.ocr.pdf"
    doc = Document()
    doc.new_page()
    doc.save(str(out))
    doc.close()

    # Build a fake process_pdf result that the image branch will
    # consume — page_results is non-empty so the
    # ``_assert_ocr_produced_blocks`` gate passes, vlm_pages=[0]
    # (single page), engine_used set.
    from nc_ocr_flow.ocr import ProcessResult
    from nc_ocr_flow.ocr_models import OcrBlock, OcrResult

    def fake_proc(pdf_path, engine=None):
        return ProcessResult(
            output_pdf=str(out),
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
            vlm_pages=[0],
        )

    def fake_classify(_path):
        return {"needs_ocr": True, "pdf_type": "scanned",
                "confidence": 0.9, "has_encoding_issues": False}

    # The image branch uploads the new PDF, then DELETEs the
    # source image. Make upload succeed and delete blow up.
    upload_calls: list[str] = []
    delete_calls: list[str] = []

    def fake_upload(nc_path, src):
        upload_calls.append(nc_path)

    def fake_delete(nc_path):
        delete_calls.append(nc_path)
        raise requests.ConnectionError(
            "sabre conn reset (simulated)"
        )

    # The collision check before the upload does a PROPFIND on
    # the new .pdf path. Make it return None so the upload
    # proceeds (no existing PDF in the way).
    def fake_propfind(*a, **k):
        return (None, None)
    monkeypatch.setattr(ws, "_propfind_size_etag", fake_propfind)
    monkeypatch.setattr(ws, "_list_dir_names", lambda _d: set())
    # The image classifier must say "this is a document image"
    # or the branch returns early as "not a document".
    monkeypatch.setattr(ws, "classify",
                        lambda _p: SimpleNamespace(
                            is_document=True, reason="doc"))
    monkeypatch.setattr(ws, "_image_to_pdf",
                        lambda p: str(out))
    # Stub the WebDAV download so the test does not try to
    # actually GET the file. Copy a tiny placeholder so the
    # classifier is happy.
    placeholder = tmp_path / "downloaded.jpg"
    placeholder.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(ws, "_webdav_download",
                        lambda nc, dest: __import__("shutil").copy2(
                            str(placeholder), str(dest)))
    monkeypatch.setattr(ws, "_webdav_upload", fake_upload)
    monkeypatch.setattr(ws, "_webdav_delete", fake_delete)
    monkeypatch.setattr(ws, "_stamp_metadata", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_webdav_stat", lambda *a, **k: (None, None))

    with patch.object(ws, "process_pdf", side_effect=fake_proc), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        result = ws._process_file(
            "/likivik/files/photo.jpg", node_id=1,
            engine="google", force=False,
        )

    # Upload ran; delete was attempted and raised (caught).
    assert len(upload_calls) == 1, upload_calls
    assert len(delete_calls) == 1, delete_calls

    # The result carries the new reason; the worker propagates it
    # to job["reason"] (verified end-to-end below).
    assert result.get("reason") == "image_delete_failed"
    assert result.get("delete_error")  # populated

    # End-to-end: a job for this path, run via the worker path,
    # records ``status='done'`` AND ``reason='image_delete_failed'``
    # (the reason is what tells the operator the cleanup failed).
    ws.jobstore._reset_for_tests()
    new_id = ws.jobstore.record_enqueue({
        "path": "/likivik/files/photo.jpg",
        "nc_path": "/likivik/files/photo.jpg",
        "node_id": 1,
        "engine": "google",
        "force": False,
        "status": "queued",
        "created": __import__("time").time(),
    })
    job = ws.jobstore.get(new_id)
    job["started"] = __import__("time").time()
    # Re-apply the mocks in the new test scope (the ``monkeypatch``
    # setattr from above is still active for the whole test
    # function; we just need to re-enter the with-block so the
    # ``process_pdf`` patch is active when ``_run_job`` calls
    # ``_process_file``).
    with patch.object(ws, "process_pdf", side_effect=fake_proc), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        ws._run_job(job)
    assert job["status"] == "done"
    assert job["reason"] == "image_delete_failed"
    # The job's ``error`` is also populated so the panel can show
    # the underlying WebDAV exception in the history row.
    assert "image_delete_failed" in (job.get("error") or "")


# --- C3: Atomic PDF overwrite ---------------------------------------------

def test_c3_webdav_replace_atomic_calls_move_with_overwrite(monkeypatch):
    """C3: ``_webdav_replace_atomic`` must PUT to a sibling temp
    path, MOVE with ``Destination`` + ``Overwrite: T`` headers,
    and clean up the temp on success. Pre-fix the PDF overwrite
    path did a plain PUT over the user's file, leaving a
    truncated PDF on partial failure.
    """
    # Build a tiny local file to upload.
    import tempfile as _tempfile
    src_fd, src_path = _tempfile.mkstemp(suffix=".pdf")
    os.close(src_fd)
    Path(src_path).write_bytes(b"%PDF-1.4\n%fake-ocr-output\n")

    seen = {"put": [], "move": [], "delete": []}

    class _Resp:
        def __init__(self, code=204):
            self.status_code = code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    def fake_put(url, *, data, auth, headers, timeout):
        seen["put"].append((url, headers))
        return _Resp(201)

    def fake_request(method, url, *, auth, headers, timeout):
        if method == "MOVE":
            seen["move"].append((url, headers))
        elif method == "DELETE":
            seen["delete"].append(url)
        return _Resp(204)

    monkeypatch.setattr(ws.requests, "put", fake_put)
    monkeypatch.setattr(ws.requests, "request", fake_request)
    # Speed up the retry helper.
    monkeypatch.setattr(ws, "_RETRY_BASE_DELAY", 0.0)

    ws._webdav_replace_atomic(
        "/likivik/files/Documents/foo.pdf", Path(src_path),
    )

    # 1) PUT went to a sibling .ocr-tmp-<rand> path (NOT the
    #    original — that's the whole point of C3).
    assert len(seen["put"]) == 1
    put_url, put_headers = seen["put"][0]
    assert put_url != ws._webdav_url("/likivik/files/Documents/foo.pdf")
    assert ".ocr-tmp-" in put_url
    # 2) MOVE went to the ORIGINAL WebDAV URL with
    #    ``Destination`` and ``Overwrite: T`` headers — sabre
    #    treats that as an atomic replace.
    assert len(seen["move"]) == 1
    move_url, move_headers = seen["move"][0]
    assert move_url == put_url
    target_url = ws._webdav_url("/likivik/files/Documents/foo.pdf")
    assert move_headers.get("Destination") == target_url
    assert move_headers.get("Overwrite") == "T"
    # 3) No cleanup DELETE on success (cleanup only on failure).
    assert seen["delete"] == []


def test_c3_webdav_replace_atomic_cleans_up_on_move_failure(monkeypatch):
    """C3: when the MOVE fails after a successful PUT, the
    helper must DELETE the temp object so a future attempt does
    not collide with a leaked sibling. Without the cleanup the
    retry would 409 on the new MOVE because the temp path is
    still occupied.
    """
    src_fd, src_path = tempfile.mkstemp(suffix=".pdf")
    os.close(src_fd)
    Path(src_path).write_bytes(b"%PDF-1.4\n")

    seen: list[tuple[str, str]] = []

    class _Resp:
        def __init__(self, code, body=""):
            self.status_code = code
            self.text = body

        def raise_for_status(self):
            if self.status_code >= 400:
                err = requests.HTTPError(f"http {self.status_code}")
                err.response = self
                raise err

    def fake_put(url, *, data, auth, headers, timeout):
        return _Resp(201)

    def fake_request(method, url, *, auth, headers, timeout):
        seen.append((method, url))
        if method == "MOVE":
            # All three attempts fail with 503 — the helper's
            # internal retry exhausts.
            return _Resp(503, "transient")
        return _Resp(404)

    # The cleanup DELETE uses ``requests.delete`` directly (not
    # ``requests.request``), so mock it explicitly.
    def fake_delete(url, *, auth, timeout):
        seen.append(("DELETE", url))
        return _Resp(204)

    monkeypatch.setattr(ws.requests, "put", fake_put)
    monkeypatch.setattr(ws.requests, "request", fake_request)
    monkeypatch.setattr(ws.requests, "delete", fake_delete)
    monkeypatch.setattr(ws, "_RETRY_BASE_DELAY", 0.0)

    with pytest.raises(requests.HTTPError):
        ws._webdav_replace_atomic(
            "/likivik/files/Documents/foo.pdf", Path(src_path),
        )

    methods = [m for m, _ in seen]
    assert methods.count("MOVE") == 3, methods
    assert methods.count("DELETE") == 1, methods


# --- C4: /jobs/{id} after pruning -----------------------------------------

def test_c4_jobs_pruned_404_has_useful_detail(client, monkeypatch):
    """C4: a job id past the retention cap must 404, and the
    detail must tell the operator the row was pruned (not that
    the job never existed) and point at /stats + /states. The
    NC app uses these endpoints already, so the panel degrades
    gracefully.
    """
    # Force the retention cap to 2 rows so the next enqueue
    # prunes the first.
    monkeypatch.setattr(ws.jobstore, "_MAX_ROWS", 2)
    # Enqueue three jobs to push id=1 out of the table.
    for i in range(1, 4):
        ws.jobstore.record_enqueue({
            "path": f"/likivik/files/d-{i}.pdf",
            "nc_path": f"/likivik/files/d-{i}.pdf",
            "node_id": 1000 + i,
            "engine": "google",
            "force": False,
            "status": "queued",
            "created": 1.0 + i,
        })
    # Id=1 should now be pruned.
    r = client.get("/jobs/1", headers=h())
    assert r.status_code == 404, r.text
    detail = r.json()["detail"]
    assert "not found" in detail.lower()
    assert "prune" in detail.lower()
    assert "/stats" in detail
    assert "/states" in detail


# --- C5: Stale-row reconciler ---------------------------------------------

def test_c5_reconcile_stale_marks_404_rows_gone(monkeypatch):
    """C5: a row whose underlying file is gone (HEAD 404) must
    be flipped to ``status='gone'`` with ``reason='file_removed'``.
    Rows that still exist are left alone. Idempotent: a second
    pass finds no eligible rows.
    """
    # Seed the file index with a mix of states.
    ws.jobstore._reset_for_tests()
    for status, path in [
        ("error", "/likivik/files/__probe_1.pdf"),
        ("error", "/likivik/files/__probe_2.pdf"),
        ("error", "/likivik/files/real_doc.pdf"),
        ("queued", "/likivik/files/another_probe.pdf"),
        ("done", "/likivik/files/never_touched.pdf"),  # not in scope
    ]:
        ws.jobstore.file_put({
            "path": path, "status": status, "engine": None,
            "reason": "test", "node_id": 0, "finished": 1.0,
            "size": 100, "etag": "abc",
        })

    # HEAD returns 404 for the *probe* paths and 200 for the
    # real / done paths. We mock ``requests.request`` directly
    # because ``requests.head`` captures ``request`` at import
    # time and bypasses attribute lookup on the parent module,
    # so monkeypatching ``ws.requests.head`` doesn't intercept
    # the call from ``_webdav_exists``.
    def fake_request(method, url, **k):
        assert method.upper() == "HEAD"
        if "__probe" in url or "another_probe" in url:
            class R:
                status_code = 404
            return R()
        class R:
            status_code = 200
        return R()

    monkeypatch.setattr(ws.requests, "request", fake_request)

    # First pass: scope the query to the probe paths only so the
    # real_doc row does not show up in the test's pass-2
    # expectations. We confirm via file_get that real_doc was
    # left alone.
    out1 = ws.reconcile_stale_files(
        limit=50, max_propfind=50,
        statuses=["queued"],  # only probes are queued
    )
    assert out1["checked"] == 1   # one queued (another_probe)
    assert out1["marked_gone"] == 1
    assert out1["kept"] == 0

    # The 404 path is now 'gone'.
    rec = ws.jobstore.file_get("/likivik/files/another_probe.pdf")
    assert rec["status"] == "gone"
    assert rec["reason"] == "file_removed"

    # The still-existing error row is untouched (HEAD 200
    # implies the file is there). It will keep being eligible
    # for the next pass until the file actually disappears;
    # that's the correct behaviour — the reconciler is a sweeper,
    # not a one-shot cleaner.
    rec = ws.jobstore.file_get("/likivik/files/real_doc.pdf")
    assert rec["status"] == "error"

    # Second pass on the error rows: all three error rows are
    # still in the index (we never reconciled them in pass 1
    # because we scoped pass 1 to ``statuses=['queued']``). The
    # two probes HEAD-404 and are marked gone; ``real_doc``
    # HEAD-200 and is left alone.
    out3 = ws.reconcile_stale_files(
        limit=50, max_propfind=50, statuses=["error"],
    )
    assert out3["checked"] == 3
    assert out3["marked_gone"] == 2
    assert out3["kept"] == 1

    # Third pass on the error rows: only ``real_doc`` is left,
    # and HEAD still says 200, so the row stays as ``error``.
    out4 = ws.reconcile_stale_files(
        limit=50, max_propfind=50, statuses=["error"],
    )
    assert out4["checked"] == 1
    assert out4["marked_gone"] == 0
    assert out4["kept"] == 1


def test_c5_reconcile_endpoint_requires_secret(client):
    """C5: the ``/reconcile`` endpoint is gated on the webhook
    secret the same way every other operator action is."""
    r = client.post("/reconcile", json={})
    assert r.status_code == 401


def test_c5_reconcile_endpoint_runs_and_returns_counts(client, monkeypatch):
    """C5: ``POST /reconcile`` runs the bounded pass and returns
    its counts so an operator can invoke it on demand without
    restarting the service.
    """
    ws.jobstore._reset_for_tests()
    ws.jobstore.file_put({
        "path": "/likivik/files/stale.pdf", "status": "error",
        "engine": None, "reason": "old", "node_id": 0,
        "finished": 1.0, "size": 1, "etag": "x",
    })

    def fake_request(method, url, **k):
        assert method.upper() == "HEAD"
        class R:
            status_code = 404
        return R()
    monkeypatch.setattr(ws.requests, "request", fake_request)

    r = client.post(
        "/reconcile", headers=h(),
        json={"limit": 10, "max_propfind": 10, "statuses": ["error"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["marked_gone"] == 1
    assert body["checked"] == 1


# --- C6: Bounded automatic retry -----------------------------------------

def test_c6_is_transient_classifier():
    """C6: the transient classifier must mark 5xx, 408, 429,
    and transport errors as transient; 4xx other than 408/429
    and any other exception as permanent.
    """
    import requests as _req
    # 5xx → transient
    err_503 = _req.HTTPError("server error")
    err_503.response = type("R", (), {"status_code": 503})()
    assert ws._is_transient_failure(err_503, 503) is True
    err_500 = _req.HTTPError("server error")
    err_500.response = type("R", (), {"status_code": 500})()
    assert ws._is_transient_failure(err_500, 500) is True
    # 408/429 → transient
    err_408 = _req.HTTPError("timeout")
    err_408.response = type("R", (), {"status_code": 408})()
    assert ws._is_transient_failure(err_408, 408) is True
    err_429 = _req.HTTPError("rate limit")
    err_429.response = type("R", (), {"status_code": 429})()
    assert ws._is_transient_failure(err_429, 429) is True
    # 4xx other than 408/429 → permanent
    err_404 = _req.HTTPError("not found")
    err_404.response = type("R", (), {"status_code": 404})()
    assert ws._is_transient_failure(err_404, 404) is False
    err_401 = _req.HTTPError("auth")
    err_401.response = type("R", (), {"status_code": 401})()
    assert ws._is_transient_failure(err_401, 401) is False
    # Transport → transient
    assert ws._is_transient_failure(_req.ConnectionError("conn"), None) is True
    assert ws._is_transient_failure(_req.Timeout("timeout"), None) is True
    assert ws._is_transient_failure(TimeoutError("timeout"), None) is True
    assert ws._is_transient_failure(OSError("reset"), None) is True
    # Permanent: any other exception.
    assert ws._is_transient_failure(ValueError("nope"), None) is False
    assert ws._is_transient_failure(RuntimeError("nope"), None) is False


def test_c6_maybe_schedule_retry_creates_queued_row(monkeypatch):
    """C6: on a transient failure with attempts < cap, the
    helper enqueues a fresh row with attempts+1 and a backoff
    timestamp. ``claim_next`` will not pick it up until
    ``next_run_at`` arrives, so the worker does not busy-loop.
    """
    import time as _time
    ws.jobstore._reset_for_tests()
    job = {
        "id": 0,
        "path": "/likivik/files/a.pdf",
        "nc_path": "/likivik/files/a.pdf",
        "node_id": 1, "engine": "google", "force": False,
        "status": "running", "attempts": 0,
    }
    # Stub enqueue_retry to capture what it would write.
    captured: dict = {}
    def fake_enqueue(j, *, attempts, next_run_at):
        captured["attempts"] = attempts
        captured["next_run_at"] = next_run_at
        return 99
    monkeypatch.setattr(ws.jobstore, "enqueue_retry", fake_enqueue)

    err = requests.HTTPError("503 from sabre")
    err.response = type("R", (), {"status_code": 503})()
    now = _time.time()
    scheduled = ws._maybe_schedule_retry(job, err, 503)
    assert scheduled is True
    assert captured["attempts"] == 1
    # Backoff for the first retry is 60s (idx 0 of the schedule).
    assert 0 <= captured["next_run_at"] - now - 60.0 < 1.0


def test_c6_retry_exhausted_does_not_re_enqueue(monkeypatch):
    """C6: once ``attempts >= _MAX_RETRY_ATTEMPTS`` the helper
    must NOT enqueue another row; the failure becomes terminal
    so the operator can act on it.
    """
    ws.jobstore._reset_for_tests()
    job = {"id": 0, "path": "/likivik/files/a.pdf",
           "nc_path": "/likivik/files/a.pdf",
           "node_id": 1, "engine": "google", "force": False,
           "status": "running", "attempts": ws._MAX_RETRY_ATTEMPTS}
    called = {"n": 0}
    def fake_enqueue(*a, **k):
        called["n"] += 1
        return 99
    monkeypatch.setattr(ws.jobstore, "enqueue_retry", fake_enqueue)

    err = requests.HTTPError("503 again")
    err.response = type("R", (), {"status_code": 503})()
    assert ws._maybe_schedule_retry(job, err, 503) is False
    assert called["n"] == 0


def test_c6_claim_next_skips_jobs_whose_next_run_at_is_future(monkeypatch):
    """C6: the SQL filter added to ``claim_next`` keeps a
    scheduled retry out of the worker's hands until its
    backoff window arrives.
    """
    import time as _time
    ws.jobstore._reset_for_tests()
    # Enqueue a fresh job (no retry, claimable immediately) and
    # a scheduled retry (``next_run_at`` in the future).
    ws.jobstore.record_enqueue({
        "path": "/likivik/files/fresh.pdf",
        "nc_path": "/likivik/files/fresh.pdf",
        "node_id": 1, "engine": "google", "force": False,
        "status": "queued", "created": _time.time(),
        "next_run_at": 0,
    })
    ws.jobstore.record_enqueue({
        "path": "/likivik/files/retry.pdf",
        "nc_path": "/likivik/files/retry.pdf",
        "node_id": 2, "engine": "google", "force": False,
        "status": "queued", "created": _time.time() + 1,
        # Far in the future: claim_next must NOT pick it.
        "next_run_at": _time.time() + 3600,
    })

    j = ws.jobstore.claim_next()
    assert j is not None
    assert j["path"] == "/likivik/files/fresh.pdf"

    # The second claim must return None — the retry's backoff
    # has not elapsed.
    j2 = ws.jobstore.claim_next()
    assert j2 is None


def test_c6_stats_exposes_retry_counts():
    """C6: ``/stats`` surfaces ``retries_total`` and
    ``retries_queued`` so the panel can show the operator the
    amount of scheduled-but-not-yet-due work.
    """
    import time as _time
    ws.jobstore._reset_for_tests()
    ws.jobstore.record_enqueue({
        "path": "/likivik/files/old.pdf", "nc_path": "/likivik/files/old.pdf",
        "node_id": 1, "engine": "google", "force": False,
        "status": "queued", "created": _time.time(),
        "attempts": 0, "next_run_at": 0,
    })
    ws.jobstore.record_enqueue({
        "path": "/likivik/files/retry.pdf",
        "nc_path": "/likivik/files/retry.pdf",
        "node_id": 2, "engine": "google", "force": False,
        "status": "queued", "created": _time.time() + 1,
        "attempts": 1, "next_run_at": _time.time() + 3600,
    })
    s = ws.jobstore.stats()
    assert s.get("queued") == 2
    assert s.get("retries_total") == 1
    assert s.get("retries_queued") == 1


# --- C7: Status consumers (gone + new reasons) ----------------------------

def test_c7_gone_status_round_trips_through_states_endpoint(client):
    """C7: the 'gone' status from the previous batch must not
    break the API contract the NC app reads. The /states endpoint
    must surface the row verbatim — the frontend's STATE_DONE /
    STATE_FRESH lists do not include 'gone', so neither action
    shows, which is the correct behaviour (the file is gone,
    there is nothing to act on).

    The test asserts:

      1. /states returns the row with status='gone'.
      2. /stats does not count 'gone' rows as errors.
      3. /jobs/{id} returns the row normally (it is in the
         retention window).

    The NC app (pkgs/ocrflow-ncapp) uses STATE_DONE and
    STATE_FRESH — both lists are explicit arrays, so 'gone' is
    not enumerated, but it also is not mis-rendered: the
    FileStateService.classify() returns ``state => $status``
    for unknown statuses, and the panel's template renders
    the status as a CSS class + text. The 'gone' text appears
    unchanged. The frontend Files action shows no entries
    (neither "Send to OCR" nor "Re-OCR anyway"), which is the
    correct outcome for a non-existent file.
    """
    ws.jobstore._reset_for_tests()
    nc_path = "/likivik/files/gone_doc.pdf"
    ws.jobstore.file_put({
        "path": nc_path, "status": "gone",
        "engine": None, "reason": "file_removed",
        "node_id": 0, "finished": 1.0, "size": None, "etag": None,
    })
    # The /states endpoint is what the NC app reads; it must
    # return the row with the literal status the service stored.
    r = client.get(f"/states?paths={nc_path}", headers=h())
    assert r.status_code == 200, r.text
    body = r.json()
    states = body.get("states") or body.get("body", {}).get("states", {})
    rec = states.get(nc_path)
    assert rec is not None, body
    assert rec["status"] == "gone"
    assert rec["reason"] == "file_removed"

    # /stats does not surface 'gone' as a failure — only
    # 'error' and 'gone' are distinct counts.
    s = client.get("/stats", headers=h()).json()
    assert "gone" in s or s.get("gone", 0) == 0  # not counted as error
    # The critical assertion: 'gone' is NOT lumped into 'error'.
    assert s.get("error", 0) == 0


# --- B1: force=True must not bypass the in-flight gate ---------------------


def test_two_force_concurrent_enqueues_produce_one_jobs_row(client, monkeypatch):
    """B1 audit: two force=True callers for the SAME path while the
    first job is still queued must produce exactly ONE ``jobs`` row.

    Production shape this guards: the Nextcloud app's "Re-OCR anyway"
    is double-clicked, or ``/rescan`` races a /webhook handler, both
    with ``force=true``. The previous behaviour inserted two rows
    and ran Vision twice for one file. The fix holds a per-path
    enqueue lock so the second call sees the existing in-flight row
    and returns ``status='already_running'`` pointing at the first
    job — no second jobs row, no second Vision bill.

    We don't have to time the threads down to microseconds; the lock
    is held across the gate-and-insert pair so any interleaving of
    two force=True enqueues collapses to one row regardless of who
    lost the race.
    """
    import threading
    monkeypatch.setattr(ws, "_work_available",
                        ws._work_available)  # keep behaviour visible
    # The real worker would claim-and-run the row in milliseconds,
    # finishing it before the second caller gets a chance to see the
    # in-flight row. Stub claim_next so the first row stays
    # 'queued' across the whole test.
    monkeypatch.setattr(ws.jobstore, "claim_next", lambda: None)

    path = "/likivik/files/Work/double-clicked.pdf"

    results: list[dict] = []
    barrier = threading.Barrier(2)

    def caller(idx: int) -> None:
        barrier.wait()  # sync the start so both threads call in lockstep
        results.append(ws._enqueue(path, node_id=10, engine="google",
                                   force=True))

    t1 = threading.Thread(target=caller, args=(0,))
    t2 = threading.Thread(target=caller, args=(1,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # At least one caller must have actually enqueued — otherwise the
    # test is a no-op and proves nothing. Without the lock, both
    # would insert; with the lock, exactly one does, the second
    # returns 'already_running'.
    assert len(results) == 2
    statuses = sorted(r["status"] for r in results)
    assert statuses == ["already_running", "queued"], (
        f"force=True must collapse to one queued row + one "
        f"'already_running' handoff, got {statuses}"
    )

    # The durable invariant: exactly ONE jobs row exists for the path.
    rows = [r for r in ws.jobstore.query(path_contains=path)
            if r.get("path") == path and r.get("status") in
            ("queued", "running")]
    assert len(rows) == 1, (
        f"two force=True callers must produce ONE jobs row, "
        f"got {len(rows)}: {[r['status'] for r in rows]}"
    )


def test_force_inflight_gate_holds_check_and_insert_atomically(
        client, monkeypatch):
    """Deterministic regression for the racy ``force=True`` in-flight gate.

    The existing ``test_two_force_concurrent_enqueues_produce_one_jobs_row``
    test only FAILS on the old buggy code when the OS happens to
    schedule the threads in a way that lets the second caller hit the
    in-flight re-check before the first caller inserts. CI's timing
    exposes the race even when local runs miss it. So this test FORCES
    the bad interleaving by controlling two gates:

      * ``in_flight_job_for_path`` — the FIRST call returns ``None`` and
        sets ``t1_at_gate`` (so we know the first caller has reached
        the in-flight check but has not yet inserted). The SECOND call
        waits for ``t1_at_gate`` to be set and then runs the REAL
        ``in_flight_job_for_path`` query — which returns ``None`` under
        the buggy code (T1 has not inserted yet) but returns the row
        under the fix (T1 has already inserted, because the single
        critical section spans check + insert).
      * ``_enqueue_path_lock`` — on the buggy code the same lock object
        is returned for both critical sections, which serialises the
        two ``with`` blocks and turns the race into a sub-microsecond
        timing window CI sometimes catches and local runs never do. We
        split it per-caller: each thread's FIRST acquire returns one
        lock, each thread's SECOND acquire returns a different lock.
        The BUGGY code then sees ``with L1: check; with L2: insert``
        with L1 and L2 independent — so T2's first lock is free while
        T1 is mid-insert, the race fires, and both threads insert. The
        FIX only has one ``with _enqueue_path_lock`` per call, so both
        callers' single lock resolves to the SAME object — T2 blocks
        behind T1 and only enters after T1's insert is visible, so
        T2 sees the row and returns ``'already_running'``.
      * ``record_enqueue`` — sleeps 50 ms so T2 reliably reaches its
        in-flight check (in the first lock, in the buggy code) before
        T1 finishes the insert in its second lock.
    """
    import threading
    import time
    monkeypatch.setattr(ws.jobstore, "claim_next", lambda: None)

    path = "/likivik/files/Work/force-gate-atomic.pdf"

    real_in_flight = ws.jobstore.in_flight_job_for_path
    real_record_enqueue = ws.jobstore.record_enqueue
    gate_calls = [0]
    t1_at_gate = threading.Event()
    lock_calls: dict[int, int] = {}
    split_lock_a = threading.Lock()
    split_lock_b = threading.Lock()

    def controlled_in_flight(nc_path):
        n = gate_calls[0]
        gate_calls[0] = n + 1
        if n == 0:
            # First caller (T1): signal that we are AT the in-flight
            # gate but have not yet inserted; return None to mimic
            # "no in-flight" at the moment of T1's check.
            t1_at_gate.set()
            return None
        # Second caller (T2): wait for T1 to have reached the gate,
        # THEN run the real check. On the BUGGY code T1 has only just
        # passed its check and has not inserted yet → real check
        # returns None → T2 also falls through. On the FIX T1 has
        # already inserted (T2 was blocked on the lock until then) →
        # real check returns the row → T2 returns 'already_running'.
        assert t1_at_gate.wait(timeout=5.0), (
            "first caller never reached the in-flight gate — the "
            "test scaffolding cannot reproduce the bad interleaving"
        )
        return real_in_flight(nc_path)

    def slow_record_enqueue(job):
        # Sleep enough that T2 reliably reaches its in-flight check
        # before T1 finishes the insert.
        time.sleep(0.05)
        return real_record_enqueue(job)

    def split_path_lock(nc_path):
        """Return a DIFFERENT lock per call within one thread.

        Per-thread counter: each thread's first acquire is lock A,
        each thread's second acquire is lock B. On the buggy code the
        two ``with _enqueue_path_lock`` blocks therefore use
        different lock objects — the original buggy design intent,
        which the brief notes was accidentally collapsed to the same
        lock by a duplicate ``_ENQUEUE_LOCKS`` global. On the fix
        there is only ONE acquire per ``_enqueue`` call, so both
        callers' single lock resolves to lock A — T2 blocks behind
        T1, sees the row, returns 'already_running'.
        """
        tid = threading.get_ident()
        n = lock_calls.get(tid, 0)
        lock_calls[tid] = n + 1
        return split_lock_a if n == 0 else split_lock_b

    monkeypatch.setattr(ws.jobstore, "in_flight_job_for_path",
                        controlled_in_flight)
    monkeypatch.setattr(ws.jobstore, "record_enqueue",
                        slow_record_enqueue)
    monkeypatch.setattr(ws, "_enqueue_path_lock", split_path_lock)

    results: list[dict] = []
    errors: list[BaseException] = []

    def caller(idx: int) -> None:
        try:
            results.append(ws._enqueue(path, node_id=10, engine="google",
                                       force=True))
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    # Start caller 0 and wait for it to reach the in-flight gate so
    # the interleaving is deterministic, not racy.
    t1 = threading.Thread(target=caller, args=(0,))
    t1.start()
    assert t1_at_gate.wait(timeout=5.0), (
        "first caller never reached the in-flight gate — the test "
        "scaffolding cannot reproduce the bad interleaving"
    )
    t2 = threading.Thread(target=caller, args=(1,))
    t2.start()
    t1.join(timeout=10.0)
    t2.join(timeout=10.0)

    assert not errors, f"unexpected errors: {errors}"
    assert len(results) == 2, (
        f"both _enqueue calls must return, got {len(results)}: {results}"
    )
    statuses = sorted(r["status"] for r in results)
    assert statuses == ["already_running", "queued"], (
        f"force=True must collapse to one queued row + one "
        f"'already_running' handoff even under a forced bad "
        f"interleaving, got {statuses} "
        f"(in_flight_job_for_path was called {gate_calls[0]} times)"
    )

    # Durable invariant: exactly ONE jobs row for the path. This is
    # the property the test is really about — the in-process
    # response statuses are a secondary signal.
    rows = [r for r in ws.jobstore.query(path_contains=path)
            if r.get("path") == path and r.get("status") in
            ("queued", "running")]
    assert len(rows) == 1, (
        f"two force=True callers under the bad interleaving must "
        f"produce ONE jobs row, got {len(rows)}: "
        f"{[r['status'] for r in rows]}"
    )


def test_enqueue_cross_process_collision_returns_already_running(
        client, monkeypatch):
    """_enqueue hand-off when ``record_enqueue`` is rejected by the DB.

    Simulates the cross-process B1 backstop: another worker in a
    separate process slipped a queued row in for this path while we
    held the in-process ``_enqueue_path_lock``. Our
    ``record_enqueue`` hits ``uq_jobs_inflight`` and returns ``None``;
    ``_enqueue`` must then look up the winner and return it with
    ``status='already_running'``, matching the shape the
    in-process race produces — so the webhook / rescan / scan-all
    callers see one consistent contract regardless of which
    process actually inserted the row.

    The threading lock above is process-local; this path is the
    only thing that protects multi-worker uvicorn deployments
    from the same double-billing bug. The webhook / rescan / scan-all
    callers do not need to know which case fired.
    """
    monkeypatch.setattr(ws.jobstore, "claim_next", lambda: None)

    path = "/likivik/files/Work/cross-process.pdf"
    # Seed one in-flight row for this path via the real
    # ``record_enqueue`` — simulates "another process inserted first".
    # We need ``time.time()`` and a ``time`` import.
    import time as _time
    seeded_id = ws.jobstore.record_enqueue({
        "path": path, "nc_path": path, "node_id": 0,
        "engine": "google", "force": False, "status": "queued",
        "created": _time.time(), "started": None, "finished": None,
        "result": None, "error": None, "reason": None,
        "attempts": 0, "next_run_at": 0,
    })
    assert seeded_id is not None

    real_in_flight = ws.jobstore.in_flight_job_for_path
    call_count = [0]

    def lie_first_call_only(nc_path):
        # Lie the FIRST call (the in-process pre-check) so _enqueue
        # proceeds past the in-lock gate to the actual insert where
        # the DB backstop fires. From the SECOND call on (the
        # post-insert fallback) we let the real function run so it
        # returns the winner — that's the row we expect _enqueue to
        # hand back as ``status='already_running'``.
        call_count[0] += 1
        if call_count[0] == 1:
            return None
        return real_in_flight(nc_path)

    monkeypatch.setattr(ws.jobstore, "in_flight_job_for_path",
                        lie_first_call_only)

    result = ws._enqueue(path, node_id=10, engine="google", force=True)
    assert result.get("status") == "already_running", (
        "the cross-process path-collision must surface as"
        " 'already_running' (same contract as the in-process race),"
        f" got {result.get('status')!r}"
    )
    assert result.get("path") == path

    # And exactly ONE in-flight row exists.
    rows = [r for r in ws.jobstore.query(path_contains=path)
            if r.get("path") == path and r.get("status") in
            ("queued", "running")]
    assert len(rows) == 1

    # Sanity: restore the real in_flight_job_for_path and confirm
    # the second call (from a fresh _enqueue) sees the existing row
    # via the in-process check and returns 'already_running' there
    # too. Both paths converge on the same observable contract.
    monkeypatch.setattr(ws.jobstore, "in_flight_job_for_path",
                        real_in_flight)
    result2 = ws._enqueue(path, node_id=10, engine="google", force=True)
    assert result2.get("status") == "already_running"


# --- B2: /stats exposes retries_total + retries_queued --------------------


def test_stats_endpoint_exposes_retry_counters(client, monkeypatch):
    """B2 wire contract: /stats must include ``retries_total`` and
    ``retries_queued`` keys with int values, and the NC-app
    StatsService guard ``if (!empty(...))`` must now find them.
    """
    # Seed a few rows: one done, one queued-but-attempts>0 (a retry
    # waiting on backoff), one finished retry.
    import time
    now = time.time()
    ws.jobstore.record_enqueue({
        "path": "/likivik/files/Work/a.pdf", "nc_path": "/likivik/files/Work/a.pdf",
        "node_id": 0, "engine": "google", "force": 0, "status": "done",
        "created": now, "started": now, "finished": now,
        "result": None, "error": None, "reason": None,
        "attempts": 0, "next_run_at": None,
    })
    ws.jobstore.record_enqueue({
        "path": "/likivik/files/Work/b.pdf", "nc_path": "/likivik/files/Work/b.pdf",
        "node_id": 0, "engine": "google", "force": 0, "status": "queued",
        "created": now, "started": None, "finished": None,
        "result": None, "error": None, "reason": None,
        "attempts": 1, "next_run_at": now + 60,
    })
    ws.jobstore.record_enqueue({
        "path": "/likivik/files/Work/c.pdf", "nc_path": "/likivik/files/Work/c.pdf",
        "node_id": 0, "engine": "google", "force": 0, "status": "done",
        "created": now - 100, "started": now - 100, "finished": now - 90,
        "result": None, "error": None, "reason": None,
        "attempts": 1, "next_run_at": None,
    })

    r = client.get("/stats", headers=h())
    assert r.status_code == 200
    d = r.json()
    assert "retries_total" in d, (
        "/stats must include retries_total so the NC app's "
        "StatsService row renders — B2 wire contract"
    )
    assert "retries_queued" in d, (
        "/stats must include retries_queued for the same reason"
    )
    assert d["retries_total"] == 2, (
        f"two rows with attempts>0 must count to 2, got {d['retries_total']}"
    )
    assert d["retries_queued"] == 1, (
        f"only one row is status=queued+attempts>0, got {d['retries_queued']}"
    )
    # The pre-existing keys must still be present (so we didn't
    # accidentally drop the wire contract for the rest of the panel).
    for k in ("service", "indexed", "scanned", "skipped", "errors",
              "by_engine", "skip_reasons"):
        assert k in d, f"/stats lost key {k}"


# --- B3: _webdav_exists treats 404 *and* 410 Gone as gone ----------------


class _FakeResp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_webdav_exists_treats_410_gone_like_404(monkeypatch):
    """B3 audit: HTTP 410 Gone must yield ``False`` from
    ``_webdav_exists`` (i.e. "the path is gone for good"). Before
    the fix the helper used ``status_code != 404`` so 410 was
    classified as 'still exists' and rows could never be
    reconciled to ``status='gone'``.
    """
    monkeypatch.setattr(ws, "NC_USER", "likivik")
    monkeypatch.setattr(ws, "NC_PASSWORD", "x")

    def fake_request(method, url, **k):
        assert method == "HEAD"
        return _FakeResp(410)

    monkeypatch.setattr(ws.requests, "request", fake_request)

    assert ws._webdav_exists("/likivik/files/Work/deleted.pdf") is False, (
        "B3 fix: 410 Gone must be treated identically to 404"
    )


def test_webdav_exists_keeps_5xx_uncertain(monkeypatch):
    """B3 hardening: a transport blip (5xx) must NOT mark the file
    gone — leave it for the next reconciliation pass.
    """
    monkeypatch.setattr(ws, "NC_USER", "likivik")
    monkeypatch.setattr(ws, "NC_PASSWORD", "x")

    monkeypatch.setattr(ws.requests, "request",
                        lambda *a, **k: _FakeResp(503))
    assert ws._webdav_exists("/likivik/files/Work/blip.pdf") is True, (
        "a 5xx blip must not regress to 'gone' — keep the row for the "
        "next reconciliation pass"
    )

    # Transport error too → keep.
    def boom(*a, **k):
        import requests as _r
        raise _r.ConnectionError("tailnet down")
    monkeypatch.setattr(ws.requests, "request", boom)
    assert ws._webdav_exists("/likivik/files/Work/down.pdf") is True


# --- B5: enqueue-lock cache evicts idle entries -----------------------------


def test_enqueue_lock_cache_evicts_idle_entries(monkeypatch):
    """B5 leak guard: ``_enqueue_path_lock`` must drop entries
    unused for more than ``_ENQUEUE_LOCK_TTL_S`` so the per-path
    lock dict cannot grow without bound on a long-running service.

    We don't want to sleep for an hour — shrink the TTL and step
    forward in fake time.
    """
    # Shrink TTL so the test runs in milliseconds. Also shrink the
    # sweep interval the same way so the eviction logic stays in one
    # place.
    monkeypatch.setattr(ws, "_ENQUEUE_LOCK_TTL_S", 60.0)
    # Reset the module-level caches so a prior test's locks don't
    # leak into this one's eviction assertions. The real service
    # never does this — module state is a happy-forever effect, but
    # the test set has the freedom to clear it.
    ws._ENQUEUE_LOCKS.clear()
    ws._ENQUEUE_LOCKS_LAST_USED.clear()
    fake_now = {"t": 1_000_000.0}

    def fake_time():
        return fake_now["t"]

    monkeypatch.setattr(ws.time, "time", fake_time)

    # First call inserts an entry at t=1_000_000.
    lock_a = ws._enqueue_path_lock("/likivik/files/A/one.pdf")
    assert "/likivik/files/A/one.pdf" in ws._ENQUEUE_LOCKS
    # A second path co-exists, distinct lock.
    lock_b = ws._enqueue_path_lock("/likivik/files/B/two.pdf")
    assert lock_a is not lock_b
    assert len(ws._ENQUEUE_LOCKS) == 2

    # 30s later, neither is stale — both stay.
    fake_now["t"] += 30
    ws._enqueue_path_lock("/likivik/files/C/three.pdf")
    assert len(ws._ENQUEUE_LOCKS) == 3

    # 200s after the original entry (well past the 60s TTL), the two
    # long-untouched entries are gone, but B was touched at +30 so
    # it's only 170s old — it survives a sweep.
    fake_now["t"] = 1_000_000.0 + 200.0
    ws._enqueue_path_lock("/likivik/files/A/one.pdf")  # touched → survives
    # Now A is fresh; B+ are stale → should be evicted.
    assert len(ws._ENQUEUE_LOCKS) == 1
    assert "/likivik/files/A/one.pdf" in ws._ENQUEUE_LOCKS

    # And the race protection that the lock exists for is preserved:
    # re-acquiring the per-path lock returns the same ``Lock`` object.
    same = ws._enqueue_path_lock("/likivik/files/A/one.pdf")
    assert same is ws._ENQUEUE_LOCKS["/likivik/files/A/one.pdf"]
