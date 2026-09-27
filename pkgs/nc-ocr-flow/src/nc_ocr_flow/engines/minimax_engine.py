"""MiniMax-M3 (vision LLM) per-page OCR engine.

Tier-3 / escalation engine: walks the PDF page-by-page, renders each
page to a PNG at 200 dpi, and asks MiniMax-M3 to transcribe it via
tool-use with structured blocks.

Why per-page and not whole-doc?

  M3 is a generative LLM, not a layout-aware OCR engine. It produces
  blocks for what it sees; per-page lets us (a) parallelize with the
  parent process if desired, (b) re-embed the text layer page-by-page
  via the orchestrator's ``_embed_ocr_text``, and (c) clearly mark
  failed pages for triage in the PDF metadata.

Env:

  NC_OCR_MINIMAX_KEY      API key (or NC_OCR_MINIMAX_KEY_FILE)
  NC_OCR_MINIMAX_URL      default https://api.minimax.io/v1
  NC_OCR_MINIMAX_MODEL    default MiniMax-M3
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nc_ocr_flow.ocr_models import OcrBlock, OcrResult

log = logging.getLogger(__name__)

ENGINE_NAME = "minimax"

MINIMAX_URL = os.environ.get(
    "NC_OCR_MINIMAX_URL", "https://api.minimax.io/v1"
).rstrip("/")
MINIMAX_MODEL = os.environ.get("NC_OCR_MINIMAX_MODEL", "MiniMax-M3")

# Blocks with conf below this are flagged in PDF metadata for review.
LOW_CONF_FLOOR = 0.70

PROMPT = (
    "You are an OCR engine. Transcribe ALL text on this document page "
    "exactly as printed, preserving reading order. The document may be "
    "in Russian or English, and may contain stamps, signatures, and "
    "handwritten notes. Call the write_ocr_blocks tool with every "
    "text region."
)

OCR_TOOLS = [{
    "type": "function",
    "function": {
        "name": "write_ocr_blocks",
        "description": "Write the OCR result as structured blocks in reading order.",
        "parameters": {
            "type": "object",
            "properties": {
                "blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["header", "text", "table", "handwritten",
                                         "signature", "stamp", "picture", "formula"],
                            },
                            "bbox": {
                                "type": "array",
                                "items": {"type": "number"},
                                "description": "Normalized [x1,y1,x2,y2], 0-1000",
                            },
                            "text": {"type": "string"},
                            "conf": {"type": "number"},
                        },
                        "required": ["type", "bbox", "text", "conf"],
                    },
                }
            },
            "required": ["blocks"],
        },
    },
}]

# Approximate prompt/image token cost per page at 200dpi (metrics only)
OCR_PROMPT_TOKEN_COST = 1500


# --- Public entry point ----------------------------------------------------


class MiniMaxError(RuntimeError):
    pass


def process_pdf(pdf_path: str | os.PathLike,
                output_pdf: str | os.PathLike | None = None,
                **_unused) -> "_orch.ProcessResult":
    """OCR each page of the PDF via MiniMax-M3 and embed text layer."""
    from nc_ocr_flow import ocr as _orch

    pdf_path = str(pdf_path)
    out_path = Path(output_pdf) if output_pdf else Path(tempfile.mkdtemp()) / "mm.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import fitz

    page_results: list[OcrResult] = []
    vlm_pages: list[int] = []
    vlm_failed: list[int] = []

    src = fitz.open(pdf_path)
    try:
        for page_idx in range(len(src)):
            png_bytes = _render_page_png_bytes(src, page_idx, dpi=200)
            try:
                res = ocr_page_minimax(png_bytes)
            except MiniMaxError as exc:
                log.warning("minimax failed on page %d: %s", page_idx, exc)
                vlm_failed.append(page_idx)
                res = OcrResult(blocks=[], page_width=0.0, page_height=0.0)

            page_results.append(res)
            vlm_pages.append(page_idx)

        # Embed text layer + save.
        for page_idx, res in enumerate(page_results):
            if res.blocks:
                _orch._embed_ocr_text(src, page_idx, res)
        src.saveIncr()  # no-op for our temp output — orchestrator will save
    finally:
        src.close()

    return _orch.ProcessResult(
        output_pdf=str(out_path),
        page_results=page_results,
        engine_used=ENGINE_NAME,
        tess_pages=[],
        vlm_pages=vlm_pages,
        vlm_failed_pages=vlm_failed,
        l2_pages={},
    )


# --- Per-page API ----------------------------------------------------------


def ocr_page_minimax(png_bytes: bytes) -> OcrResult:
    """OCR one PNG page via MiniMax-M3 with tool-call structured output.

    If the tool call is missing or unparseable, falls back to a plain-
    transcription single-block mode (full-page bbox).
    """
    from PIL import Image

    w, h = Image.open(io.BytesIO(png_bytes)).size

    body = {
        "model": MINIMAX_MODEL,
        "messages": [_user_message(png_bytes, PROMPT)],
        "tools": OCR_TOOLS,
        "tool_choice": {"type": "function", "function": {"name": "write_ocr_blocks"}},
        "max_tokens": 8000,
    }
    data = _chat(body)

    usage = data.get("usage", {})
    log.info(
        "minimax usage: prompt=%s completion=%s reasoning=%s",
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
    )

    msg = (data.get("choices") or [{}])[0].get("message", {})
    tool_calls = msg.get("tool_calls") or []
    blocks: list[OcrBlock] = []
    if tool_calls:
        try:
            args_json = tool_calls[0]["function"]["arguments"]
            blocks = _blocks_from_toolcall(args_json, w, h)
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            log.warning("minimax tool-call parse failed (%s); falling back", exc)

    if blocks:
        log.info("minimax structured: %d blocks", len(blocks))
        return OcrResult(blocks=blocks, page_width=float(w), page_height=float(h))

    # --- Fallback: plain transcription, single full-page block ---
    if tool_calls:
        retry_body = {
            "model": MINIMAX_MODEL,
            "messages": [_user_message(png_bytes, (
                "Transcribe ALL text on this document page exactly as printed, "
                "preserving line structure. The document may be in Russian or "
                "English. Output ONLY the transcription, no commentary."
            ))],
            "max_tokens": 8000,
        }
        data = _chat(retry_body)
        usage = data.get("usage", {})
        log.info(
            "minimax fallback usage: prompt=%s completion=%s",
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )

    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    text = text.strip()

    if not text:
        raise MiniMaxError("minimax returned empty transcription")

    return OcrResult(
        blocks=[OcrBlock(
            bbox=(0.0, 0.0, float(w), float(h)),
            text=text,
            confidence=0.99,
            label="minimax-plain",
        )],
        page_width=float(w),
        page_height=float(h),
    )


# --- Helpers ----------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")


def _html_table_to_text(html: str) -> str:
    """Convert <table> HTML to plain searchable text (row lines, | separators)."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I)
    lines = []
    for row in rows:
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, flags=re.S | re.I)
        cells = [_TAG_RE.sub("", c).strip() for c in cells]
        cells = [_WS_RE.sub(" ", c) for c in cells]
        lines.append(" | ".join(c for c in cells if c))
    return "\n".join(lines)


