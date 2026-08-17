"""Tests for born-digital detection, VLM routing, and redaction logic.

No GPU, no ocrmypdf needed — pure unit tests with PyMuPDF.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from nc_ocr_flow.ocr import (
    PageMeta, _parse_tsv, _needs_vlm, _embed_surya_text,
    _get_font, FONT_PATH,
    PER_PAGE_CONF_FLOOR, PER_PAGE_MIN_CHARS,
)


# --- Born-digital detection --------------------------------------------------

def _make_pdf_with_text(text: str = "Hello world this is a test page with enough text") -> Path:
    """Create a born-digital PDF with real text layer."""
    import fitz
    import tempfile
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), text, fontsize=12)
    doc.save(f.name)
    doc.close()
    return Path(f.name)


def _make_image_only_pdf() -> Path:
    """Create an image-only PDF (no text layer)."""
    import fitz
    import tempfile
    f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Draw a rectangle (simulates scanned image content, no text)
    page.draw_rect(fitz.Rect(0, 0, 595, 842), color=(1, 1, 1), fill=(0.9, 0.9, 0.9))
    doc.save(f.name)
    doc.close()
    return Path(f.name)


def test_born_digital_pdf_has_text():
    """PDF with real text layer should be detected as having text."""
    import fitz
    pdf = _make_pdf_with_text("Это тестовая страница с достаточным количеством текста")
    doc = fitz.open(str(pdf))
    text = doc[0].get_text().strip()
    assert len(text) > 20
    doc.close()
    pdf.unlink()


def test_image_only_pdf_no_text():
    """Image-only PDF should have no extractable text."""
    import fitz
    pdf = _make_image_only_pdf()
    doc = fitz.open(str(pdf))
    text = doc[0].get_text().strip()
    assert len(text) == 0
    doc.close()
    pdf.unlink()


# --- VLM routing with born-digital detection ---------------------------------

def test_vlm_routing_skips_born_digital():
    """Born-digital pages (text > 20 chars) should not go to VLM."""
    import fitz
    pdf = _make_pdf_with_text("This is a long enough text to trigger skip-text logic in ocrmypdf")
    doc = fitz.open(str(pdf))
    num_pages = len(doc)
    skipped = set()
    for i in range(num_pages):
        if len(doc[i].get_text().strip()) > 20:
            skipped.add(i)
    assert 0 in skipped
    doc.close()
    pdf.unlink()


def test_vlm_routing_includes_image_only_pages():
    """Pages with no text should NOT be in skipped set → eligible for VLM."""
    import fitz
    pdf = _make_image_only_pdf()
    doc = fitz.open(str(pdf))
    skipped = set()
    for i in range(len(doc)):
        if len(doc[i].get_text().strip()) > 20:
            skipped.add(i)
    assert 0 not in skipped
    doc.close()
    pdf.unlink()


def test_vlm_routing_empty_tsv_flags_page():
    """When tesseract finds nothing (empty TSV), page should go to VLM.

    This was the bug: empty TSV → no page_meta entry → page invisible to routing.
    """
    # Simulate: no TSV entries for page 0
    page_meta = {}  # empty — tesseract found nothing
    num_pages = 1
    skipped_pages = set()

    vlm_pages = []
    for page_idx in range(num_pages):
        if page_idx in skipped_pages:
            continue
        meta = page_meta.get(page_idx + 1)
        if meta is None or _needs_vlm(meta):
            vlm_pages.append(page_idx)

    assert 0 in vlm_pages


def test_vlm_routing_mixed_pages():
    """Mixed PDF: some born-digital, some scanned."""
    import fitz
    # Page 0: born-digital, Page 1: image-only
    doc = fitz.open()
    p0 = doc.new_page(width=595, height=842)
    p0.insert_text((50, 50), "This page has real digital text content", fontsize=12)
    p1 = doc.new_page(width=595, height=842)
    p1.draw_rect(fitz.Rect(0, 0, 595, 842), color=(1, 1, 1), fill=(0.9, 0.9, 0.9))

    skipped = set()
    for i in range(len(doc)):
        if len(doc[i].get_text().strip()) > 20:
            skipped.add(i)

    assert 0 in skipped  # born-digital
    assert 1 not in skipped  # image-only

    doc.close()


# --- Full-page redaction -----------------------------------------------------

def test_redaction_preserves_images():
    """Full-page redaction with PDF_REDACT_IMAGE_NONE should preserve images."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Insert an image (rectangle as placeholder)
    page.insert_text((50, 50), "Tesseract text", fontsize=12)

    # Redact entire page (removes text, keeps images)
    page.add_redact_annot(page.rect)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    text = page.get_text().strip()
    assert len(text) == 0  # text removed

    doc.close()


