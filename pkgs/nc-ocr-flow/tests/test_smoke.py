"""Smoke tests for nc-ocr-flow.

Validates:
  - classifier API shape (ClassifyResult, OcrResult)
  - ocr API shape (ProcessResult, PageMeta)
  - XMP round-trip via pikepdf (no real PDF needed — in-memory PDF)
  - Constants are correct
"""
from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

import pytest

from nc_ocr_flow.classifier import (
    ClassifyResult,
    OcrResult,
    DOC,
    PHOTO,
    _MOBILENET_SIZE,
    _TESSERACT_DPI,
    _PSM_DOC,
    _PSM_PHOTO,
)
from nc_ocr_flow.ocr import (
    ProcessResult,
    PageMeta,
    PER_PAGE_CONF_FLOOR,
    PER_PAGE_MIN_CHARS,
    XMP_KEYS,
    _needs_vlm,
)


# --- Constants tests --------------------------------------------------------

def test_constants():
    """Verify research-backed constants are in place."""
    assert PER_PAGE_CONF_FLOOR == 70.0
    assert PER_PAGE_MIN_CHARS == 40
    assert _MOBILENET_SIZE == 224
    assert _TESSERACT_DPI == "200"  # avoid 300-DPI Cyrillic regression
    assert _PSM_DOC == "6"          # uniform text blocks
    assert _PSM_PHOTO == "11"       # sparse text probe


def test_classify_labels():
    assert DOC == "document"
    assert PHOTO == "photo"


def test_xmp_keys_defined():
    """All XMP keys must be present for nc-mcp to consume."""
    expected = {"vlm_text", "vlm_pages", "vlm_timestamp", "confidence_floor"}
    assert set(XMP_KEYS.keys()) == expected


# --- API shape tests --------------------------------------------------------

def test_classify_result_shape():
    """ClassifyResult is a frozen dataclass with is_document and reason."""
    r = ClassifyResult(is_document=True, reason="mobilenet")
    assert r.is_document is True
    assert r.reason == "mobilenet"
    with pytest.raises(Exception):  # FrozenInstanceError
        r.is_document = False  # type: ignore


def test_ocr_result_shape():
    r = OcrResult(text="hello", confidence_p10=85.5, char_count=5)
    assert r.text == "hello"
    assert r.confidence_p10 == 85.5
    assert r.char_count == 5


def test_process_result_shape():
    r = ProcessResult(
        output_pdf="/tmp/test.pdf",
        tesseract_pages=[0, 1, 2],
        vlm_pages=[1],
        xmp_written=True,
    )
    assert r.output_pdf == "/tmp/test.pdf"
    assert r.vlm_pages == [1]
    assert r.xmp_written is True


# --- _needs_vlm logic -------------------------------------------------------

def test_needs_vlm_low_confidence():
    p = PageMeta(page_idx=0, confidence_p10=50.0, char_count=200)
    assert _needs_vlm(p) is True


def test_needs_vlm_low_chars():
    p = PageMeta(page_idx=0, confidence_p10=95.0, char_count=10)
    assert _needs_vlm(p) is True


def test_needs_vlm_good_page():
    p = PageMeta(page_idx=0, confidence_p10=95.0, char_count=200)
    assert _needs_vlm(p) is False


# --- XMP round-trip --------------------------------------------------------

def _make_minimal_pdf(path: Path) -> None:
    """Create a minimal valid 1-page PDF with empty XMP metadata slot."""
    # Use pikepdf to create a blank PDF, save it
    import pikepdf
    pdf = pikepdf.new()
    pdf.save(path)
    pdf.close()


def test_xmp_roundtrip(tmp_path: Path):
    """Verify we can write to XMP and read it back."""
    import pikepdf

    pdf_path = tmp_path / "test.pdf"
    _make_minimal_pdf(pdf_path)

    # Write a custom field via pikepdf's open_metadata
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=True) as meta:
            meta["dc:title"] = "test document"
            meta[XMP_KEYS["vlm_text"]] = "Page 1: Hello world"
            meta[XMP_KEYS["vlm_pages"]] = "[0]"
            meta[XMP_KEYS["vlm_timestamp"]] = "2026-08-13T17:00:00Z"
            meta[XMP_KEYS["confidence_floor"]] = "70.0"
        pdf.save()

    # Read it back
    with pikepdf.open(pdf_path) as pdf:
        with pdf.open_metadata() as meta:
            assert meta.get("dc:title") == "test document"
            assert meta.get(XMP_KEYS["vlm_text"]) == "Page 1: Hello world"
            assert meta.get(XMP_KEYS["vlm_pages"]) == "[0]"
            assert meta.get(XMP_KEYS["confidence_floor"]) == "70.0"


def test_xmp_survives_rename(tmp_path: Path):
    """XMP must survive file rename — main reason we chose this approach."""
    import pikepdf

    pdf_path = tmp_path / "original.pdf"
    renamed_path = tmp_path / "renamed.pdf"
    _make_minimal_pdf(pdf_path)

    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        with pdf.open_metadata(set_pikepdf_as_editor=True) as meta:
            meta[XMP_KEYS["vlm_text"]] = "Critical: this text must survive rename"
        pdf.save()

    # Rename
    pdf_path.rename(renamed_path)

    # Read after rename
    with pikepdf.open(renamed_path) as pdf:
        with pdf.open_metadata() as meta:
            assert meta.get(XMP_KEYS["vlm_text"]) == "Critical: this text must survive rename"


# --- Classifier: skip if model missing -------------------------------------

def test_classify_handles_missing_model(tmp_path: Path, monkeypatch):
    """If mobilenet model file is missing, classify must fail-safe to PHOTO."""
    monkeypatch.setenv("NC_OCR_MOBILENET_MODEL", str(tmp_path / "nonexistent.onnx"))

    # Create a tiny dummy image
    img_path = tmp_path / "test.jpg"
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="white")
    img.save(img_path, "JPEG")

    from nc_ocr_flow.classifier import classify
    result = classify(img_path)
    # Must default to photo (safe default — false negative worse than false positive)
    assert result.is_document is False
    assert "error" in result.reason.lower() or "missing" in result.reason.lower()


# --- Watcher: should_process ----------------------------------------------

def test_watcher_should_process_skips_photos():
    from nc_ocr_flow.watcher import _should_process
    assert _should_process(Path("/tank/nextcloud/data/Photos/cat.jpg")) is False


def test_watcher_should_process_skips_trash():
    from nc_ocr_flow.watcher import _should_process
    assert _should_process(Path("/tank/nextcloud/data/foo/.trash/old.pdf")) is False


def test_watcher_should_process_skips_unknown_ext():
    from nc_ocr_flow.watcher import _should_process
    assert _should_process(Path("/tank/nextcloud/data/Documents/notes.txt")) is False


def test_watcher_should_process_accepts_pdf():
    from nc_ocr_flow.watcher import _should_process
    pdf = Path("/tank/nextcloud/data/Documents/scan.pdf")
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    try:
        assert _should_process(pdf) is True
    finally:
        pdf.unlink()


def test_watcher_should_process_skips_already_ocrd(tmp_path):
    from nc_ocr_flow.watcher import _should_process
    pdf = tmp_path / "scan.pdf"
    ocr_pdf = tmp_path / "scan.ocr.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    ocr_pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    assert _should_process(pdf) is False  # .ocr.pdf exists → skip
