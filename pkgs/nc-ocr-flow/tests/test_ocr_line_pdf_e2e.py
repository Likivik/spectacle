"""End-to-end: Surya /detect geometry → line_geometry pairing → searchable PDF.

Pipeline being exercised (all production code except the inline adapter
explicitly noted):

  1. Build a deterministic synthetic image-only PDF (no text layer) with
     PyMuPDF + PIL, drawing the test phrases at known coordinates.
  2. Render page → PNG via ocr._render_page_png (production).
  3. Call surya_client.detect_lines() with mocked HTTP, returning a
     hand-crafted /detect JSON payload (Surya server not contacted).
  4. Pair geometry ↔ text via line_geometry.pair_lines_by_reading_order
     (production pure pairing).
  5. Adapt LineTextPair list → SuryaResult inline (test-only glue — there
     is no production hybrid path yet, by design — see line_geometry.py
     docstring).
  6. Call ocr._embed_surya_text(doc, page_idx, surya_result) (production).
  7. Save, re-open, assert extracted text contains expected lines,
     page count unchanged, and page still renders to a valid pixmap.

Does NOT touch Serenity, ocrmypdf, or tesseract. Does NOT modify
production code, deployment, or commit anything.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# --- Synthetic PDF builder --------------------------------------------------

# Page in PDF points (A4-ish): 595 × 842
PAGE_W = 595.0
PAGE_H = 842.0

# Six lines in two rows (row 1: 3 lines; row 2: 3 lines), with x0/y0/x1/y1
# in PDF points — but render_page_png renders at 200dpi, so image-pixel
# coordinates are (PDF_pt × 200/72). We'll compute them in the test.
#
# Expected text in reading order:
EXPECTED_LINES = [
    "alpha line one",      # row 1, left
    "beta line two",       # row 1, middle
    "gamma line three",    # row 1, right
    "delta line four",     # row 2, left
    "epsilon line five",   # row 2, middle
    "zeta line six",       # row 2, right
]


def _pt_to_px(pt: float, dpi: int = 200) -> float:
    return pt * dpi / 72.0


def _make_synthetic_pdf(path: Path) -> None:
    """Render EXPECTED_LINES into an image-only PDF (no text layer).

    Uses PIL to paint black text on a white page, then embeds that as
    the page image via PyMuPDF so get_text() returns nothing — this
    is the scanned-page case the VLM path is meant to handle.
    """
    import fitz
    from PIL import Image, ImageDraw, ImageFont

    dpi = 200
    img_w = int(_pt_to_px(PAGE_W, dpi))
    img_h = int(_pt_to_px(PAGE_H, dpi))
    img = Image.new("RGB", (img_w, img_h), "white")
    draw = ImageDraw.Draw(img)

    # Try to get a real TTF (dejavu is in the nix profile most places),
    # fall back to PIL default bitmap font.
    font = None
    for fp in [
        "/run/current-system/sw/share/X11/fonts/DejaVuSans.ttf",
        "/nix/store/cf1a53iqg6ncnygl698c4v0l8qam5a2q-gcc-14.3.0-lib/lib",  # sentinel
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]:
        if Path(fp).exists() and fp.endswith(".ttf"):
            try:
                font = ImageFont.truetype(fp, 28)
                break
            except OSError:
                pass
    if font is None:
        font = ImageFont.load_default()

    # Two rows; lines laid out at known positions
    row_y_pt = [120.0, 280.0]   # top of each row in PDF points
    x_starts_pt = [60.0, 250.0, 440.0]  # left edges of columns

    # For each EXPECTED_LINES entry, draw at known pdf-point coordinates.
    # row_y_pt[0] holds 3 lines (alpha, beta, gamma); row_y_pt[1] holds
    # 3 lines (delta, epsilon, zeta).
    positions_pt = [
        (x_starts_pt[0], row_y_pt[0]),  # alpha
        (x_starts_pt[1], row_y_pt[0]),  # beta
        (x_starts_pt[2], row_y_pt[0]),  # gamma
        (x_starts_pt[0], row_y_pt[1]),  # delta
        (x_starts_pt[1], row_y_pt[1]),  # epsilon
        (x_starts_pt[2], row_y_pt[1]),  # zeta
    ]

    for (x_pt, y_pt), text in zip(positions_pt, EXPECTED_LINES):
        x_px = _pt_to_px(x_pt, dpi)
        y_px = _pt_to_px(y_pt, dpi)
        draw.text((x_px, y_px), text, fill="black", font=font)

    # Save image to bytes → embed in PDF page (no text layer)
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_image(page.rect, stream=img_bytes.getvalue())
    doc.save(str(path))
    doc.close()


def _line_boxes_in_image_pixels() -> list[tuple[float, float, float, float]]:
    """Compute the /detect bbox payload for each EXPECTED_LINES entry,
    in image-pixel coordinates (200dpi). Used to fake Surya's /detect
    response.
    """
    dpi = 200
    row_y_pt = [120.0, 280.0]
    x_starts_pt = [60.0, 250.0, 440.0]

    # bbox is x0,y0,x1,y1 in image pixels. Use ~110pt wide, ~24pt tall.
    box_w_pt = 110.0
    box_h_pt = 24.0

    pts = [
        (x_starts_pt[0], row_y_pt[0]),
        (x_starts_pt[1], row_y_pt[0]),
        (x_starts_pt[2], row_y_pt[0]),
        (x_starts_pt[0], row_y_pt[1]),
        (x_starts_pt[1], row_y_pt[1]),
        (x_starts_pt[2], row_y_pt[1]),
    ]
    return [
        (
            _pt_to_px(x, dpi),
            _pt_to_px(y, dpi),
            _pt_to_px(x + box_w_pt, dpi),
            _pt_to_px(y + box_h_pt, dpi),
        )
        for (x, y) in pts
    ]


# --- Surya /detect mock ----------------------------------------------------

class _FakeDetectResponse:
    """Mimics requests.Response for surya_client.detect_lines()."""

    def __init__(self, payload: dict):
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _fake_detect_response() -> _FakeDetectResponse:
    """Return a /detect JSON payload matching EXPECTED_LINES layout."""
    boxes = _line_boxes_in_image_pixels()
    lines = []
    for (x0, y0, x1, y1) in boxes:
        lines.append({
            "bbox": [x0, y0, x1, y1],
            "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            "confidence": 0.95,
        })
    return _FakeDetectResponse({
        "lines": lines,
        "page_width": _pt_to_px(PAGE_W, 200),
        "page_height": _pt_to_px(PAGE_H, 200),
    })


# --- Bridge adapter (test-only; no production hybrid path exists yet) ------

def _bridge_to_surya_result(pairs, page_w: float, page_h: float):
    """Convert paired geometry+text into a SuryaResult for the embedder.

    Test-only glue. Production has no hybrid adapter yet — see
    line_geometry.py docstring explaining the seam is intentionally
    pure + standalone.
    """
    from nc_ocr_flow.surya_client import SuryaBlock, SuryaResult

    blocks = [
        SuryaBlock(
            bbox=tuple(pair.line.bbox),
            text=pair.block.text,
            confidence=pair.confidence if pair.confidence is not None else 0.0,
            label=pair.block.label or "Text",
        )
        for pair in pairs
    ]
    return SuryaResult(blocks=blocks, page_width=page_w, page_height=page_h)


# --- The actual end-to-end test --------------------------------------------

def test_geometry_to_searchable_pdf_pipeline(tmp_path: Path):
    """Whole pipeline: detect → pair → embed → extractable text."""
    import fitz
    from nc_ocr_flow import surya_client, line_geometry, ocr

    # 1. Synthetic image-only PDF
    pdf_in = tmp_path / "scanned.pdf"
    _make_synthetic_pdf(pdf_in)
    assert pdf_in.exists()

    # Sanity: input PDF has 1 page and no extractable text
    pre = fitz.open(str(pdf_in))
    assert len(pre) == 1
    assert pre[0].get_text().strip() == "", "test PDF must be image-only"
    pre.close()

    # 2. Render to PNG via production path
    png = ocr._render_page_png(pdf_in, 0, dpi=200)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "render_page_png must emit PNG"

    # 3. Surya /detect (mocked) → DetectionResult
    fake = _fake_detect_response()
    with patch.object(surya_client.requests, "post", return_value=fake) as mock_post:
        det = surya_client.detect_lines(png, url="http://mock-surya:8084")

    # The mock was actually called with /detect
    assert mock_post.call_count == 1
    assert mock_post.call_args.args[0] == "http://mock-surya:8084/detect"
    assert len(det.lines) == 6

    # 4. Pair geometry with deterministic text (production pairing)
    text_blocks = [
        line_geometry.TextBlock(text=line) for line in EXPECTED_LINES
    ]
    pairing = line_geometry.pair_lines_by_reading_order(det.lines, text_blocks)
    assert pairing.is_complete, (
        f"pairing incomplete: "
        f"{len(pairing.unmatched_lines)} unmatched lines, "
        f"{len(pairing.unmatched_texts)} unmatched texts"
    )
    paired_texts = [p.body for p in pairing.pairs]
    assert paired_texts == EXPECTED_LINES, (
        f"reading order mismatch: got {paired_texts}"
    )

    # 5. Bridge pairs → SuryaResult (test-only)
    surya_result = _bridge_to_surya_result(
        pairing.pairs, det.page_width, det.page_height,
    )
    assert len(surya_result.blocks) == 6

    # 6. Embed into a copy of the PDF via production path.
    #    Production uses doc.saveIncr() (writes back to the same file
    #    already created by _run_ocrmypdf). Here we open the input and
    #    save to a separate output path, which is the equivalent semantic
    #    for our pipeline slice.
    pdf_out = str(tmp_path / "searchable.pdf")
    doc = fitz.open(str(pdf_in))
    assert len(doc) == 1
    ocr._embed_surya_text(doc, 0, surya_result)
    doc.save(pdf_out, garbage=4, deflate=True)
    doc.close()
    assert Path(pdf_out).exists()
    assert Path(pdf_out).stat().st_size > 0

    # 7. Assert extracted text contains every expected line
    out = fitz.open(str(pdf_out))
    try:
        # Page count unchanged
        assert len(out) == 1, "page count must be preserved"

        # Extracted text — visible + invisible both searchable
        extracted = out[0].get_text().strip()

        for line in EXPECTED_LINES:
            assert line in extracted, (
                f"expected line {line!r} not in extracted text:\n{extracted!r}"
            )

        # Render still valid (proves the file is a renderable PDF, not
        # an empty / corrupted output)
        pix = out[0].get_pixmap(dpi=150)
        assert pix.width > 0 and pix.height > 0
        assert pix.samples, "rendered pixmap has no pixel data"
    finally:
        out.close()

    # 8. Round-trip with the production helper just to prove the output
    #    PDF is not corrupted: open + extract text + page count + render.
    out2 = fitz.open(str(pdf_out))
    try:
        assert len(out2) == 1
        assert out2[0].get_text().strip() != ""
        assert out2[0].get_pixmap().width > 0
    finally:
        out2.close()


# --- Second test: deterministic output regardless of input line ordering --

def test_pairing_then_embed_survives_shuffled_input(tmp_path: Path):
    """Same content, lines fed to detect() in different order — pairing
    re-orders them into the correct reading order before embedding, so
    the output PDF text must still contain every expected line.

    This guards the integration: even if Surya returns lines out of
    order (it shouldn't, but defensive), our pairing normalizes them
    before the embedder scales bboxes into PDF coordinates.
    """
    import fitz
    from nc_ocr_flow import surya_client, line_geometry, ocr

    pdf_in = tmp_path / "scanned2.pdf"
    _make_synthetic_pdf(pdf_in)

    png = ocr._render_page_png(pdf_in, 0, dpi=200)
    fake = _fake_detect_response()

    # Shuffle the lines inside the JSON payload — production pairing must
    # restore reading order via y0 + x0 sorting.
    payload = json.loads(fake.text)
    payload["lines"] = list(reversed(payload["lines"]))
    shuffled = _FakeDetectResponse(payload)

    with patch.object(surya_client.requests, "post", return_value=shuffled):
        det = surya_client.detect_lines(png, url="http://mock-surya:8084")

    text_blocks = [line_geometry.TextBlock(text=t) for t in EXPECTED_LINES]
    pairing = line_geometry.pair_lines_by_reading_order(det.lines, text_blocks)
    assert pairing.is_complete
    assert [p.body for p in pairing.pairs] == EXPECTED_LINES, (
        "pairing failed to restore reading order from shuffled input"
    )

    surya_result = _bridge_to_surya_result(
        pairing.pairs, det.page_width, det.page_height,
    )

    pdf_out = str(tmp_path / "searchable2.pdf")
    doc = fitz.open(str(pdf_in))
    ocr._embed_surya_text(doc, 0, surya_result)
    doc.save(pdf_out, garbage=4, deflate=True)
    doc.close()

    out = fitz.open(str(pdf_out))
    try:
        assert len(out) == 1
        extracted = out[0].get_text().strip()
        for line in EXPECTED_LINES:
            assert line in extracted, (
                f"line {line!r} missing after shuffle+pair+embed:\n{extracted!r}"
            )
        assert out[0].get_pixmap().width > 0
    finally:
        out.close()