def _blocks_from_toolcall(args_json: str, png_w: int, png_h: int) -> list[OcrBlock]:
    """Parse tool-call arguments into OcrBlocks.

    bboxes are normalized 0-1000 → scale to PNG pixel dims so the
    embedder's scale_x/scale_y (page_pts / png_px) work unchanged
    with page_width=png_w.
    """
    args = json.loads(args_json)
    raw_blocks = args.get("blocks") or []
    blocks: list[OcrBlock] = []
    for b in raw_blocks:
        text = str(b.get("text") or "").strip()
        if not text:
            continue
        if str(b.get("type", "")).lower() == "table":
            if "<table" in text.lower():
                text = _html_table_to_text(text)
        bbox = b.get("bbox") or [0, 0, 1000, 1000]
        if len(bbox) != 4:
            bbox = [0, 0, 1000, 1000]
        x0 = float(bbox[0]) / 1000.0 * png_w
        y0 = float(bbox[1]) / 1000.0 * png_h
        x1 = float(bbox[2]) / 1000.0 * png_w
        y1 = float(bbox[3]) / 1000.0 * png_h
        try:
            conf = float(b.get("conf", 0.9))
        except (TypeError, ValueError):
            conf = 0.9
        label = str(b.get("type", "text")).lower()
        blocks.append(OcrBlock(
            bbox=(x0, y0, x1, y1),
            text=text,
            confidence=conf,
            label=label,
        ))
    return blocks


def _read_key() -> str:
    val = os.environ.get("NC_OCR_MINIMAX_KEY")
    if val:
        return val
    path = os.environ.get("NC_OCR_MINIMAX_KEY_FILE")
    if path:
        return Path(path).read_text().strip()
    return ""


def _chat(body: dict) -> dict:
    key = _read_key()
    if not key:
        raise MiniMaxError("NC_OCR_MINIMAX_KEY not set")
    req = Request(
        f"{MINIMAX_URL}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=180) as resp:
            return json.load(resp)
    except HTTPError as exc:
        raise MiniMaxError(f"minimax HTTP {exc.code}: {exc.read()[:200]}") from exc
    except URLError as exc:
        raise MiniMaxError(f"minimax unreachable: {exc.reason}") from exc


def _user_message(png_bytes: bytes, prompt: str) -> dict:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": prompt},
        ],
    }


def _render_page_png_bytes(doc, page_idx: int, dpi: int = 200) -> bytes:
    """Render one PDF page to PNG bytes (200 dpi default).

    Mirrors the orchestrator's _render_page_png but operates on an
    already-opened fitz.Document so the same doc is reused for the
    embed step (saves re-parsing).
    """
    pix = doc[page_idx].get_pixmap(dpi=dpi)
    return pix.tobytes("png")


__all__ = [
    "process_pdf", "ENGINE_NAME", "ocr_page_minimax",
    "MiniMaxError", "LOW_CONF_FLOOR",
]