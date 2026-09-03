"""MiniMax-M3 vision OCR backend for nc-ocr-flow.

One page PNG in → SuryaResult-compatible blocks out (bbox, text, conf).
The model returns plain text without coordinates, so we emit a single
full-page block and let the embedder size it.

Env:
    NC_OCR_MINIMAX_KEY      API key (or NC_OCR_MINIMAX_KEY_FILE)
    NC_OCR_MINIMAX_URL      default https://api.minimax.io/v1
    NC_OCR_MINIMAX_MODEL    default MiniMax-M3
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .surya_client import SuryaBlock, SuryaResult

log = logging.getLogger(__name__)

MINIMAX_URL = os.environ.get("NC_OCR_MINIMAX_URL", "https://api.minimax.io/v1").rstrip("/")
MINIMAX_MODEL = os.environ.get("NC_OCR_MINIMAX_MODEL", "MiniMax-M3")
PROMPT = (
    "Transcribe ALL text on this document page exactly as printed, "
    "preserving line structure. The document may be in Russian or English. "
    "Output ONLY the transcription, no commentary."
)

OCR_PROMPT_TOKEN_COST = 1500  # ~image tokens per page at 150dpi (for metrics only)


def _read_key() -> str:
    val = os.environ.get("NC_OCR_MINIMAX_KEY")
    if val:
        return val
    path = os.environ.get("NC_OCR_MINIMAX_KEY_FILE")
    if path:
        return Path(path).read_text().strip()
    return ""


class MiniMaxError(RuntimeError):
    pass


def ocr_page_minimax(png_bytes: bytes) -> SuryaResult:
    """Transcribe a page PNG via MiniMax-M3 vision chat API.

    Returns a SuryaResult with ONE block covering the full page (the API
    gives text without bboxes); the embedder scales it to page size.
    """
    key = _read_key()
    if not key:
        raise MiniMaxError("NC_OCR_MINIMAX_KEY not set")

    b64 = base64.b64encode(png_bytes).decode("ascii")
    body = json.dumps({
        "model": MINIMAX_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        "max_tokens": 8000,
    }).encode()

    req = Request(
        f"{MINIMAX_URL}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=180) as resp:
            data = json.load(resp)
    except HTTPError as exc:
        raise MiniMaxError(f"minimax HTTP {exc.code}: {exc.read()[:200]}") from exc
    except URLError as exc:
        raise MiniMaxError(f"minimax unreachable: {exc.reason}") from exc

    usage = data.get("usage", {})
    log.info("minimax usage: prompt=%s completion=%s",
             usage.get("prompt_tokens"), usage.get("completion_tokens"))

    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    # reasoning block if present (M3 emits it)
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    text = text.strip()

    if not text:
        raise MiniMaxError("minimax returned empty transcription")

    # Single full-page block; page geometry uses the actual PNG pixel size,
    # approximated via the render DPI known by the caller (200).
    # We report width/height as PNG pixel dims so scale_x/y == 1.0 in embed.
    from PIL import Image
    import io
    w, h = Image.open(io.BytesIO(png_bytes)).size
    return SuryaResult(
        blocks=[SuryaBlock(bbox=(0.0, 0.0, float(w), float(h)),
                           text=text, confidence=0.99, label="minimax")],
        page_width=float(w),
        page_height=float(h),
    )
