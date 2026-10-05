"""Thin orchestrator: picks an engine, runs it, embeds the text layer.

Three engines — ``google`` (default), ``tesseract``, ``minimax`` — are
implemented under ``nc_ocr_flow.engines``. Each engine exposes a
``process_pdf(pdf_path, output_pdf=None)`` returning a
``ProcessResult`` whose ``engine_used`` field records which engine
actually ran.

This module:

  - Resolves the engine name (env ``NC_OCR_ENGINE`` or explicit arg).
  - Dispatches to ``engines.<name>_engine.process_pdf``.
  - For engines that return per-page ``OcrResult``s (google, minimax),
    embeds them onto the PDF via the shared helper
    ``_embed_ocr_text``.
  - Keeps the shared helpers (_render_page_png, _generate_tsv,
    _parse_tsv, born-digital detection) that engines still need.
  - Exposes ``ProcessResult`` with the new ``engine_used`` field and
    ``page_results`` list.

The single knob is ``NC_OCR_ENGINE`` ∈ {``google``, ``tesseract``,
``minimax``}. There is no L2/L3 escalation routing here — each
engine is selected and run once.
"""
from __future__ import annotations

import csv
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .ocr_models import OcrBlock, OcrResult

log = logging.getLogger(__name__)

# Per-page quality gates (kept for the historical tesseract-quality path;
# unused by engines but exported for tests / external callers).
PER_PAGE_CONF_FLOOR = 70.0
PER_PAGE_MIN_CHARS = 40

# Font for invisible text layer (must support Cyrillic)
FONT_PATH = os.environ.get(
    "NC_OCR_FONT_PATH",
    "/run/current-system/sw/share/X11/fonts/DejaVuSans.ttf",
)


# --- Public dataclasses ----------------------------------------------------


@dataclass
class PageMeta:
    page_idx: int  # 0-indexed
    confidence_p10: float
    char_count: int
    needs_vlm: bool = False


@dataclass
class ProcessResult:
    output_pdf: str
    engine_used: str = "google"
    # Engines that produce a searchable text layer (google, minimax)
    # populate this list; the tesseract engine leaves it empty because
    # ocrmypdf writes the text layer directly into the PDF.
    page_results: list[OcrResult] = field(default_factory=list)
    # 0-indexed pages where ocrmypdf/tesseract wrote a text layer.
    tess_pages: list[int] = field(default_factory=list)
    # 0-indexed pages routed to a VLM-style engine (google whole-doc
    # is whole-doc so all pages are "vlm"; minimax is per-page).
    vlm_pages: list[int] = field(default_factory=list)
    # 0-indexed pages where the engine failed and the page is text-less.
    vlm_failed_pages: list[int] = field(default_factory=list)
    # L2 router verdicts: {page_idx: {"label","confidence","escalate"}}
    # Retained as an empty default; engine may populate if it runs L2.
    l2_pages: dict[int, dict] = field(default_factory=dict)


# --- Main entry point -----------------------------------------------------


def process_pdf(
    input_path: str | Path,
    output_path: str | Path | None = None,
    engine: str | None = None,
) -> ProcessResult:
    """Run OCR on a single PDF.

    Args:
        input_path:  Source PDF.
        output_path: Destination PDF (default: <input>.ocr.pdf).
        engine:      One of ``"google"`` (default), ``"tesseract"``,
                     ``"minimax"``. If None, the ``NC_OCR_ENGINE`` env
                     var is consulted.

    Returns:
        ``ProcessResult`` with ``output_pdf``, ``engine_used``,
        ``page_results``, ``tess_pages``, ``vlm_pages``,
        ``vlm_failed_pages``. Raises ``ValueError`` for an unknown
        engine.
    """
    from .engines import resolve_engine, get_process_pdf

    chosen = resolve_engine(engine)
    engine_process = get_process_pdf(chosen)

    input_pdf = Path(input_path)
    out_pdf = (
        Path(output_path) if output_path else input_pdf.with_suffix(".ocr.pdf")
    )

    log.info("process_pdf: engine=%s input=%s output=%s",
             chosen, input_pdf, out_pdf)

    # Hand off to the engine. Engines that produce OcrResults
    # (google, minimax) need the orchestrator to embed the text layer
    # and save the PDF; tesseract writes a layer directly via ocrmypdf.
    engine_result = engine_process(
        str(input_pdf),
        str(out_pdf),
    )

    # Normalize engine output into our ProcessResult.
    return _finalize(engine_result, chosen, str(out_pdf))


