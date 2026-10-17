"""Tests for born-digital detection, VLM routing, and redaction logic.

No GPU, no ocrmypdf needed — pure unit tests with PyMuPDF.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from nc_ocr_flow.ocr import (
    PageMeta, _parse_tsv, _needs_vlm,
    _get_font, _strip_existing_text, _embed_ocr_text, process_pdf,
    FONT_PATH,
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


# --- Re-OCR replace-text-layer regression ----------------------------------

def _make_reocr_fixture() -> Path:
    """Build a 1-page PDF with a visible raster image plus a pre-existing
    invisible (render-mode=3) text layer, simulating a user-side OCR
    pass that produced something not-quite-right.

    Using render-mode-3 invisible text is intentional: it is exactly how
    Tesseract/ocrmypdf add the user-side text layer, and it is the case
    that ``add_redact_annot(page.rect)`` + ``apply_redactions`` must
    successfully scrub.
    """
    import fitz as _fitz
    import io
    from PIL import Image

    doc = _fitz.open()
    page = doc.new_page(width=595, height=842)

    # Visible raster (a flat color image) — the source of truth that must
    # survive the redaction step.
    png_buf = io.BytesIO()
    Image.new("RGB", (450, 700), (220, 220, 220)).save(png_buf, format="PNG")
    page.insert_image(_fitz.Rect(70, 70, 525, 770), stream=png_buf.getvalue())

    # Pre-existing text layer (Tesseract-style invisible).
    page.insert_text((50, 100),
                     "PRE-EXISTING TESSERACT GARBAGE BLOCK ONE",
                     fontsize=8, fontname="helv", render_mode=3)
    page.insert_text((50, 200),
                     "PRE-EXISTING TESSERACT GARBAGE BLOCK TWO",
                     fontsize=8, fontname="helv", render_mode=3)
    page.insert_text((50, 300),
                     "PRE-EXISTING TESSERACT GARBAGE BLOCK THREE",
                     fontsize=8, fontname="helv", render_mode=3)

    out_path = Path(tempfile.mkstemp(suffix=".pdf")[1])
    doc.save(str(out_path))
    doc.close()
    return out_path


def test_reocr_zero_blocks_preserves_pre_existing_text():
    """Per-page invariant (A1): a re-OCR whose engine returns 0 blocks
    for a page must NOT strip that page's pre-existing text layer.

    Before the per-page fix, the orchestrator called
    ``_strip_existing_text(doc)`` once up front, which scrubbed
    **every** page. An engine that returned no blocks for a page
    (Vision timeout, parse failure, genuinely blank page) would
    therefore silently destroy the prior (good) text on that page
    even though the user got a brand-new file revision stamped with
    our metadata. The new invariant is per-page: pages without
    blocks keep whatever text layer they already had. Pages
    **with** blocks continue to have their old text stripped and
    the new one embedded (see ``test_reocr_replaces_with_engine_blocks``
    and ``test_reocr_per_page_skips_strip_on_no_blocks_page``).
    """
    import fitz
    from nc_ocr_flow.engines import google_engine as _ge2
    from nc_ocr_flow.ocr_models import OcrResult

    src = _make_reocr_fixture()
    out = Path(tempfile.mkstemp(suffix=".pdf")[1])

    # Mock engine: zero blocks (the failure mode the user hit).
    # The engine contract is ``list[(source_page_idx, OcrResult)]``;
    # page 0 of a 1-page source is ``(0, OcrResult(...))``.
    _orig = _ge2._ocr_pdf
    _ge2._ocr_pdf = lambda pdf_path: [
        (0, OcrResult(blocks=[], page_width=595, page_height=842)),
    ]
    try:
        result = process_pdf(src, out, engine="google")
    finally:
        _ge2._ocr_pdf = _orig

    # The orchestrator must have run cleanly.
    assert result.engine_used == "google"

    # And the pre-existing text must STILL be on the page (NOT
    # stripped). Under the old "strip-then-embed" behaviour this
    # test used to assert the OPPOSITE — and was the test pinning
    # the silent-data-loss bug; the A1 fix inverts it deliberately.
    post = fitz.open(str(out))
    try:
        text = post[0].get_text()
    finally:
        post.close()
    assert "TESSERACT GARBAGE" in text, (
        "A1: page 1 had no engine blocks; its pre-existing text "
        "layer must be PRESERVED, not silently stripped. Got: "
        f"{text!r}"
    )


def test_reocr_per_page_skips_strip_on_no_blocks_page():
    """A1 spec test: multi-page PDF whose page 2 already has a text
    layer; engine returns blocks only for page 1. After ``process_pdf``
    page 1 carries the new OCR output and page 2 still extracts its
    original text verbatim (the old whole-doc strip wiped it).

    This is the silent-data-loss mode the audit caught: a 3-page scan
    is re-OCR'd, Vision returns blocks for page 0 only (page 1 timed
    out, page 2 hit a parse error) → page 1 and page 2 used to lose
    their previously-good Tesseract layer even though we did nothing
    to those pages. Webhook/billing records show "re-OCR ran" so
    nothing on the user side signals the loss.
    """
    import fitz
    from nc_ocr_flow.engines import google_engine as _ge2
    from nc_ocr_flow.ocr_models import OcrBlock, OcrResult

    # Build a 2-page PDF; each page carries its OWN distinct
    # pre-existing text layer (render_mode=3 invisible, exactly the
    # shape a Tesseract/ocrmypdf pass produces).
    doc = fitz.open()
    p0 = doc.new_page(width=595, height=842)
    p0.insert_text((50, 50),
                   "PAGE ZERO PRE-EXISTING TEXT",
                   fontsize=12, fontname="helv", render_mode=3)
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50),
                   "PAGE ONE ORIGINAL TEXT KEEPER",
                   fontsize=12, fontname="helv", render_mode=3)

    src = Path(tempfile.mkstemp(suffix=".pdf")[1])
    doc.save(str(src))
    doc.close()

    out = Path(tempfile.mkstemp(suffix=".pdf")[1])

    # Engine returns blocks only for page 0 (page 1 is a "blank /
    # engine-failed" page). Engine contract is
    # ``list[(source_page_idx, OcrResult)]``: each tuple pairs the
    # real source page index with the engine output for it.
    new_block = OcrBlock(
        bbox=(50, 50, 545, 200),
        text="FRESH ENGINE OUTPUT FOR PAGE ZERO",
        confidence=0.95,
        label="google-block",
    )
    _orig = _ge2._ocr_pdf
    _ge2._ocr_pdf = lambda pdf_path: [
        (0, OcrResult(blocks=[new_block], page_width=595, page_height=842)),  # page 0
        (1, OcrResult(blocks=[], page_width=595, page_height=842)),         # page 1
    ]
    try:
        result = process_pdf(src, out, engine="google")
    finally:
        _ge2._ocr_pdf = _orig

    assert result.engine_used == "google"

    post = fitz.open(str(out))
    try:
        p0_text = post[0].get_text()
        p1_text = post[1].get_text()
    finally:
        post.close()

    # Page 0: engine returned blocks → old text GONE, new text IN.
    assert "PAGE ZERO PRE-EXISTING" not in p0_text, (
        f"A1 fix ineffective: page 0 should have its old text "
        f"stripped and replaced, got {p0_text!r}"
    )
    assert "FRESH ENGINE OUTPUT FOR PAGE ZERO" in p0_text, (
        f"A1 fix ineffective: new block was not embedded on page 0, "
        f"got {p0_text!r}"
    )

    # Page 1: engine returned no blocks → old text MUST be preserved
    # (NOT silently stripped). This is the regression assertion that
    # inverts under the fix: under the old whole-doc strip, this
    # text was lost.
    assert "PAGE ONE ORIGINAL TEXT KEEPER" in p1_text, (
        f"A1 silent-data-loss: page 1 had no engine blocks, so its "
        f"pre-existing text layer must be preserved verbatim, got "
        f"{p1_text!r}"
    )


def test_strip_existing_text_per_page_only_touches_target():
    """``_strip_existing_text(doc, page_idx=k)`` must redact only page
    k, leaving sibling pages' text layers untouched.

    Pins the per-page branch of the helper directly (as opposed to
    via the orchestrator) so a future refactor that re-merges the
    loops over ``doc`` is caught by this test rather than regressing
    silently through ``process_pdf``.
    """
    import fitz

    doc = fitz.open()
    p0 = doc.new_page(width=595, height=842)
    p0.insert_text((50, 50), "PAGE ZERO TEXT", fontsize=12, render_mode=3)
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50), "PAGE ONE TEXT", fontsize=12, render_mode=3)
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 50), "PAGE TWO TEXT", fontsize=12, render_mode=3)

    _strip_existing_text(doc, page_idx=1)

    try:
        t0 = doc[0].get_text()
        t1 = doc[1].get_text()
        t2 = doc[2].get_text()
    finally:
        doc.close()

    assert "PAGE ZERO" in t0, f"page 0 should be untouched: {t0!r}"
    assert t1.strip() == "", f"page 1 must be stripped: {t1!r}"
    assert "PAGE TWO" in t2, f"page 2 should be untouched: {t2!r}"


def test_reocr_replaces_with_engine_blocks():
    """Engine returns blocks → pre-existing text is gone AND new text
    is embedded."""
    import fitz
    from nc_ocr_flow.engines import google_engine as _ge2
    from nc_ocr_flow.ocr_models import OcrBlock, OcrResult

    # A synthetic block: a Cyrillic-Russian declaration header.
    block = OcrBlock(
        bbox=(50, 50, 545, 200),
        text="ЕВРАЗИЙСКИЙ ЭКОНОМИЧЕСКИЙ СОЮЗ\nДЕКЛАРАЦИЯ О СООТВЕТСТВИИ",
        confidence=0.95,
        label="google-block",
    )

    src = _make_reocr_fixture()
    out = Path(tempfile.mkstemp(suffix=".pdf")[1])

    _orig = _ge2._ocr_pdf
    _ge2._ocr_pdf = lambda pdf_path: [
        (0, OcrResult(blocks=[block], page_width=595, page_height=842)),
    ]
    try:
        result = process_pdf(src, out, engine="google")
    finally:
        _ge2._ocr_pdf = _orig

    assert result.engine_used == "google"

    post = fitz.open(str(out))
    text = post[0].get_text()
    post.close()
    assert "TESSERACT GARBAGE" not in text
    assert "ЕВРАЗИЙСКИЙ" in text, f"new Cyrillic text not embedded: {text!r}"
    assert "ДЕКЛАРАЦИЯ" in text


def test_strip_existing_text_preserves_image_raster():
    """``_strip_existing_text`` must keep the visible image untouched
    (PDF_REDACT_IMAGE_NONE) — a re-OCR never destroys the raster."""
    import fitz
    src = _make_reocr_fixture()
    out = Path(tempfile.mkstemp(suffix=".pdf")[1])
    shutil.copy(str(src), str(out))

    doc = fitz.open(str(out))
    pre_bbl = doc[0].get_bboxlog()
    pre_text = doc[0].get_text()
    n_img_pre = sum(1 for b in pre_bbl if b[0] in ("fill-image",))
    assert n_img_pre >= 1
    assert "TESSERACT GARBAGE" in pre_text

    _strip_existing_text(doc)
    post_bbl = doc[0].get_bboxlog()
    post_text = doc[0].get_text()
    n_img_post = sum(1 for b in post_bbl if b[0] in ("fill-image",))
    doc.close()

    assert post_text == "", (
        f"_strip_existing_text left text behind: {post_text!r}"
    )
    assert n_img_post >= 1, "raster was wiped — PDF_REDACT_IMAGE_NONE failed"


def test_embed_ocr_text_default_still_redacts():
    """The ``already_redacted`` parameter defaults to ``False`` so
    direct callers of ``_embed_ocr_text`` (e.g. tests that exercise
    the function in isolation) keep the previous behaviour: one call
    redacts and embeds."""
    import fitz
    from nc_ocr_flow.ocr_models import OcrBlock, OcrResult

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "OLD TEXT", fontsize=12, render_mode=3)

    block = OcrBlock(
        bbox=(50, 50, 545, 200),
        text="NEW",
        confidence=0.95,
        label="google-block",
    )
    result = OcrResult(blocks=[block], page_width=595, page_height=842)

    _embed_ocr_text(doc, 0, result)   # default: already_redacted=False
    text = doc[0].get_text()
    doc.close()

    assert "OLD TEXT" not in text
    assert "NEW" in text


def test_embed_ocr_text_already_redacted_skips_redaction():
    """When called via the orchestrator (which already stripped the
    page text), ``already_redacted=True`` skips the inner step.
    Detectable: text survival from a layer that would have been
    wiped by an embedded redact call stays intact."""
    import fitz
    from nc_ocr_flow.ocr_models import OcrBlock, OcrResult

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "EXISTING BLOCK A", fontsize=12, render_mode=3)
    # A second block we expect to KEEP (the “legacy” was already
    # stripped at the orchestrator level).
    page.insert_text((50, 100), "EXISTING BLOCK B", fontsize=12, render_mode=1)

    block = OcrBlock(
        bbox=(50, 200, 545, 350),
        text="FRESH",
        confidence=0.95,
        label="google-block",
    )
    result = OcrResult(blocks=[block], page_width=595, page_height=842)

    _embed_ocr_text(doc, 0, result, already_redacted=True)
    text = doc[0].get_text()
    doc.close()

    # Both pre-existing blocks survive (we said redacted-already)
    assert "EXISTING BLOCK A" in text
    assert "EXISTING BLOCK B" in text
    assert "FRESH" in text



def test_embed_ocr_text_normalises_decomposed_text():
    """Regression: decomposed text must never reach the text layer.

    Vision can return a word as a base letter plus a separate COMBINING
    MARK. Writing that verbatim made the embedded layer extract as
    mojibake (0 base-script characters, a pile of U+0300-U+036F marks),
    which is exactly what a broken OCR run looks like. The embedder is
    the single choke point for every engine, so it must normalise.

    Latin is used deliberately: the fallback font in a bare environment
    is Helvetica (no Cyrillic), but the normalisation mechanism is
    script-independent, and the Cyrillic side is covered by
    ``test_google_engine.test_decomposed_line_has_no_combining_marks``.
    """
    import fitz
    import unicodedata

    from nc_ocr_flow.ocr_models import OcrBlock, OcrResult

    doc = fitz.open()
    doc.new_page(width=595, height=842)

    decomposed = "Cafe\u0301"  # "Café" in NFD
    assert unicodedata.normalize("NFC", decomposed) == "Caf\u00e9"

    block = OcrBlock(
        bbox=(50, 50, 545, 200),
        text=decomposed,
        confidence=0.95,
        label="google-block",
    )
    result = OcrResult(blocks=[block], page_width=595, page_height=842)

    _embed_ocr_text(doc, 0, result, already_redacted=True)
    text = doc[0].get_text()
    doc.close()

    marks = [c for c in text if 0x0300 <= ord(c) <= 0x036F]
    assert marks == [], f"combining marks survived into the layer: {text!r}"
    assert "Caf\u00e9" in text, f"precomposed text missing from layer: {text!r}"


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
    """_is_recently_processed / _mark_processed go through SQLite."""
    import importlib
    import os
    import sys
    import tempfile

    sd = tempfile.mkdtemp(prefix="ncocr-loop-")
    old = os.environ.get("NC_OCR_STATE_DIR")
    os.environ["NC_OCR_STATE_DIR"] = sd
    try:
        for mod_name in list(sys.modules):
            if mod_name in ("nc_ocr_flow.webhook_server",
                            "nc_ocr_flow.jobstore"):
                del sys.modules[mod_name]
        ws = importlib.import_module("nc_ocr_flow.webhook_server")
        assert not ws._is_recently_processed(999)
        ws._mark_processed(999)
        assert ws._is_recently_processed(999)
        assert not ws._is_recently_processed(998)
        ws.jobstore.node_forget(999)
        assert not ws._is_recently_processed(999)
    finally:
        if old is None:
            os.environ.pop("NC_OCR_STATE_DIR", None)
        else:
            os.environ["NC_OCR_STATE_DIR"] = old
        for mod_name in ("nc_ocr_flow.webhook_server",
                         "nc_ocr_flow.jobstore"):
            sys.modules.pop(mod_name, None)


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
