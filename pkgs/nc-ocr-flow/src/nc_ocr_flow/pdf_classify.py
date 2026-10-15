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

Two-tier decision
-----------------
``pdf_inspector`` exposes a fast detector (``detect_pdf``) that samples
content streams without extracting text, and a deep analyser
(``process_pdf``) that fully extracts text and runs text-quality
heuristics (cmap gaps, U+FFFD density, dollar-as-space, cipher-garble
letter statistics). The fast path is what every "is this born-digital"
check should use — it's cheap (~10–50 ms) and correct for the common
cases. The deep path costs the full extraction pass.

The bug this guards against: the fast path can misclassify a PDF whose
text layer is *visible* on the page but whose character decoding is
broken (Type0/Identity-H font with no ToUnicode CMap, a deliberately
wrong ToUnicode mapping, dollar-as-space substitution, cipher-garble
ASCII output, …). Because no text was actually extracted, the fast path
reports ``text_based`` with ``has_encoding_issues=False`` and the file
would be silently skipped — never OCR'd. The OCRmyPDF case (invisible
text layer, rendering mode 3) is already caught by the fast path as
``image_based`` with reason ``invisible_text_layer``; the blind spot
is specifically the *visible-garbage-text* case.

So the decision is two-tier:

1. Always run the fast ``detect_pdf`` first.
2. If it returns ``text_based`` *and* does not flag encoding issues
   (i.e. the verdict is "skip OCR"), promote the verdict by calling
   ``process_pdf`` as a tie-breaker. Either of these from the deep
   path overrides the skip:
     - ``has_encoding_issues`` is true (the text-quality heuristics
       fired: U+FFFD density, dollar-as-space, cipher-garble letter
       statistics, etc.)
     - ``ocr_reasons_by_page`` is non-empty (pdf_inspector has
       recorded a concrete per-page reason such as
       ``suspected_garbled_text`` or ``invisible_text_layer``)
3. If the deep call raises ``OcrRequired`` (or any "this PDF must be
   OCR'd" exception) we treat it as needs_ocr=True. Any other failure
   is treated conservatively as needs_ocr=True with a logged warning —
   the wrapper's stated philosophy is that false negatives (skipping a
   file that needed OCR) are worse than false positives (running OCR
   on a clean born-digital PDF, which ``ocrmypdf --redo-ocr`` handles
   fine).

The heuristic fallback remains the last resort when pdf_inspector is
not installed or every code path raises.

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

    # Tier 1: fast detector. Cheap (~10–50 ms); classifies by sampling
    # content streams and doesn't extract text.
    try:
        fast = pdf_inspector.detect_pdf(p)
    except Exception as exc:
        log.warning(
            "pdf_classify: pdf_inspector.detect_pdf failed (%s); "
            "falling back to heuristic",
            exc,
        )
        return _heuristic_classify(p)

    fast_pdf_type = getattr(fast, "pdf_type", None) or "unknown"
    fast_confidence = float(getattr(fast, "confidence", 0.0) or 0.0)
    fast_has_encoding_issues = bool(getattr(fast, "has_encoding_issues", False))

    # Fast-path decision: not a clean text_based PDF, OR one whose
    # encoding is broken → OCR. Note: detect_pdf always reports
    # has_encoding_issues=False (it doesn't extract text), so the only
    # case where fast would skip is (text_based, no encoding issues).
    fast_needs_ocr = (fast_pdf_type != "text_based") or fast_has_encoding_issues

    # Most files already have a definitive verdict here. Only fall
    # through to the deep analyser when the fast path is about to let
    # a file be skipped — that's the specific blind spot described in
    # the module docstring.
    if fast_needs_ocr:
        return {
            "needs_ocr": True,
            "pdf_type": fast_pdf_type,
            "confidence": fast_confidence,
            "has_encoding_issues": fast_has_encoding_issues,
        }

    # Tier 2: deep analyser. Pays the full extraction cost (slower,
    # pulls in ONNX if anything downstream asks). Only invoked when the
    # fast verdict would otherwise let the file be skipped.
    try:
        deep = pdf_inspector.process_pdf(p)
    except Exception as deep_exc:
        exc_name = type(deep_exc).__name__
        # pdf_inspector raises OcrRequired (or analogues) when the deep
        # pass decides the file genuinely cannot be decoded without
        # OCR. Honour that as needs_ocr=True without further triage.
        # Anything else (corrupt PDF, native lib error, …) — be
        # conservative: route to OCR rather than risk skipping a file
        # that needs it.
        if "OcrRequired" in exc_name or "OcrNeeded" in exc_name:
            log.info(
                "pdf_classify: pdf_inspector.process_pdf signalled OCR "
                "required (%s) — treating as needs_ocr=True",
                deep_exc,
            )
            return {
                "needs_ocr": True,
                "pdf_type": "unknown",
                "confidence": fast_confidence,
                "has_encoding_issues": True,
            }
        log.warning(
            "pdf_classify: pdf_inspector.process_pdf failed (%s); "
            "treating as needs_ocr=True conservatively",
            deep_exc,
        )
        return {
            "needs_ocr": True,
            "pdf_type": fast_pdf_type,
            "confidence": fast_confidence,
            "has_encoding_issues": True,
        }

    deep_has_encoding_issues = bool(getattr(deep, "has_encoding_issues", False))
    deep_reasons = list(getattr(deep, "ocr_reasons_by_page", None) or [])
    deep_confidence = float(
        getattr(deep, "confidence", 0.0) or 0.0
    )

    # The deep pass wins when it surfaces a *specific* signal that the
    # text layer is unreliable. ``ocr_reasons_by_page`` is only
    # populated when pdf_inspector has decided a concrete reason to
    # route the page to OCR; ``pages_needing_ocr`` alone is NOT a
    # reliable signal here — pdf_inspector populates it for every
    # text-bearing page by default, so we'd over-OCR every born-digital
    # file. ``has_encoding_issues`` covers the text-quality heuristics
    # (U+FFFD density, dollar-as-space, cipher-garble).
    deep_says_ocr = deep_has_encoding_issues or bool(deep_reasons)

    return {
        "needs_ocr": bool(deep_says_ocr),
        "pdf_type": fast_pdf_type,
        "confidence": deep_confidence or fast_confidence,
        "has_encoding_issues": deep_has_encoding_issues,
    }


