"""Tests for the pdf-inspector wrapper ``pdf_classify.classify_pdf``.

Both the happy path (text_based PDF → needs_ocr=False) and the scanned-
PDF path (no text layer → needs_ocr=True) are exercised. The fallback
heuristic is harder to trigger in CI; the wrapper's return shape is
tested directly via monkeypatching the import to raise ImportError.

The visible-mojibake blind-spot regression test (``test_classify_pdf_*``
with the ``_mojibake.pdf`` fixture) verifies that the wrapper
correctly routes to OCR when the fast ``detect_pdf`` path returns
``text_based`` but the deep ``process_pdf`` path detects broken font
encoding (Type0/Identity-H without a ToUnicode CMap plus high CIDs
that the CMap can't decode). Without the two-tier fix the file is
silently skipped.
"""
from __future__ import annotations

import re

import fitz
import pikepdf
import pytest

from nc_ocr_flow import pdf_classify


def _make_pdf(path: str, *, with_text: bool) -> None:
    doc = fitz.open()
    p = doc.new_page()
    if with_text:
        p.insert_text((72, 72), "Born-digital text content " * 6)
    doc.save(path)
    doc.close()


def _make_visible_mojibake_pdf(path: str) -> None:
    """Build a PDF whose text is VISIBLE on the page but undecodable.

    Strategy: start from a fitz text PDF, then swap its /helv font for
    a Type0 / Identity-H CID font with no ``/ToUnicode`` CMap and
    rewrite the content-stream Tj hex codes to 2-byte CID values above
    0x80. The bytes still paint visible glyphs (the rendering mode is
    unchanged), but pdf_inspector's CID pass-through emits a string of
    U+FFFD replacement characters, which trips the text-quality
    heuristics in the deep ``process_pdf`` path.

    On the fast ``detect_pdf`` path this file still classifies as
    ``text_based`` with ``has_encoding_issues=False`` — that's the
    blind spot. The two-tier wrapper must therefore escalate to
    ``process_pdf`` and conclude ``needs_ocr=True``.
    """
    import tempfile

    # First make a normal text PDF.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        scratch = f.name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world sample text content for mojibake test")
    doc.save(scratch)
    doc.close()

    with pikepdf.open(scratch) as pdf:
        page = pdf.pages[0]
        res = page.obj["/Resources"]

        # Build a Type0 / Identity-H font with NO /ToUnicode CMap.
        cid_font = pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/CIDFontType2"),
                "/BaseFont": pikepdf.Name("/Helvetica"),
                "/CIDSystemInfo": pikepdf.Dictionary(
                    {
                        "/Registry": pikepdf.String("Adobe"),
                        "/Ordering": pikepdf.String("Identity"),
                        "/Supplement": 0,
                    }
                ),
                # Widths: 0 -> 500, etc. — pdf_inspector doesn't check
                # glyph widths, so the actual values are irrelevant
                # for triggering the encoding-issue path.
                "/W": pikepdf.Array([0, [500] * 256]),
            }
        )

        type0 = pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/Type0"),
                "/BaseFont": pikepdf.Name("/Helvetica"),
                "/Encoding": pikepdf.Name("/Identity-H"),
                "/DescendantFonts": pikepdf.Array([cid_font]),
                # No /ToUnicode — that is the whole point of the fixture.
            }
        )

        del res["/Font"]["/helv"]
        res["/Font"]["/helv"] = type0

        # Rewrite any <hex> Tj string in the content stream to use
        # 2-byte CID codes in the high-byte range (>0x80). pdf_inspector
        # only emits U+FFFD per CID when (a) the font is a CID font and
        # (b) at least one byte > 0x7F is undecodable, so this is the
        # minimal trigger.
        high_cids = "".join(f"{b:04X}" for b in range(0x81, 0x8F))  # 14 CIDs
        contents = page.obj["/Contents"]
        if isinstance(contents, pikepdf.Array):
            streams = list(contents)
        else:
            streams = [contents]
        for cs in streams:
            raw = cs.read_bytes()
            raw = re.sub(rb"<[0-9a-fA-F]+>", b"<" + high_cids.encode() + b">", raw)
            cs.write(raw)

        pdf.save(path)


def test_classify_pdf_text_based(tmp_path):
    """PDF with a text layer → needs_ocr=False, pdf_type=text_based.

    Control for the mojibake regression: a clean born-digital PDF must
    still be skipped (needs_ocr=False), so the two-tier fix does not
    cause needless OCR on good files.
    """
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


def test_classify_pdf_visible_mojibake(tmp_path):
    """Regression: visible-mojibake PDF must be routed to OCR.

    The fast ``detect_pdf`` path sees a Type0 / Identity-H font and
    reports ``text_based`` with ``has_encoding_issues=False`` (it
    doesn't extract text, so it can't see that every CID decodes to
    U+FFFD). Before the fix the wrapper therefore returned
    ``needs_ocr=False`` and the file was silently skipped — never
    OCR'd. The two-tier fix calls ``process_pdf`` when the fast path
    would otherwise skip, and the deep path's text-quality heuristics
    (``has_encoding_issues=True``, ``ocr_reasons_by_page`` containing
    ``suspected_garbled_text``) flip the verdict to needs_ocr=True.
    """
    p = str(tmp_path / "mojibake.pdf")
    _make_visible_mojibake_pdf(p)

    # Sanity: the fixture is genuinely constructed (not empty).
    assert pikepdf.Pdf.open(p).pages, "fixture PDF has no pages"

    result = pdf_classify.classify_pdf(p)

    assert isinstance(result["needs_ocr"], bool)
    assert isinstance(result["has_encoding_issues"], bool)
    # The two-tier fix must surface the encoding problem.
    assert result["has_encoding_issues"] is True, (
        f"expected has_encoding_issues=True, got {result!r}"
    )
    assert result["needs_ocr"] is True, (
        f"expected needs_ocr=True for visible-mojibake PDF, got {result!r}"
    )


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


def test_heuristic_looks_garbled_flags_replacement_chars():
    """The heuristic text-quality check must flag high U+FFFD density."""
    # 30% U+FFFD in a 200-char sample → trips the threshold.
    bad = "\ufffd" * 60 + "A" * 140
    assert pdf_classify._looks_garbled(bad) is True

    # A single replacement char in a long clean string → below threshold.
    ok = "Hello world this is a perfectly fine string of text" + "\ufffd"
    assert pdf_classify._looks_garbled(ok) is False


def test_heuristic_looks_garbled_flags_combining_diacritic_run():
    """The heuristic text-quality check must flag long combining-diacritic runs."""
    bad = "Hello " + "\u0301" * 10 + " World"  # 10 consecutive combining acute accents
    assert pdf_classify._looks_garbled(bad) is True

    # Just one or two diacritics → below the run-length threshold.
    ok = "Caf\u00e9 au lait"  # 'é' is precomposed, not a run
    assert pdf_classify._looks_garbled(ok) is False


def test_heuristic_looks_garbled_flags_dollar_as_space():
    """The heuristic text-quality check must flag dollar-as-space substitution."""
    bad = "Word$Word$Word " * 8  # 24 $ all between letters
    assert pdf_classify._looks_garbled(bad) is True

    # A handful of $-signs in normal text is fine.
    ok = "Price is $10. The next item costs $20. Total $30."
    assert pdf_classify._looks_garbled(ok) is False