def _finalize(engine_result: ProcessResult, engine: str, out_pdf: str) -> ProcessResult:
    """Embed per-page OcrResults into the PDF (if the engine produced
    any) and finalize the ``ProcessResult``.
    """
    import fitz

    page_results = engine_result.page_results or []
    if not page_results:
        # Tesseract engine: ocrmypdf already wrote the text layer; we
        # only need to ensure the file at out_pdf exists. Some engines
        # may write directly to out_pdf; trust them.
        if Path(out_pdf).exists():
            return ProcessResult(
                output_pdf=out_pdf,
                engine_used=engine,
                page_results=[],
                tess_pages=list(engine_result.tess_pages),
                vlm_pages=list(engine_result.vlm_pages),
                vlm_failed_pages=list(engine_result.vlm_failed_pages),
                l2_pages=dict(engine_result.l2_pages),
            )
        # No file written and no page_results → nothing to do.
        return ProcessResult(
            output_pdf=out_pdf,
            engine_used=engine,
            page_results=[],
            tess_pages=[],
            vlm_pages=[],
            vlm_failed_pages=[],
            l2_pages={},
        )

    # Engines that produce OcrResults need the orchestrator to embed
    # the text layer + save.
    doc = fitz.open(out_pdf)
    try:
        for page_idx, res in enumerate(page_results):
            if res.blocks:
                _embed_ocr_text(doc, page_idx, res)
        # saveIncr writes a new revision to the same file (PyMuPDF's
        # standard "save incrementally" path). If the file didn't exist
        # before, fall back to a full save.
        try:
            doc.saveIncr()
        except Exception:
            doc.save(out_pdf, garbage=4, deflate=True)
    finally:
        doc.close()

    return ProcessResult(
        output_pdf=out_pdf,
        engine_used=engine,
        page_results=page_results,
        tess_pages=list(engine_result.tess_pages),
        vlm_pages=list(engine_result.vlm_pages),
        vlm_failed_pages=list(engine_result.vlm_failed_pages),
        l2_pages=dict(engine_result.l2_pages),
    )


# --- TSV / quality helpers (kept for callers + tests) ----------------------


def _needs_vlm(page_meta: PageMeta) -> bool:
    return (
        page_meta.confidence_p10 < PER_PAGE_CONF_FLOOR
        or page_meta.char_count < PER_PAGE_MIN_CHARS
    )


