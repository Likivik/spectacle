"""Tesseract-only whole-document OCR engine.

Cheap tier: runs ``ocrmypdf`` once over the whole PDF. Per-page VLM
fallback is intentionally absent — callers wanting per-page escalation
should use the ``minimax`` engine instead.

Born-digital detection: if a page already has >20 chars of extractable
text, it is left untouched (ocrmypdf with ``--skip-text`` does the
same in practice). Pages that tesseract finds nothing on also stay
text-less — use a real OCR engine if you need them filled in.

This engine is the historical "fast lane"; it does NOT touch the L2
writingtype router (handwriting escalation belongs to minimax).
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from nc_ocr_flow import ocr as _orch

log = logging.getLogger(__name__)

ENGINE_NAME = "tesseract"

_BORN_DIGITAL_MIN_CHARS = 20  # copied from ocr's constant


# --- Public entry point ----------------------------------------------------


def process_pdf(pdf_path: str | os.PathLike,
                output_pdf: str | os.PathLike | None = None,
                **_unused) -> "_orch.ProcessResult":
    """OCR a whole PDF with tesseract only.

    Returns ``ocr.ProcessResult`` with:
      engine_used = "tesseract"
      tess_pages  = list of 0-indexed page numbers that received a
                    tesseract layer (i.e. non born-digital pages).
      vlm_pages   = []   (no per-page VLM tier in this engine)
      l2_pages    = {}   (no writingtype escalation)
    """
    pdf_path = str(pdf_path)
    out_path = Path(output_pdf) if output_pdf else Path(tempfile.mkdtemp()) / "tess.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tess_pages = _run_ocrmypdf_tesseract(pdf_path, str(out_path))

    return _orch.ProcessResult(
        output_pdf=str(out_path),
        page_results=[],   # tesseract writes a text layer directly into the PDF
        engine_used=ENGINE_NAME,
        tess_pages=tess_pages,
        vlm_pages=[],
        vlm_failed_pages=[],
        l2_pages={},
    )


# --- ocrmypdf invocation ---------------------------------------------------


def _run_ocrmypdf_tesseract(input_pdf: str, output_pdf: str) -> list[int]:
    """Invoke ocrmypdf with tesseract; return the list of OCR'd page indexes.

    Uses ``--skip-text`` so born-digital pages aren't re-OCR'd. The
    ocrmypdf CLI does not report per-page skip stats; we infer from
    the output PDF's extractable-text length compared to the input.
    """
    pre_born = _born_digital_pages(input_pdf)

    cmd = [
        "ocrmypdf",
        "--language", "rus+eng",
        "--skip-text",
        "--output-type", "pdf",
        "--clean",
        input_pdf,
        output_pdf,
    ]
    log.info("ocrmypdf (tesseract-only): %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except FileNotFoundError:
        raise RuntimeError("ocrmypdf not installed (apt: ocrmypdf)")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
        raise RuntimeError(f"ocrmypdf failed: {stderr.strip()}") from exc

    # OCR'd pages = total pages minus the born-digital ones.
    total = _page_count(input_pdf)
    tess_pages = [i for i in range(total) if i not in pre_born]
    return tess_pages


def _born_digital_pages(pdf_path: str) -> set[int]:
    """Return the set of 0-indexed pages with >20 chars of text already."""
    import fitz  # PyMuPDF
    out: set[int] = set()
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            if len(page.get_text().strip()) > _BORN_DIGITAL_MIN_CHARS:
                out.add(i)
    return out


def _page_count(pdf_path: str) -> int:
    import fitz
    with fitz.open(pdf_path) as doc:
        return len(doc)


__all__ = ["process_pdf", "ENGINE_NAME"]