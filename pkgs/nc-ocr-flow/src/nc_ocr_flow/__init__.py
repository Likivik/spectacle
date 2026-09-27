"""Nextcloud OCR pipeline: three-engine architecture.

Engines (selected via ``NC_OCR_ENGINE`` env var or
``process_pdf(..., engine=...)`` arg):

  - ``"google"``    — Google Cloud Vision DOCUMENT_TEXT_DETECTION (default)
  - ``"tesseract"`` — tesseract via ocrmypdf, no VLM fallback
  - ``"minimax"``   — MiniMax-M3 vision LLM with structured tool-use blocks

The shared data model (per-page blocks with bboxes + text + confidence)
lives in :mod:`nc_ocr_flow.ocr_models`.
"""
from __future__ import annotations

__version__ = "0.3.0"