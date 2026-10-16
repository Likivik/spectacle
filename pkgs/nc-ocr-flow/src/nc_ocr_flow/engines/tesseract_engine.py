"""Tesseract-only whole-document OCR engine.

Cheap tier: runs ``ocrmypdf`` once over the whole PDF. Per-page VLM
fallback is intentionally absent — callers wanting per-page escalation
should use the ``minimax`` engine instead.

Born-digital handling: uses ``--redo-ocr`` so ocrmypdf replaces the
text layer on every page (genuine digital text is preserved by ocrmypdf's
character-level re-extraction, broken OCR layers are replaced). This
aligns tesseract with the google and minimax engines, which always
write a fresh text layer regardless of whether the input has one.

This engine is the historical "fast lane"; it does no handwriting
escalation (that is minimax's job).
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

_OCR_TIMEOUT_S = 600


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
      l2_pages    = {}   (no handwriting escalation)
    """
    pdf_path = str(pdf_path)
    out_path = Path(output_pdf) if output_pdf else Path(tempfile.mkdtemp()) / "tess.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tess_pages = _run_ocrmypdf_tesseract(pdf_path, str(out_path))

    # tesseract OCRs every page (ocrmypdf --redo-ocr rewrites or adds
    # the text layer on all of them), so its billable pages match
    # tess_pages. webhook_server counts billable pages from
    # result["vlm_pages"], so we set vlm_pages here too — keeping the
    # cross-engine contract that every engine reports its billable
    # page indices in vlm_pages.
    return _orch.ProcessResult(
        output_pdf=str(out_path),
        page_results=[],   # tesseract writes a text layer directly into the PDF
        engine_used=ENGINE_NAME,
        tess_pages=tess_pages,
        vlm_pages=tess_pages,
        vlm_failed_pages=[],
        l2_pages={},
    )


# --- ocrmypdf invocation ---------------------------------------------------


def _run_ocrmypdf_tesseract(input_pdf: str, output_pdf: str) -> list[int]:
    """Invoke ocrmypdf with tesseract; return the list of pages touched.

    Uses ``--redo-ocr`` so the text layer is replaced on every page
    (genuine born-digital text is re-extracted, broken OCR layers are
    replaced — same end-state as the google and minimax engines).
    """
    cmd = [
        "ocrmypdf",
        "--language", "rus+eng",
        "--redo-ocr",
        "--output-type", "pdf",
        "--clean",
        input_pdf,
        output_pdf,
    ]
    log.info("ocrmypdf (tesseract-only): %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=_OCR_TIMEOUT_S)
    except FileNotFoundError:
        raise RuntimeError("ocrmypdf not installed (apt: ocrmypdf)")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
        raise RuntimeError(f"ocrmypdf failed: {stderr.strip()}") from exc
    except subprocess.TimeoutExpired as exc:
        stderr = (exc.stderr or b"").decode(errors="replace") if exc.stderr else ""
        raise RuntimeError(
            f"ocrmypdf failed/timed out after {_OCR_TIMEOUT_S}s: {stderr.strip()}"
        ) from exc

    # With --redo-ocr every page has its text layer replaced or added —
    # record all of them as tesseract pages for provenance. We do
    # NOT pre-scan the input for born-digital pages just to feed a
    # log line anymore: the old ``_born_digital_pages`` walked the
    # whole document only to log "(replaced) vs (from scratch)" and
    # its result was otherwise discarded (tess_pages is range(total)
    # either way). The full-document scan was a real cost on big
    # multi-hundred-page inputs.
    total = _page_count(input_pdf)
    tess_pages = list(range(total))
    log.info("ocrmypdf (tesseract): %d total pages", total)
    return tess_pages


def _page_count(pdf_path: str) -> int:
    import fitz
    with fitz.open(pdf_path) as doc:
        return len(doc)


__all__ = ["process_pdf", "ENGINE_NAME"]