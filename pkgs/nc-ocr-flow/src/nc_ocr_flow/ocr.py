"""Hybrid OCR pipeline: tesseract-first, Surya VLM fallback, sandwich PDF.

Pipeline:
  1. ocrmypdf --skip-text --language rus+eng --tsv  (tesseract pass)
     - Pages with existing text (born-digital) are skipped automatically
     - Pages without text get tesseract OCR → sandwich PDF with text layer
     - TSV file written with per-word confidence scores
  2. Parse TSV → per-page 10th-percentile confidence
  3. Pages with conf_p10 < 70 or chars < 40 → Surya VLM fallback
  4. Surya returns blocks with bbox + text (91 languages, including Russian)
  5. For VLM pages: remove tesseract text layer, insert Surya text as invisible layer
  6. Save PDF (NC versioning preserves original)

API:
    process_pdf(input_path, output_path) -> ProcessResult
"""
from __future__ import annotations

import csv
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Per-page quality gates
PER_PAGE_CONF_FLOOR = 70.0
PER_PAGE_MIN_CHARS = 40

# Font for invisible text layer (must support Cyrillic)
# On NixOS: dejavu_fonts, noto-fonts, etc.
FONT_PATH = os.environ.get(
    "NC_OCR_FONT_PATH",
    "/run/current-system/sw/share/X11/fonts/DejaVuSans.ttf",
)


@dataclass
class PageMeta:
    page_idx: int  # 0-indexed
    confidence_p10: float
    char_count: int
    needs_vlm: bool = False


@dataclass
class ProcessResult:
    output_pdf: str
    tesseract_pages: list[int] = field(default_factory=list)
    vlm_pages: list[int] = field(default_factory=list)


# --- ocrmypdf (tesseract pass) -----------------------------------------------

def _run_ocrmypdf(input_pdf: Path, output_pdf: Path, tsv_path: Path) -> None:
    """Run ocrmypdf with tesseract, produce sandwich PDF + sidecar text."""
    cmd = [
        "ocrmypdf",
        "--skip-text",       # skip pages with existing text (born-digital)
        "--rotate-pages",
        "--deskew",
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
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)


def _generate_tsv(pdf_path: Path, tsv_path: Path) -> None:
    """Run tesseract directly on each page to get TSV confidence data.

    ocrmypdf doesn't support --tsv, so we run tesseract separately
    on rendered page images to extract per-word confidence scores.
    """
    import fitz
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    all_lines = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"]
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


def _needs_vlm(page_meta: PageMeta) -> bool:
    return (
        page_meta.confidence_p10 < PER_PAGE_CONF_FLOOR
        or page_meta.char_count < PER_PAGE_MIN_CHARS
    )


# --- Page rendering ----------------------------------------------------------

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
            raise FileNotFoundError(f"pdftoppm produced no output for page {page_idx}")
        return pngs[0].read_bytes()
    finally:
        for f in tmp_path.parent.glob(f"{tmp_path.stem}*"):
            try:
                f.unlink()
            except OSError:
                pass


# --- Surya VLM OCR -----------------------------------------------------------

def _surya_ocr_page(png_bytes: bytes):
    """Call Surya server on serenity, get blocks with bbox + text."""
    from .surya_client import ocr_page
    return ocr_page(png_bytes)


# --- Sandwich PDF embedding (PyMuPDF) ----------------------------------------

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