def _heuristic_classify(path: str) -> dict:
    """Conservative fallback: needs_ocr=True unless page text is long enough.

    Uses PyMuPDF (already a hard dep of nc-ocr-flow). All pages must
    pass the threshold; otherwise we err on the side of OCR.

    Additionally flags ``has_encoding_issues`` (and therefore routes to
    OCR) when the extracted text is obviously garbled: high U+FFFD
    density, long combining-diacritic runs, or the dollar-as-space
    pattern from broken ToUnicode CMaps. This mirrors pdf_inspector's
    text-quality heuristics at a coarser level so the heuristic
    fallback doesn't repeat the same blind spot as the fast path when
    pdf-inspector itself is unavailable.
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
        all_text_parts: list[str] = []
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
                page_text = page.get_text()
                all_text_parts.append(page_text)
                text_len = len(page_text.strip())
                if text_len < _HEURISTIC_MIN_CHARS:
                    any_below = True
                    break
        # If every page has plenty of text, the file is plausibly
        # born-digital; but first sanity-check that the text we
        # extracted actually looks like language rather than mojibake.
        has_encoding_issues = False
        if not any_below:
            has_encoding_issues = _looks_garbled("".join(all_text_parts))
        # If encoding issues were found, route to OCR even though the
        # page had plenty of characters.
        needs_ocr = any_below or has_encoding_issues
        return {
            "needs_ocr": needs_ocr,
            "pdf_type": "text_based" if not needs_ocr else "scanned",
            "confidence": 0.5,
            "has_encoding_issues": has_encoding_issues,
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


def _looks_garbled(text: str) -> bool:
    """Cheap text-quality check used by the heuristic fallback.

    Returns True if any of these red flags trip:
      - More than 2% of characters are U+FFFD replacement markers.
      - A run of 6+ consecutive combining diacritics (U+0300–U+036F).
      - The dollar-as-space pattern from broken ToUnicode CMaps
        (more than half of all '$' are flanked by letters).
    """
    if not text:
        return False
    n = len(text)

    # 1. U+FFFD density
    repl = text.count("\ufffd")
    if n >= 50 and repl / n > 0.02:
        return True

    # 2. Long combining-diacritic run
    combining_run = 0
    longest_run = 0
    for ch in text:
        if 0x0300 <= ord(ch) <= 0x036F:
            combining_run += 1
            if combining_run > longest_run:
                longest_run = combining_run
            if longest_run >= 6:
                return True
        else:
            combining_run = 0

    # 3. Dollar-as-space pattern
    total_dollars = text.count("$")
    if total_dollars > 10:
        letter_dollar_letter = 0
        for i in range(1, n - 1):
            if text[i] == "$":
                prev = text[i - 1]
                nxt = text[i + 1]
                if prev.isalpha() and nxt.isalpha():
                    letter_dollar_letter += 1
        if letter_dollar_letter * 2 > total_dollars:
            return True

    return False


__all__ = ["classify_pdf"]