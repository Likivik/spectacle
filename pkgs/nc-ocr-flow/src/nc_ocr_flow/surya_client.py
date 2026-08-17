"""HTTP client for Surya OCR server (runs on serenity GPU host)."""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

SURYA_URL = os.environ.get("NC_OCR_SURYA_URL", "http://serenity:8084")


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


__all__ = ["SuryaBlock", "SuryaResult", "ocr_page", "SURYA_URL"]
