"""PDF born-digital / OCR-needs classification via ``pdf-inspector``.

Thin wrapper around the Rust-backed ``pdf_inspector`` package, used by
the webhook to decide whether a freshly-uploaded PDF needs OCR at all
(born-digital with a clean text layer → skip).

API:
    classify_pdf(path) -> dict

The wrapper returns a plain dict (instead of pdf_inspector's dataclass)
so callers don't have to import pdf_inspector. If pdf_inspector is not
installed or the call fails for any reason (corrupt PDF, missing
native lib, …), we fall back to a conservative heuristic that says
"needs OCR" unless the PDF already has plenty of extractable text.

The heuristic is intentionally conservative: false negatives (saying
"born digital" when the layer is broken) are worse than false
positives (running OCR on a clean born-digital PDF just overwrites
a fine text layer, which ``ocrmypdf --redo-ocr`` handles fine).
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Page text length (chars) below which we consider the page "empty"
# enough that the whole PDF probably needs OCR. Mirrors the historical
# ``_BORN_DIGITAL_MIN_CHARS`` constant.
_HEURISTIC_MIN_CHARS = 20


def classify_pdf(path: str | Path) -> dict:
    """Classify a PDF: text_based → skip OCR, anything else → OCR it.

    Returns a dict with keys:
        needs_ocr          bool
        pdf_type           str   (text_based | scanned | image_based | mixed | unknown)
        confidence         float
        has_encoding_issues bool

    Falls back to a conservative heuristic (needs_ocr = True unless
    every page has >=20 chars of extractable text) if pdf-inspector is
    not installed or raises.
    """
    p = str(path)

    # Try pdf-inspector first
    try:
        import pdf_inspector  # type: ignore[import-not-found]
    except ImportError:
        log.warning(
            "pdf_classify: pdf-inspector not installed; "
            "falling back to heuristic (needs_ocr=True unless page text "
            "> %d chars)",
            _HEURISTIC_MIN_CHARS,
        )
        return _heuristic_classify(p)

    try:
        # Use detect_pdf to also get has_encoding_issues; classify_pdf
        # is cheaper but doesn't surface that flag.
        result = pdf_inspector.detect_pdf(p)
    except Exception as exc:
        log.warning(
            "pdf_classify: pdf_inspector.detect_pdf failed (%s); "
            "falling back to heuristic",
            exc,
        )
        return _heuristic_classify(p)

    pdf_type = getattr(result, "pdf_type", None) or "unknown"
    confidence = float(getattr(result, "confidence", 0.0) or 0.0)
    has_encoding_issues = bool(getattr(result, "has_encoding_issues", False))
    # needs_ocr is the decision the caller cares about: not a clean
    # text_based PDF, OR one whose encoding is broken.
    needs_ocr = (pdf_type != "text_based") or has_encoding_issues

    return {
        "needs_ocr": needs_ocr,
        "pdf_type": pdf_type,
        "confidence": confidence,
        "has_encoding_issues": has_encoding_issues,
    }


def _heuristic_classify(path: str) -> dict:
    """Conservative fallback: needs_ocr=True unless page text is long enough.

    Uses PyMuPDF (already a hard dep of nc-ocr-flow). All pages must
    pass the threshold; otherwise we err on the side of OCR.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        # No PyMuPDF, no pdf-inspector — the safest bet is "OCR it".
        log.warning(
            "pdf_classify: neither pdf-inspector nor fitz available; "
            "defaulting needs_ocr=True"
        )
        return {
            "needs_ocr": True,
            "pdf_type": "unknown",
            "confidence": 0.0,
            "has_encoding_issues": False,
        }

    try:
        any_below = False
        with fitz.open(path) as doc:
            page_count = len(doc)
            if page_count == 0:
                return {
                    "needs_ocr": True,
                    "pdf_type": "unknown",
                    "confidence": 0.0,
                    "has_encoding_issues": False,
                }
            for page in doc:
                text_len = len(page.get_text().strip())
                if text_len < _HEURISTIC_MIN_CHARS:
                    any_below = True
                    break
        # If every page has plenty of text, assume born-digital; else OCR.
        return {
            "needs_ocr": any_below,
            "pdf_type": "text_based" if not any_below else "scanned",
            "confidence": 0.5,
            "has_encoding_issues": False,
        }
    except Exception as exc:
        log.warning(
            "pdf_classify: heuristic fitz read failed (%s); "
            "defaulting needs_ocr=True",
            exc,
        )
        return {
            "needs_ocr": True,
            "pdf_type": "unknown",
            "confidence": 0.0,
            "has_encoding_issues": False,
        }


__all__ = ["classify_pdf"]