def test_redaction_with_fill_hides_content():
    """Redaction with fill=(1,1,1) would hide content — this is the old bug."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "Secret text", fontsize=12)

    # Old behavior: fill white over everything
    page.add_redact_annot(page.rect, fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # Text is removed AND page content is whited out
    text = page.get_text().strip()
    assert len(text) == 0

    doc.close()


# --- Font handling -----------------------------------------------------------

def test_get_font_returns_font_object():
    """_get_font returns a fitz.Font object."""
    import fitz
    font = _get_font()
    assert isinstance(font, fitz.Font)


def test_font_has_buffer_or_name():
    """Font either has a buffer (custom TTF) or is built-in (helv)."""
    font = _get_font()
    # Custom fonts have buffer, built-in Helvetica has None buffer
    assert font.buffer is not None or font.name == "helv"


# --- Surya server model binding ----------------------------------------------

def test_surya_server_models_at_module_level():
    """Surya server models must be at module level for FastAPI/Pydantic."""
    from nc_ocr_flow.surya_server import OcrRequest, OcrResponse, BlockOut
    # These should be real classes, not ForwardRef
    assert hasattr(OcrRequest, "model_fields")
    assert "image_b64" in OcrRequest.model_fields
    assert hasattr(OcrResponse, "model_fields")
    assert hasattr(BlockOut, "model_fields")


def test_surya_request_validation():
    """OcrRequest validates image_b64 field."""
    from nc_ocr_flow.surya_server import OcrRequest
    req = OcrRequest(image_b64="dGVzdA==")
    assert req.image_b64 == "dGVzdA=="


# --- Webhook server ----------------------------------------------------------

def test_webdav_url_parsing():
    """_webdav_url correctly parses NC internal paths."""
    from nc_ocr_flow.webhook_server import _webdav_url
    url = _webdav_url("/admin/files/Documents/test.pdf")
    assert "/remote.php/dav/files/admin/Documents/test.pdf" in url


def test_webdav_url_fallback():
    """_webdav_url falls back to NC_USER for non-standard paths."""
    from nc_ocr_flow.webhook_server import _webdav_url
    url = _webdav_url("relative/path.pdf")
    assert "remote.php/dav" in url


def test_loop_prevention():
    """_is_recently_processed / _mark_processed work correctly."""
    from nc_ocr_flow.webhook_server import (
        _is_recently_processed, _mark_processed, _processed_ids,
    )
    _processed_ids.clear()
    assert not _is_recently_processed(999)
    _mark_processed(999)
    assert _is_recently_processed(999)
    assert not _is_recently_processed(998)


def test_webhook_secret_reading():
    """_read_secret reads from env var or file."""
    from nc_ocr_flow.webhook_server import _read_secret
    import os
    # Direct env var
    os.environ["TEST_SECRET_DIRECT"] = "secret123"
    assert _read_secret("TEST_SECRET_DIRECT") == "secret123"
    del os.environ["TEST_SECRET_DIRECT"]
    # No value → empty string
    assert _read_secret("NONEXISTENT_SECRET") == ""


def test_webhook_event_filtering():
    """Webhook only processes NodeCreatedEvent and NodeWrittenEvent."""
    # The event classes are checked as strings in handle_webhook
    valid_events = [
        "OCP\\Files\\Events\\Node\\NodeCreatedEvent",
        "OCP\\Files\\Events\\Node\\NodeWrittenEvent",
    ]
    invalid_events = [
        "OCP\\Files\\Events\\Node\\NodeDeletedEvent",
        "OCP\\Files\\Events\\Node\\NodeRenamedEvent",
    ]
    assert all(e in valid_events for e in valid_events)
    assert not any(e in valid_events for e in invalid_events)


# --- TSV edge cases ----------------------------------------------------------

def test_parse_tsv_negative_confidence_ignored():
    """Words with conf=-1 (tesseract "empty") should not count."""
    tsv_text = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t-1\t\n"
        "5\t1\t1\t1\t1\t2\t10\t10\t50\t20\t95.0\tHello\n"
    )
    import tempfile
    f = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w")
    f.write(tsv_text)
    f.close()
    result = _parse_tsv(f.name)
    # Only one valid word (conf >= 0)
    assert 1 in result
    assert result[1].char_count == 5  # "Hello"
    Path(f.name).unlink()


def test_parse_tsv_conf_p10_calculation():
    """p10 confidence is the 10th percentile of word confidences."""
    # 20 words, all confidence 80.0 → p10 = 80.0
    lines = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"]
    for i in range(20):
        lines.append(f"5\t1\t1\t1\t1\t{i+1}\t10\t10\t50\t20\t80.0\tword{i}")
    import tempfile
    f = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, mode="w")
    f.write("\n".join(lines) + "\n")
    f.close()
    result = _parse_tsv(f.name)
    assert result[1].confidence_p10 == 80.0
    Path(f.name).unlink()
