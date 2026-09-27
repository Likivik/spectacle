"""Shared OCR result model used by all engines in nc-ocr-flow.

Every engine (google, tesseract, minimax) produces pages as a list of
``OcrBlock``s wrapped in an ``OcrResult`` carrying the source page
dimensions. Engines can be invoked independently and the orchestrator
embeds whichever it picks into the PDF text layer.

Field semantics (used by ``engines/<name>_engine`` and the embedder):

  bbox            (x0, y0, x1, y1) in **PNG-image pixel coordinates** of
                  the page rendered at 200 dpi (the same PNG bytes the
                  engine was fed). The orchestrator's ``_embed_ocr_text``
                  scales these to PDF points via the page size.
  text            Per-block transcription.
  confidence      0-1 engine self-reported confidence (best-effort).
                  Surfaces in the PDF metadata for triage.
  label           Engine-specific block type, e.g. ``"text"``, ``"header"``,
                  ``"table"``, ``"handwritten"``, ``"picture"``,
                  ``"google-word"``. The orchestrator does NOT interpret
                  the label, just propagates it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OcrBlock:
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in PNG pixels
    text: str
    confidence: float
    label: str


@dataclass(frozen=True)
class OcrResult:
    blocks: list[OcrBlock]
    page_width: float   # PNG image width in pixels
    page_height: float  # PNG image height in pixels


__all__ = ["OcrBlock", "OcrResult"]