def _embed_surya_text(doc, page_idx: int, surya_result) -> None:
    """Replace tesseract text layer on a page with Surya's text.

    1. Remove existing text (tesseract's) via redaction, keep images
    2. Insert Surya text as invisible text (render_mode=3) with proper font sizing
    """
    import fitz

    page = doc[page_idx]
    font = _get_font()

    # Step 1: Remove ALL tesseract text from page, keep images
    page.add_redact_annot(page.rect)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # Step 2: Insert font into page (after redactions, which rebuild content)
    if font.buffer:
        page.insert_font(fontname="surya-font", fontbuffer=font.buffer)
        fontname = "surya-font"
    else:
        fontname = "helv"

    # Step 3: Scale Surya bboxes (image pixels) to PDF coordinates (points)
    page_w = page.rect.width
    page_h = page.rect.height
    scale_x = page_w / surya_result.page_width if surya_result.page_width > 0 else 1
    scale_y = page_h / surya_result.page_height if surya_result.page_height > 0 else 1

    for block in surya_result.blocks:
        if not block.text:
            continue

        # Scale bbox to PDF coordinates
        x0 = block.bbox[0] * scale_x
        y0 = block.bbox[1] * scale_y
        x1 = block.bbox[2] * scale_x
        y1 = block.bbox[3] * scale_y
        bbox = fitz.Rect(x0, y0, x1, y1)

        # Calculate font size to fit bbox width
        text = block.text
        tl = font.text_length(text, fontsize=1)
        if tl > 0:
            fontsize = bbox.width / tl
        else:
            fontsize = 10

        # Clamp font size to reasonable range
        fontsize = max(4, min(fontsize, 72))

        # Insert invisible text at bottom-left of bbox
        # render_mode=3 = invisible (not rendered, but selectable/searchable)
        pos = fitz.Point(bbox.x0, bbox.y1)
        # Adjust for descenders (g, y, p, etc.)
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
            log.warning("text insert failed on page %d, block bbox=%s: %s",
                        page_idx, block.bbox, exc)


# --- main entry point --------------------------------------------------------

def process_pdf(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> ProcessResult:
    """Run the full hybrid OCR pipeline on a single PDF.

    1. Tesseract (ocrmypdf) → sandwich PDF + TSV confidence
    2. Low-confidence pages → Surya VLM → re-embed text layer

    Args:
        input_path: Source PDF (or image converted to PDF)
        output_path: Destination PDF (default: input with .ocr.pdf suffix)

    Returns:
        ProcessResult with output path, tesseract/VLM page lists.
    """
    import fitz

    input_pdf = Path(input_path)
    output_pdf = (
        Path(output_path) if output_path
        else input_pdf.with_suffix(".ocr.pdf")
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        tsv_path = tmp / "ocr.tsv"

        # Pass 1: tesseract
        _run_ocrmypdf(input_pdf, output_pdf, tsv_path)
        _generate_tsv(output_pdf, tsv_path)
        page_meta = _parse_tsv(tsv_path)

    # Detect pages that already had text (ocrmypdf --skip-text skipped them)
    import fitz
    pre_ocr_doc = fitz.open(str(input_pdf))
    skipped_pages = set()
    num_pages = len(pre_ocr_doc)
    for page_idx in range(num_pages):
        page_text = pre_ocr_doc[page_idx].get_text().strip()
        if len(page_text) > 20:
            skipped_pages.add(page_idx)
    pre_ocr_doc.close()

    # Identify pages needing VLM (skip pages ocrmypdf already skipped)
    vlm_pages = []
    for page_idx in range(num_pages):
        if page_idx in skipped_pages:
            continue
        meta = page_meta.get(page_idx + 1)  # TSV uses 1-indexed pages
        if meta is None or _needs_vlm(meta):
            vlm_pages.append(page_idx)

    log.info("tesseract pages: %d, vlm pages: %d",
             len(page_meta), len(vlm_pages))

    # Pass 2: Surya VLM for bad pages
    if vlm_pages:
        doc = fitz.open(str(output_pdf))

        for page_idx in vlm_pages:
            try:
                log.info("Surya OCR page %d", page_idx)
                png = _render_page_png(output_pdf, page_idx)
                surya_result = _surya_ocr_page(png)
                _embed_surya_text(doc, page_idx, surya_result)
            except Exception as exc:
                log.warning("Surya failed for page %d: %s", page_idx, exc)

        # Save with incremental update (preserves tesseract pages)
        doc.saveIncr()
        doc.close()

    return ProcessResult(
        output_pdf=str(output_pdf),
        tesseract_pages=sorted(m.page_idx for m in page_meta.values()),
        vlm_pages=sorted(vlm_pages),
    )


__all__ = [
    "ProcessResult", "PageMeta", "process_pdf",
    "PER_PAGE_CONF_FLOOR", "PER_PAGE_MIN_CHARS",
]
