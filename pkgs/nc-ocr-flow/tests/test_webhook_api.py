"""Tests for webhook_server queue endpoints: /status, /rescan, /scan-all.

Uses FastAPI TestClient with a stubbed _process_file and mocked WebDAV
(scan-all PROPFIND) — no Nextcloud or tesseract required.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

import nc_ocr_flow.webhook_server as ws  # noqa: E402

SECRET = "test-secret"


@pytest.fixture()
def client(monkeypatch):
    """TestClient with WEBHOOK_SECRET set and OCR worker stubbed."""
    monkeypatch.setattr(ws, "WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(ws, "NC_PASSWORD", "test-pass")

    # Empty the queue & history between tests
    with ws._jobs_lock:
        ws._jobs.clear()
    with ws._ocrd_lock:
        ws._ocrd_paths.clear()
    while not ws._ocr_queue.empty():
        ws._ocr_queue.get_nowait()
        ws._ocr_queue.task_done()

    # Stub out actual processing: instant success. ``force=None`` keeps
    # the stub signature compatible with both /webhook (force default)
    # and /rescan (force=True) call shapes.
    def fake_process(nc_path, node_id, engine="auto", force=None):
        return {"path": nc_path, "output": nc_path, "vlm_pages": []}

    with patch.object(ws, "_process_file", side_effect=fake_process):
        yield TestClient(ws.app)


def h():
    return {"X-Webhook-Secret": SECRET}


# --- /status ---------------------------------------------------------------

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
        ws._ocr_queue.join()
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
    with ws._ocrd_lock:
        ws._ocrd_paths.add("/likivik/files/Work/a.pdf")

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

    # Worker already drained the queue (stub is instant): verify via history
    ws._ocr_queue.join()
    with ws._jobs_lock:
        done_paths = {j["path"] for j in ws._jobs.values() if j["status"] == "done"}
    assert "/likivik/files/Work/b.pdf" in done_paths
    assert "/likivik/files/Work/a.pdf" not in done_paths


def test_scan_all_no_skip_when_disabled(client, monkeypatch):
    xml = _propfind_xml("Work/a.pdf")

    class FakeResp:
        text = xml
        def raise_for_status(self):
            pass

    monkeypatch.setattr(ws.requests, "request", lambda *a, **k: FakeResp())
    with ws._ocrd_lock:
        ws._ocrd_paths.add("/likivik/files/Work/a.pdf")

    r = client.post(
        "/scan-all",
        json={"folder": "Work", "skip_ocrd": False},
        headers=h(),
    )
    d = r.json()
    assert d["enqueued"] == 1
    assert d["skipped_ocrd"] == 0


# --- metadata stamping -------------------------------------------------------

def test_stamp_metadata(tmp_path):
    fitz = pytest.importorskip("fitz")
    from nc_ocr_flow.webhook_server import _stamp_metadata

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
    """After worker processes a job, its path lands in _ocrd_paths."""
    client.post(
        "/rescan", json={"path": "/likivik/files/x.pdf"}, headers=h()
    )
    ws._ocr_queue.join()  # wait for the worker to drain
    with ws._ocrd_lock:
        assert "/likivik/files/x.pdf" in ws._ocrd_paths


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

    monkeypatch.setattr(
        "nc_ocr_flow.webhook_server._webdav_download",
        lambda nc, dest: __import__("shutil").copy2(pdf, dest),
    )
    monkeypatch.setattr(
        "nc_ocr_flow.webhook_server._webdav_upload", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "nc_ocr_flow.webhook_server._stamp_metadata",
        lambda *a, **k: None,
    )
    with patch.object(ws, "process_pdf", side_effect=fake_proc), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        from nc_ocr_flow.webhook_server import _process_file
        res = _process_file("/likivik/files/x.pdf", node_id=1,
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

    monkeypatch.setattr(
        "nc_ocr_flow.webhook_server._webdav_download",
        lambda nc, dest: __import__("shutil").copy2(pdf, dest),
    )
    monkeypatch.setattr(
        "nc_ocr_flow.webhook_server._webdav_upload", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "nc_ocr_flow.webhook_server._stamp_metadata",
        lambda *a, **k: None,
    )
    with patch.object(ws, "process_pdf", side_effect=fake_proc), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        from nc_ocr_flow.webhook_server import _process_file
        res = _process_file("/likivik/files/y.pdf", node_id=2,
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

    monkeypatch.setattr(
        "nc_ocr_flow.webhook_server._webdav_download",
        lambda nc, dest: __import__("shutil").copy2(pdf, dest),
    )
    monkeypatch.setattr(
        "nc_ocr_flow.webhook_server._webdav_upload", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "nc_ocr_flow.webhook_server._stamp_metadata",
        lambda *a, **k: None,
    )
    with patch.object(ws, "process_pdf", side_effect=fake_proc), \
         patch.object(ws, "classify_pdf", side_effect=fake_classify):
        from nc_ocr_flow.webhook_server import _process_file
        res = _process_file("/likivik/files/z.pdf", node_id=3,
                            engine="google", force=False)

    assert calls["proc"], "classifier said needs_ocr=True → process_pdf must run"
    assert res.get("skipped") is not True
    assert res.get("path") == "/likivik/files/z.pdf"
