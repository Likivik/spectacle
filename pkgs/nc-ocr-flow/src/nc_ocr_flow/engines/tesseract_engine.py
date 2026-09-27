"""Tesseract-only whole-document OCR engine.

Cheap tier: runs ``ocrmypdf`` once over the whole PDF. Per-page VLM
fallback is intentionally absent — callers wanting per-page escalation
should use the ``minimax`` engine instead.

Born-digital handling: uses ``--redo-ocr`` so ocrmypdf replaces the
text layer on every page (genuine digital text is preserved by ocrmypdf's
character-level re-extraction, broken OCR layers are replaced). This
aligns tesseract with the google and minimax engines, which always
write a fresh text layer regardless of whether the input has one.

The pre-scan of pages with extractable text is retained for the
``tess_pages`` accounting (pages where a text layer was replaced or
added) — pages without any text are the ones tesseract actively
OCR'd from scratch; pages with existing text had that text re-extracted
or replaced. Use the original pages-needing-OCR distinction at the
service layer (pdf_classify / ``_needs_ocr_decision``) to decide
whether to run this engine at all.

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
    """Invoke ocrmypdf with tesseract; return the list of pages touched.

    Uses ``--redo-ocr`` so the text layer is replaced on every page
    (genuine born-digital text is re-extracted, broken OCR layers are
    replaced — same end-state as the google and minimax engines). The
    ocrmypdf CLI does not report per-page re-OCR stats, so we infer
    ``tess_pages`` from the pre-scan: pages that already had >20 chars
    of text had their layer replaced or re-extracted; pages with no
    text were OCR'd from scratch — every page counts as a tesseract
    page for provenance.
    """
    pre_born = _born_digital_pages(input_pdf)

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
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except FileNotFoundError:
        raise RuntimeError("ocrmypdf not installed (apt: ocrmypdf)")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
        raise RuntimeError(f"ocrmypdf failed: {stderr.strip()}") from exc

    # With --redo-ocr every page has its text layer replaced or added —
    # record all of them as tesseract pages for provenance. The
    # ``pre_born`` set is retained for visibility: pages with
    # pre-existing text had that text layer replaced (possibly bad OCR
    # replaced with a cleaner layer); the rest were OCR'd from scratch.
    total = _page_count(input_pdf)
    tess_pages = list(range(total))
    log.info(
        "ocrmypdf (tesseract): %d total pages, %d had pre-existing text "
        "(replaced), %d OCR'd from scratch",
        total, len(pre_born), total - len(pre_born),
    )
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