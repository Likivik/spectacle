"""Image branch: fail-closed classifier, collision naming, keep-original flag.

These three behaviours all sit in ``_process_file``'s image branch, where a
wrong default mutates the user's files, so they are tested against the real
branch with only the I/O edges stubbed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("NC_OCR_STATE_DIR", "/tmp/ncocr-image-branch-tests")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import nc_ocr_flow.webhook_server as ws  # noqa: E402
from nc_ocr_flow.classifier import ClassifierUnavailable, ClassifyResult  # noqa: E402


@pytest.fixture()
def image_job(tmp_path, monkeypatch):
    """Stub the image branch's I/O edges; return (calls, result_stub)."""

    def fake_download(nc_path, dest):
        Path(dest).write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

    def fake_image_to_pdf(local_file):
        out = Path(str(local_file) + ".pdf")
        out.write_bytes(b"%PDF-1.4 stub")
        return out

    def fake_process_pdf(pdf_path, engine=None):
        return SimpleNamespace(
            output_pdf=str(pdf_path) + ".out.pdf",
            engine_used="google", vlm_pages=1, tess_pages=0,
            vlm_failed_pages=0, l2_pages=0,
        )

    Path(tmp_path / "out.pdf").write_bytes(b"%PDF-1.4 out")
    calls = {"upload": [], "delete": [], "stamped": 0}
    monkeypatch.setattr(ws, "_webdav_download", fake_download)
    monkeypatch.setattr(ws, "_image_to_pdf", fake_image_to_pdf)
    monkeypatch.setattr(ws, "process_pdf", fake_process_pdf)
    monkeypatch.setattr(ws, "_assert_ocr_produced_blocks", lambda *a, **k: None)
    monkeypatch.setattr(ws, "_stamp_metadata", lambda *a, **k: calls.__setitem__("stamped", calls["stamped"] + 1))
    monkeypatch.setattr(ws, "_webdav_upload", lambda p, src: calls["upload"].append(p))
    monkeypatch.setattr(ws, "_webdav_delete", lambda p: calls["delete"].append(p))
    monkeypatch.setattr(ws, "classify", lambda p: ClassifyResult(is_document=True, reason="mobilenet"))
    # no name collisions by default
    monkeypatch.setattr(ws, "_list_dir_names", lambda d: set())
    monkeypatch.setattr(ws, "_KEEP_SOURCE_IMAGE", False)
    return calls


# --- 1. classifier unavailable must STOP, not convert -----------------------


def test_classifier_failure_stops_the_job_and_touches_nothing(image_job, monkeypatch):
    monkeypatch.setattr(ws, "_classifier_shouted", False)

    def boom(_p):
        raise ClassifierUnavailable("model file missing")

    monkeypatch.setattr(ws, "classify", boom)
    with pytest.raises(RuntimeError) as err:
        ws._process_file("/likivik/files/photo.png", 1)
    assert "classifier unavailable" in str(err.value)
    assert image_job["upload"] == [], "must not upload a converted PDF"
    assert image_job["delete"] == [], "must not delete the source image"
    assert image_job["stamped"] == 0


def test_classifier_failure_shouts_once(monkeypatch):
    ws._classifier_shouted = False
    with patch.object(ws, "log") as fake_log:
        ws._shout_classifier_unavailable(RuntimeError("missing"))
        ws._shout_classifier_unavailable(RuntimeError("missing"))
    assert fake_log.error.call_count == 1
    ws._classifier_shouted = False


# --- 2. collision gets "name (N).pdf" --------------------------------------


def test_free_pdf_path_matches_nextcloud_naming(monkeypatch):
    """One listing, then Nextcloud's own shape: a.pdf, a(1).pdf, a(2).pdf …

    No space before the parenthesis and the counter starts at 1 — that is
    what ``@nextcloud/files`` getUniqueName produces in the web UI.
    """
    monkeypatch.setattr(ws, "_list_dir_names", lambda d: {"a.pdf", "a(1).pdf"})
    assert ws._free_pdf_nc_path("/likivik/files/a.png") == "/likivik/files/a(2).pdf"


