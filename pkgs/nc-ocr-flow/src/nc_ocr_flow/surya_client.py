"""HTTP client for Surya OCR server (runs on serenity GPU host).

Two endpoints:

  POST /ocr    — full recognition: blocks with text + bbox.
                 Use ocr_page().

  POST /detect — detection only: line bboxes + 4-corner polygons,
                 no text recognition. Use detect_lines().

The /detect endpoint returns line geometry that the calling code can
pair with text from a separate source (e.g. M3/Gemini) by reading
order — see nc_ocr_flow.line_geometry.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

SURYA_URL = os.environ.get("NC_OCR_SURYA_URL", "http://serenity:8084")


# --- /ocr: recognition -------------------------------------------------------

@dataclass(frozen=True)
class SuryaBlock:
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in image pixels
    text: str
    confidence: float
    label: str


@dataclass(frozen=True)
class SuryaResult:
    blocks: list[SuryaBlock]
    page_width: float
    page_height: float


def ocr_page(png_bytes: bytes, url: str | None = None) -> SuryaResult:
    """Send PNG to Surya server, get back blocks with bboxes + text."""
    endpoint = url or SURYA_URL
    b64 = base64.b64encode(png_bytes).decode("ascii")
    resp = requests.post(
        f"{endpoint}/ocr",
        json={"image_b64": b64},
        timeout=300,
    )
    resp.raise_for_status()
    data = resp.json()
    return SuryaResult(
        blocks=[SuryaBlock(
            bbox=tuple(b["bbox"]),
            text=b["text"],
            confidence=b["confidence"],
            label=b["label"],
        ) for b in data["blocks"]],
        page_width=data["page_width"],
        page_height=data["page_height"],
    )


# --- /detect: line geometry only ---------------------------------------------

# 4-corner polygon in image pixels, clockwise from top-left:
#   [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
# Matches Surya's documented schema (datalab-to/surya README).
LinePolygon = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class DetectionLine:
    """One text line from /detect.

    bbox:   axis-aligned [x0, y0, x1, y1] derived from the polygon.
    polygon: 4-corner clockwise polygon in image pixels (may be None
             if the server omitted it).
    confidence: model confidence (0-1), may be None.
    """
    bbox: tuple[float, float, float, float]
    polygon: LinePolygon | None
    confidence: float | None


@dataclass(frozen=True)
class DetectionResult:
    """All lines on a single page, plus page dimensions."""
    lines: list[DetectionLine]
    page_width: float
    page_height: float


def _polygon_from_json(raw: list[list[float]] | None) -> LinePolygon | None:
    if raw is None:
        return None
    return tuple((float(p[0]), float(p[1])) for p in raw)


def detect_lines(png_bytes: bytes, url: str | None = None) -> DetectionResult:
    """Send PNG to Surya server, get back line geometry only (no text).

    Use this when text comes from a different source (e.g. a VLM like
    M3/Gemini) and you want Surya only for line-localization + reading
    order. Pair the returned lines with text via
    ``nc_ocr_flow.line_geometry``.
    """
    endpoint = url or SURYA_URL
    b64 = base64.b64encode(png_bytes).decode("ascii")
    resp = requests.post(
        f"{endpoint}/detect",
        json={"image_b64": b64},
        timeout=300,
    )
    resp.raise_for_status()
    data = resp.json()
    return DetectionResult(
        lines=[DetectionLine(
            bbox=tuple(line["bbox"]),
            polygon=_polygon_from_json(line.get("polygon")),
            confidence=line.get("confidence"),
        ) for line in data["lines"]],
        page_width=data["page_width"],
        page_height=data["page_height"],
    )


__all__ = [
    # /ocr
    "SuryaBlock", "SuryaResult", "ocr_page",
    # /detect
    "DetectionLine", "DetectionResult", "detect_lines", "LinePolygon",
    # config
    "SURYA_URL",
]
