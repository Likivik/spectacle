"""ocrmypdf wrapper: embed text layer, olmOCR-v2 fallback via XMP.

API:
    process_pdf(input_pdf, output_pdf) -> ProcessResult

Pipeline:
  1. ocrmypdf --skip-text --tsv --sidecar text.txt  (embeds text layer, writes tsv)
  2. Parse tsv → per-page 10th-percentile confidence
  3. Pages with conf_p10 < 70 or chars < 40 → VLM fallback
  4. VLM extracts text via OpenAI multimodal chat endpoint
  5. VLM text written into PDF XMP metadata (survives rename/move)
  6. nc-mcp picks up XMP for Qdrant embedding
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pikepdf

log = logging.getLogger(__name__)

# Per-page quality gates (research-backed)
PER_PAGE_CONF_FLOOR = 70.0
PER_PAGE_MIN_CHARS = 40

# VLM endpoint (serenity llama.cpp with olmOCR-v2 model)
OLMOCR_ENDPOINT = os.environ.get("NC_OCR_OLMOCR_ENDPOINT", "http://serenity:8083")

# XMP namespace for our custom fields (registered with pdfxmp)
XMP_NS_NC = "http://likivik.example/nc-ocr/1.0/"
XMP_PREFIX = "nc"

XMP_KEYS = {
    "vlm_text": f"{{{XMP_NS_NC}}}vlm-text",
    "vlm_pages": f"{{{XMP_NS_NC}}}vlm-pages",
    "vlm_timestamp": f"{{{XMP_NS_NC}}}vlm-timestamp",
    "confidence_floor": f"{{{XMP_NS_NC}}}confidence-floor",
}


@dataclass
class PageMeta:
    page_idx: int
    confidence_p10: float
    char_count: int
    needs_vlm: bool = False


@dataclass
class ProcessResult:
    output_pdf: str
    tesseract_pages: list[int] = field(default_factory=list)
    vlm_pages: list[int] = field(default_factory=list)
    xmp_written: bool = False


# --- ocrmypdf invocation ----------------------------------------------------

def _run_ocrmypdf(input_pdf: Path, output_pdf: Path, tsv_path: Path) -> None:
    """Run ocrmypdf with --skip-text --tsv."""
    cmd = [
        "ocrmypdf",
        "--skip-text",
        "--rotate-pages",
        "--deskew",
        "--clean",
        "--language", "rus+eng",
        "--tsv", str(tsv_path),
        "--sidecar", str(tsv_path.with_suffix(".txt")),
        "--output-type", "pdf",
        str(input_pdf),
        str(output_pdf),
    ]
    log.info("running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)


def _parse_tsv(tsv_path: Path) -> dict[int, PageMeta]:
    """Parse ocrmypdf TSV → per-page {conf_p10, char_count}."""
    pages: dict[int, PageMeta] = {}
    if not tsv_path.exists():
        return pages

    with tsv_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        per_page_confs: dict[int, list[float]] = {}
        per_page_chars: dict[int, int] = {}

        for row in reader:
            try:
                page_num = int(row.get("page_num", 0))
                level = int(row.get("level", 0))
                if level != 5:  # only word-level
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


# --- VLM (olmOCR-v2) call ---------------------------------------------------

def _render_page_as_png(pdf_path: Path, page_idx: int) -> bytes:
    """Render a single PDF page to PNG bytes."""
    # Use pdftoppm (poppler) — already a transitive dep of ocrmypdf
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(
            ["pdftoppm", "-png", "-r", "200", "-f", str(page_idx + 1),
             "-l", str(page_idx + 1), str(pdf_path), tmp_path.stem],
            check=True, capture_output=True, timeout=60,
            cwd=tmp_path.parent,
        )
        # pdftoppm appends "-N.png" — find the actual file
        png_files = list(tmp_path.parent.glob(f"{tmp_path.stem}-*.png"))
        if not png_files:
            raise FileNotFoundError(f"pdftoppm produced no output for page {page_idx}")
        return png_files[0].read_bytes()
    finally:
        for f in tmp_path.parent.glob(f"{tmp_path.stem}*.png"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _olmocr_ocr_page(png_bytes: bytes) -> str:
    """Call serenity llama.cpp /v1/chat/completions with OpenAI multimodal format."""
    import base64
    import requests

    b64 = base64.b64encode(png_bytes).decode("ascii")
    resp = requests.post(
        f"{OLMOCR_ENDPOINT}/v1/chat/completions",
        json={
            "model": "olmocr-v2",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                        {"type": "text", "text": "Extract all text preserving layout. Return plain text."},
                    ],
                }
            ],
            "temperature": 0.0,
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# --- XMP write --------------------------------------------------------------

def _write_xmp(pdf_path: Path, vlm_text: dict[int, str], confidence_floor: float) -> bool:
    """Write VLM-extracted text into PDF XMP metadata.

    Survives rename/move/delete-copy because XMP lives inside the PDF.
    nc-mcp reads these fields via pikepdf.open()['/Metadata'].
    """
    if not vlm_text:
        return False

    try:
        with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
            # Get existing XMP or create new
            with pdf.open_metadata(set_pikepdf_as_editor=True) as meta:
                meta[XMP_KEYS["vlm_text"]] = "\n\n".join(
                    f"--- Page {idx + 1} ---\n{text}"
                    for idx, text in sorted(vlm_text.items())
                )
                meta[XMP_KEYS["vlm_pages"]] = json.dumps(sorted(vlm_text.keys()))
                meta[XMP_KEYS["vlm_timestamp"]] = datetime.now(timezone.utc).isoformat()
                meta[XMP_KEYS["confidence_floor"]] = str(confidence_floor)
            pdf.save()
        return True
    except Exception as exc:
        log.warning("XMP write failed for %s: %s", pdf_path, exc)
        return False


# --- main entry point -------------------------------------------------------

def process_pdf(input_path: str | Path, output_path: str | Path | None = None) -> ProcessResult:
    """Run the full OCR pipeline on a single PDF.

    Args:
        input_path: Source PDF
        output_path: Destination PDF (default: input_path with .ocr suffix)

    Returns:
        ProcessResult with output path, list of VLM-fallback pages, XMP status.
    """
    input_pdf = Path(input_path)
    output_pdf = (
        Path(output_path) if output_path else input_pdf.with_suffix(".ocr.pdf")
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        tsv_path = tmp / "ocr.tsv"

        _run_ocrmypdf(input_pdf, output_pdf, tsv_path)
        page_meta = _parse_tsv(tsv_path)

    flagged = [m for m in page_meta.values() if _needs_vlm(m)]
    vlm_text: dict[int, str] = {}

    for meta in flagged:
        try:
            png = _render_page_as_png(output_pdf, meta.page_idx)
            vlm_text[meta.page_idx] = _olmocr_ocr_page(png)
        except Exception as exc:
            log.warning("VLM failed for page %d: %s", meta.page_idx, exc)

    xmp_written = _write_xmp(output_pdf, vlm_text, PER_PAGE_CONF_FLOOR)

    return ProcessResult(
        output_pdf=str(output_pdf),
        tesseract_pages=sorted(m.page_idx for m in page_meta.values()),
        vlm_pages=sorted(vlm_text.keys()),
        xmp_written=xmp_written,
    )


__all__ = ["ProcessResult", "PageMeta", "process_pdf", "PER_PAGE_CONF_FLOOR", "PER_PAGE_MIN_CHARS"]
