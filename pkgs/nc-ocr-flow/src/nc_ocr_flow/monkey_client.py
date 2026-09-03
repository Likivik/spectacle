"""MonkeyOCRv2-B HTTP client (serenity GPU parsing server, port 8086).

Tier-2 OCR: typed/printed pages. Returns SuryaResult-compatible blocks
(bbox in PNG pixels) that feed the same embed path as Surya/M3.

Server: POST /parse {image_b64} -> {layouts: [{bbox, label, content}],
page_width, page_height, elapsed_s}. Bboxes arrive already converted to
PNG pixel coordinates.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

MONKEY_URL = os.environ.get("NC_OCR_MONKEY_URL", "http://serenity:8086")
TIMEOUT = int(os.environ.get("NC_OCR_MONKEY_TIMEOUT", "300"))


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
    """Send PNG to MonkeyOCR server, get back layout blocks with text."""
    endpoint = url or MONKEY_URL
    b64 = base64.b64encode(png_bytes).decode("ascii")
    resp = requests.post(
        f"{endpoint}/parse",
        json={"image_b64": b64},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    blocks = []
    for b in data.get("layouts", []):
        content = (b.get("content") or "").strip()
        if not content:
            continue  # Picture/caption-only blocks carry no text layer
        blocks.append(SuryaBlock(
            bbox=tuple(b["bbox"]),
            text=content,
            confidence=1.0,  # Monkey emits no per-block confidence
            label=b.get("label", "Text"),
        ))
    return SuryaResult(
        blocks=blocks,
        page_width=data.get("page_width", 0),
        page_height=data.get("page_height", 0),
    )


def health(url: str | None = None) -> bool:
    try:
        r = requests.get(f"{url or MONKEY_URL}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


__all__ = ["SuryaBlock", "SuryaResult", "ocr_page", "health", "MONKEY_URL"]
