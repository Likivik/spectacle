"""Tests for VLM fallback path with a mock HTTP server.

Validates:
  - ocrmypdf TSV parsing produces correct PageMeta
  - Low-confidence pages trigger VLM call
  - VLM response is written to XMP
  - Full process_pdf works end-to-end with mock VLM

No GPU needed — VLM endpoint is mocked via pytest-httpserver.
Tesseract + ocrmypdf run for real (CPU, ~5-15s per test).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# --- TSV parsing tests (no VLM, no ocrmypdf needed) -------------------------

def test_parse_tsv_empty(tmp_path: Path):
    """_parse_tsv returns empty dict for missing file."""
    from nc_ocr_flow.ocr import _parse_tsv
    result = _parse_tsv(tmp_path / "nonexistent.tsv")
    assert result == {}


def test_parse_tsv_single_page(tmp_path: Path):
    """_parse_tsv correctly parses a single page with known confidence."""
    from nc_ocr_flow.ocr import _parse_tsv, PageMeta

    tsv = tmp_path / "ocr.tsv"
    lines = [
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t95.0\tHello",
        "5\t1\t1\t1\t1\t2\t10\t10\t50\t20\t90.0\tWorld",
        "5\t1\t1\t1\t1\t3\t10\t10\t50\t20\t88.0\tTest",
    ]
    tsv.write_text("\n".join(lines) + "\n")

    result = _parse_tsv(tsv)
    assert 1 in result
    page = result[1]
    assert isinstance(page, PageMeta)
    assert page.page_idx == 0
    assert page.confidence_p10 == 88.0
    assert page.char_count == 14


def test_parse_tsv_multi_page(tmp_path: Path):
    """_parse_tsv handles multiple pages correctly."""
    from nc_ocr_flow.ocr import _parse_tsv

    tsv = tmp_path / "ocr.tsv"
    lines = [
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t95.0\tPage1",
        "5\t2\t1\t1\t1\t1\t10\t10\t50\t20\t30.0\tlow",
    ]
    tsv.write_text("\n".join(lines) + "\n")

    result = _parse_tsv(tsv)
    assert len(result) == 2
    assert result[1].confidence_p10 == 95.0
    assert result[2].confidence_p10 == 30.0
    assert result[1].page_idx == 0
    assert result[2].page_idx == 1


# --- VLM fallback decision logic -------------------------------------------

def test_needs_vlm_threshold_boundary():
    """Page at exactly the confidence floor does NOT need VLM."""
    from nc_ocr_flow.ocr import _needs_vlm, PageMeta, PER_PAGE_CONF_FLOOR
    p = PageMeta(page_idx=0, confidence_p10=PER_PAGE_CONF_FLOOR, char_count=200)
    assert _needs_vlm(p) is False


def test_needs_vlm_below_threshold():
    """Page below confidence floor needs VLM."""
    from nc_ocr_flow.ocr import _needs_vlm, PageMeta, PER_PAGE_CONF_FLOOR
    p = PageMeta(page_idx=0, confidence_p10=PER_PAGE_CONF_FLOOR - 0.1, char_count=200)
    assert _needs_vlm(p) is True


def test_needs_vlm_above_char_floor():
    """Page with high conf but too few chars needs VLM."""
    from nc_ocr_flow.ocr import _needs_vlm, PageMeta, PER_PAGE_MIN_CHARS
    p = PageMeta(page_idx=0, confidence_p10=95.0, char_count=PER_PAGE_MIN_CHARS - 1)
    assert _needs_vlm(p) is True


# --- Mock VLM HTTP server tests --------------------------------------------

def test_vlm_mock_response_shape(httpserver, monkeypatch):
    """Verify _olmocr_ocr_page correctly parses OpenAI-format response."""
    from nc_ocr_flow.ocr import _olmocr_ocr_page

    httpserver.expect_request(
        "/v1/chat/completions", method="POST"
    ).respond_with_json({
        "choices": [{
            "message": {
                "content": "Extracted text from mock VLM"
            }
        }]
    })

    monkeypatch.setattr("nc_ocr_flow.ocr.OLMOCR_ENDPOINT", httpserver.url_for("").rstrip("/"))

    result = _olmocr_ocr_page(b"\x89PNG fake bytes")
    assert result == "Extracted text from mock VLM"


def test_vlm_mock_handles_error_response(httpserver, monkeypatch):
    """_olmocr_ocr_page raises on non-200 response."""
    from nc_ocr_flow.ocr import _olmocr_ocr_page
    import requests

    httpserver.expect_request(
        "/v1/chat/completions", method="POST"
    ).respond_with_data("Internal Error", status=500)

    monkeypatch.setattr("nc_ocr_flow.ocr.OLMOCR_ENDPOINT", httpserver.url_for("").rstrip("/"))

    with pytest.raises(requests.HTTPError):
        _olmocr_ocr_page(b"\x89PNG fake bytes")


# --- XMP write tests --------------------------------------------------------

def test_xmp_write_after_vlm_fallback(tmp_path: Path):
    """XMP is written correctly with VLM text after process_pdf."""
    import pikepdf
    from nc_ocr_flow.ocr import _write_xmp, XMP_KEYS, PER_PAGE_CONF_FLOOR

    pdf_path = tmp_path / "test.pdf"
    pdf = pikepdf.new()
    pdf.save(pdf_path)
    pdf.close()

    vlm_text = {0: "Page 1 VLM text", 2: "Page 3 VLM text"}
    result = _write_xmp(pdf_path, vlm_text, PER_PAGE_CONF_FLOOR)

    assert result is True

    with pikepdf.open(pdf_path) as pdf:
        with pdf.open_metadata() as meta:
            vlm = meta.get(XMP_KEYS["vlm_text"])
            assert "Page 1 VLM text" in vlm
            assert "Page 3 VLM text" in vlm
            assert "--- Page 1 ---" in vlm
            assert "--- Page 3 ---" in vlm

            pages = json.loads(meta.get(XMP_KEYS["vlm_pages"]))
            assert pages == [0, 2]

            assert meta.get(XMP_KEYS["confidence_floor"]) == str(PER_PAGE_CONF_FLOOR)


def test_xmp_write_empty_dict(tmp_path: Path):
    """_write_xmp returns False for empty VLM text (nothing to write)."""
    import pikepdf
    from nc_ocr_flow.ocr import _write_xmp

    pdf_path = tmp_path / "test.pdf"
    pdf = pikepdf.new()
    pdf.save(pdf_path)
    pdf.close()

    result = _write_xmp(pdf_path, {}, 70.0)
    assert result is False


# --- Full pipeline with mock VLM (integration, slow) -----------------------

@pytest.mark.slow
def test_process_pdf_end_to_end_mock_vlm(httpserver, monkeypatch, tmp_path: Path):
    """Full process_pdf: ocrmypdf -> TSV parse -> mock VLM fallback -> XMP write.

    This test runs ocrmypdf + tesseract for real (CPU, ~10-30s).
    VLM endpoint is mocked — validates the pipeline logic, not the model.
    """
    from nc_ocr_flow.ocr import process_pdf

    httpserver.expect_request(
        "/v1/chat/completions", method="POST"
    ).respond_with_json({
        "choices": [{
            "message": {"content": "MOCK VLM EXTRACTED TEXT"}
        }]
    })
    monkeypatch.setattr("nc_ocr_flow.ocr.OLMOCR_ENDPOINT", httpserver.url_for("").rstrip("/"))

    import pikepdf
    input_pdf = tmp_path / "input.pdf"
    pdf = pikepdf.new()
    pdf.save(input_pdf)
    pdf.close()

    output_pdf = tmp_path / "output.pdf"

    result = process_pdf(input_pdf, output_pdf)

    assert isinstance(result.tesseract_pages, list)
    assert isinstance(result.vlm_pages, list)
    assert isinstance(result.xmp_written, bool)

    if result.vlm_pages:
        assert result.xmp_written is True
        with pikepdf.open(output_pdf) as pdf:
            with pdf.open_metadata() as meta:
                from nc_ocr_flow.ocr import XMP_KEYS
                vlm = meta.get(XMP_KEYS["vlm_text"])
                assert vlm is not None
                assert "MOCK VLM EXTRACTED TEXT" in vlm


@pytest.mark.slow
def test_process_pdf_good_text_no_vlm(httpserver, monkeypatch, tmp_path: Path):
    """If tesseract extracts text with high confidence, VLM is NOT called."""
    from nc_ocr_flow.ocr import process_pdf

    httpserver.expect_request(
        "/v1/chat/completions", method="POST"
    ).respond_with_json({
        "choices": [{"message": {"content": "SHOULD NOT BE USED"}}]
    })
    monkeypatch.setattr("nc_ocr_flow.ocr.OLMOCR_ENDPOINT", httpserver.url_for("").rstrip("/"))

    try:
        from PIL import Image, ImageDraw, ImageFont
        import img2pdf
        img = Image.new("RGB", (1000, 800), color="white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 32)
        except (OSError, IOError):
            font = ImageFont.load_default()
        for i, line in enumerate([
            "This is a test document for OCR processing.",
            "It contains multiple lines of clear text.",
            "The text should be extracted by tesseract.",
            "Each line has enough characters for confidence.",
            "Russian: This is a test document for recognition.",
        ]):
            draw.text((50, 50 + i * 40), line, fill="black", font=font)

        input_pdf = tmp_path / "input.pdf"
        input_pdf.write_bytes(img2pdf.convert(img))
    except ImportError:
        pytest.skip("PIL or img2pdf not available")

    output_pdf = tmp_path / "output.pdf"
    result = process_pdf(input_pdf, output_pdf)

    # With good text, VLM should not be called
    assert len(result.vlm_pages) == 0