def _render_page_png(pdf_path: Path, page_idx: int, dpi: int = 200) -> bytes:
    """Render a single PDF page to PNG bytes using pdftoppm (poppler)."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi),
             "-f", str(page_idx + 1), "-l", str(page_idx + 1),
             str(pdf_path), str(tmp_path.with_suffix(""))],
            check=True, capture_output=True, timeout=60,
        )
        # pdftoppm appends "-N.png"
        pngs = list(tmp_path.parent.glob(f"{tmp_path.stem}-*.png"))
        if not pngs:
            # Some versions use different naming
            pngs = list(tmp_path.parent.glob(f"{tmp_path.stem}*.png"))
        if not pngs:
            raise FileNotFoundError(
                f"pdftoppm produced no output for page {page_idx}"
            )
        return pngs[0].read_bytes()
    finally:
        for f in tmp_path.parent.glob(f"{tmp_path.stem}*"):
            try:
                f.unlink()
            except OSError:
                pass


def _run_ocrmypdf(input_pdf: Path, output_pdf: Path, tsv_path: Path) -> None:
    """Run ocrmypdf with tesseract; write sandwich PDF + sidecar text."""
    cmd = [
        "ocrmypdf",
        "--skip-text",       # skip pages with existing text (born-digital)
        "--rotate-pages",
        "--rotate-pages-threshold", "2.0",
        "--language", "rus+eng",
        "--sidecar", str(tsv_path.with_suffix(".txt")),
        "--output-type", "pdf",
        str(input_pdf),
        str(output_pdf),
    ]
    log.info("ocrmypdf: %s", " ".join(cmd))
    result = subprocess.run(cmd, check=False, capture_output=True, timeout=600)
    if result.returncode != 0:
        log.error("ocrmypdf stderr: %s", result.stderr.decode(errors="replace"))
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )


def _generate_tsv(pdf_path: Path, tsv_path: Path) -> None:
    """Run tesseract directly on each page to get TSV confidence data.

    ocrmypdf doesn't support --tsv, so we run tesseract separately
    on rendered page images to extract per-word confidence scores.
    """
    import fitz
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    all_lines = [
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
        "left\ttop\twidth\theight\tconf\ttext"
    ]
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pix = page.get_pixmap(dpi=200)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(pix.tobytes("png"))
            tmp_png = Path(tmp.name)
        try:
            tsv_out = tmp_png.with_suffix(".tsv")
            subprocess.run(
                ["tesseract", str(tmp_png), str(tsv_out.with_suffix("")),
                 "-l", "rus+eng", "tsv"],
                check=False, capture_output=True, timeout=60,
            )
            if tsv_out.exists():
                lines = tsv_out.read_text().splitlines()
                # Skip header, adjust page numbers
                for line in lines[1:]:
                    parts = line.split("\t")
                    if len(parts) >= 12 and parts[0] == "5":
                        parts[1] = str(page_idx + 1)
                        all_lines.append("\t".join(parts))
                tsv_out.unlink(missing_ok=True)
        finally:
            tmp_png.unlink(missing_ok=True)
    doc.close()
    tsv_path.write_text("\n".join(all_lines) + "\n")


def _parse_tsv(tsv_path: Path | str) -> dict[int, PageMeta]:
    """Parse tesseract TSV → per-page {conf_p10, char_count}."""
    tsv_path = Path(tsv_path)
    pages: dict[int, PageMeta] = {}
    if not tsv_path.exists():
        return pages

    per_page_confs: dict[int, list[float]] = {}
    per_page_chars: dict[int, int] = {}

    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            try:
                page_num = int(row.get("page_num", 0))
                level = int(row.get("level", 0))
                if level != 5:  # word-level only
                    continue
                conf = float(row.get("conf", -1))
                text = (row.get("text") or "").strip()
                if conf >= 0:
                    per_page_confs.setdefault(page_num, []).append(conf)
                per_page_chars[page_num] = per_page_chars.get(page_num, 0) + len(text)
            except (ValueError, KeyError):
                continue

    for page_num in per_page_confs:
        confs = sorted(per_page_confs[page_num])
        idx = max(0, len(confs) // 10 - 1)
        conf_p10 = confs[idx]
        pages[page_num] = PageMeta(
            page_idx=page_num - 1,  # convert to 0-indexed
            confidence_p10=conf_p10,
            char_count=per_page_chars.get(page_num, 0),
        )
    return pages


# --- Sandwich PDF embedding (PyMuPDF) -------------------------------------


def _get_font():
    """Get a Unicode font for invisible text (supports Cyrillic)."""
    import fitz
    if Path(FONT_PATH).exists():
        return fitz.Font(fontfile=FONT_PATH)
    # Fallback: try system fonts
    for path in [
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/nix/var/nix/profiles/default/share/fonts/dejavu/DejaVuSans.ttf",
    ]:
        if Path(path).exists():
            return fitz.Font(fontfile=path)
    # Last resort: built-in Helvetica (Latin only, no Cyrillic)
    log.warning("No Cyrillic font found; falling back to Helvetica")
    return fitz.Font("helv")


def _embed_ocr_text(doc, page_idx: int, ocr_result: OcrResult) -> None:
    """Replace existing text layer on a page with engine OCR text.

    1. Remove existing text (tesseract's, or stale) via redaction, keep
       images (the original rasterized page must remain visible).
    2. Insert OCR text as invisible text (render_mode=3) with font
       sized to fit each block bbox.

    The ``OcrResult.blocks`` carry bboxes in PNG-image pixels (the
    resolution the engine ran on); we map them to PDF-point coords
    using ``page.rect / ocr_result.page_(width|height)``.
    """
    import fitz

    page = doc[page_idx]
    font = _get_font()

    # Step 1: Remove existing text from page, keep images.
    page.add_redact_annot(page.rect)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # Step 2: Insert font into page (after redactions rebuild content).
    if font.buffer:
        page.insert_font(fontname="ocr-font", fontbuffer=font.buffer)
        fontname = "ocr-font"
    else:
        fontname = "helv"

    # Step 3: Scale image-pixel bboxes to PDF-point coords.
    page_w = page.rect.width
    page_h = page.rect.height
    sx = page_w / ocr_result.page_width if ocr_result.page_width > 0 else 1
    sy = page_h / ocr_result.page_height if ocr_result.page_height > 0 else 1

    for block in ocr_result.blocks:
        if not block.text:
            continue

        x0 = block.bbox[0] * sx
        y0 = block.bbox[1] * sy
        x1 = block.bbox[2] * sx
        y1 = block.bbox[3] * sy
        bbox = fitz.Rect(x0, y0, x1, y1)

        # Multi-line blocks: lay each line out vertically inside the bbox.
        lines = block.text.split("\n")
        if len(lines) > 1:
            n = len(lines)
            step = bbox.height / max(n, 1)
            line_bboxes = [
                (
                    ln,
                    fitz.Rect(bbox.x0, bbox.y0 + i * step,
                              bbox.x1, bbox.y0 + (i + 1) * step),
                )
                for i, ln in enumerate(lines)
            ]
        else:
            line_bboxes = [(block.text, bbox)]

        for text, lb in line_bboxes:
            if not text:
                continue
            tl = font.text_length(text, fontsize=1)
            fontsize = lb.width / tl if tl > 0 else 10
            fontsize = max(4, min(fontsize, 72))

            pos = fitz.Point(lb.x0, lb.y1)
            if font.descender < 0:
                pos.y += abs(font.descender) * fontsize * 0.3

            try:
                page.insert_text(
                    pos, text,
                    fontsize=fontsize,
                    fontname=fontname,
                    render_mode=3,  # invisible
                )
            except Exception as exc:
                log.warning(
                    "text insert failed on page %d, block bbox=%s: %s",
                    page_idx, block.bbox, exc,
                )


__all__ = [
    "ProcessResult", "PageMeta",
    "process_pdf",
    "PER_PAGE_CONF_FLOOR", "PER_PAGE_MIN_CHARS",
    "FONT_PATH",
    "_render_page_png", "_run_ocrmypdf", "_generate_tsv", "_parse_tsv",
    "_needs_vlm", "_get_font",
    "_embed_ocr_text",
]