def test_free_pdf_path_starts_at_one(monkeypatch):
    monkeypatch.setattr(ws, "_list_dir_names", lambda d: {"a.pdf"})
    assert ws._free_pdf_nc_path("/likivik/files/a.png") == "/likivik/files/a(1).pdf"


def test_free_pdf_path_lists_the_parent_once(monkeypatch):
    seen = []

    def listing(d):
        seen.append(d)
        return {"a.pdf", "a(1).pdf", "a(2).pdf"}

    monkeypatch.setattr(ws, "_list_dir_names", listing)
    assert ws._free_pdf_nc_path("/likivik/files/Work/a.png") == "/likivik/files/Work/a(3).pdf"
    assert seen == ["/likivik/files/Work"], "exactly one directory listing"


def test_free_pdf_path_none_when_listing_fails(monkeypatch):
    monkeypatch.setattr(ws, "_list_dir_names", lambda d: None)
    assert ws._free_pdf_nc_path("/likivik/files/a.png") is None


def test_collision_uploads_under_a_new_name(image_job):
    assert image_job  # fixture wiring
    pdf_path = ws._free_pdf_nc_path("/likivik/files/a.png")
    assert pdf_path == "/likivik/files/a.pdf"


def test_collision_skips_when_no_name_left(image_job, monkeypatch):
    monkeypatch.setattr(ws, "_free_pdf_nc_path", lambda p: None)
    res = ws._process_file("/likivik/files/photo.png", 1)
    assert res.get("skipped") is True
    assert res.get("reason") == ws.SKIP_REASON_PDF_EXISTS
    assert image_job["upload"] == []


# --- 3. keep-original flag -------------------------------------------------


def test_keep_source_image_flag_preserves_the_original(image_job, monkeypatch):
    monkeypatch.setattr(ws, "_KEEP_SOURCE_IMAGE", True)
    res = ws._process_file("/likivik/files/photo.png", 1)
    assert image_job["upload"] == ["/likivik/files/photo.pdf"]
    assert image_job["delete"] == [], "source image must survive the flag"
    assert res.get("kept_source") is True
    assert res.get("reason") == ws.SKIP_REASON_SOURCE_KEPT


def test_default_still_deletes_the_source_image(image_job):
    res = ws._process_file("/likivik/files/photo.png", 1)
    assert image_job["delete"] == ["/likivik/files/photo.png"]
    assert res.get("kept_source") is None
    assert image_job["upload"] == ["/likivik/files/photo.pdf"]


def test_photo_still_skipped(image_job, monkeypatch):
    monkeypatch.setattr(ws, "classify", lambda p: ClassifyResult(is_document=False, reason="mobilenet"))
    res = ws._process_file("/likivik/files/photo.png", 1)
    assert res.get("skipped") is True
    assert image_job["upload"] == [] and image_job["delete"] == []


# --- the directory listing itself -----------------------------------------


def test_list_dir_names_url_is_not_double_prefixed(monkeypatch):
    """"/<user>/files/Work" must become one "/files/<user>/Work" DAV path.

    The first cut pasted the index path onto the DAV root and asked for
    /files/likivik/likivik/files/ — a 404 on every collision check.
    """
    seen = {}

    class _Resp:
        text = (
            '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
            "<d:response><d:href>/remote.php/dav/files/likivik/Work/</d:href></d:response>"
            "<d:response><d:href>/remote.php/dav/files/likivik/Work/a.pdf</d:href></d:response>"
            "</d:multistatus>"
        )

        def raise_for_status(self):
            pass

    def fake_request(method, url, **kw):
        seen["url"] = url
        seen["depth"] = kw["headers"]["Depth"]
        return _Resp()

    monkeypatch.setattr(ws.requests, "request", fake_request)
    names = ws._list_dir_names("/likivik/files/Work")
    assert seen["url"] == "http://localhost/remote.php/dav/files/likivik/Work/", seen["url"]
    assert seen["depth"] == "1"
    assert names == {"Work", "a.pdf"}
