"""Tests for the pdf-inspector wrapper ``pdf_classify.classify_pdf``.

Both the happy path (text_based PDF → needs_ocr=False) and the scanned-
PDF path (no text layer → needs_ocr=True) are exercised. The fallback
heuristic is harder to trigger in CI; the wrapper's return shape is
tested directly via monkeypatching the import to raise ImportError.
"""
import fitz
import pytest

from nc_ocr_flow import pdf_classify


def _make_pdf(path: str, *, with_text: bool) -> None:
    doc = fitz.open()
    p = doc.new_page()
    if with_text:
        p.insert_text((72, 72), "Born-digital text content " * 6)
    doc.save(path)
    doc.close()


def test_classify_pdf_text_based(tmp_path):
    """PDF with a text layer → needs_ocr=False, pdf_type=text_based."""
    p = str(tmp_path / "text.pdf")
    _make_pdf(p, with_text=True)
    result = pdf_classify.classify_pdf(p)
    assert "needs_ocr" in result
    assert "pdf_type" in result
    assert "confidence" in result
    assert "has_encoding_issues" in result
    assert isinstance(result["needs_ocr"], bool)
    # text_based + no encoding issues → needs_ocr must be False
    assert result["pdf_type"] == "text_based"
    assert result["has_encoding_issues"] is False
    assert result["needs_ocr"] is False


def test_classify_pdf_scanned(tmp_path):
    """Blank-page PDF (no text) → needs_ocr=True, pdf_type=scanned."""
    p = str(tmp_path / "scanned.pdf")
    _make_pdf(p, with_text=False)
    result = pdf_classify.classify_pdf(p)
    assert result["needs_ocr"] is True
    assert result["pdf_type"] == "scanned"


def test_classify_pdf_falls_back_on_import_error(tmp_path, monkeypatch):
    """When pdf_inspector isn't importable, fall back to the heuristic.

    Defensive: we don't want a missing optional dep to crash the
    webhook. Simulate the import failure and verify the wrapper still
    returns a usable dict with the same keys.
    """
    # Force the inside-wrapper import to fail.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pdf_inspector" or name.startswith("pdf_inspector"):
            raise ImportError("simulated missing pdf_inspector")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # Also clear the wrapper's local namespace cache if it caches the
    # module name; force a re-import path.
    if hasattr(pdf_classify, "_pdf_inspector"):
        monkeypatch.setattr(pdf_classify, "_pdf_inspector", None)

    p = str(tmp_path / "x.pdf")
    _make_pdf(p, with_text=False)  # blank → heuristic should say needs_ocr=True
    result = pdf_classify.classify_pdf(p)
    assert set(result.keys()) >= {"needs_ocr", "pdf_type", "confidence", "has_encoding_issues"}
    # Blank PDF: PyMuPDF heuristic returns text="" < 20 chars → needs_ocr=True.
    assert result["needs_ocr"] is True