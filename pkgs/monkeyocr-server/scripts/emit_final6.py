#!/usr/bin/env python3
"""MonkeyOCRv2 canonical artifact emitter for final6 (and friends).

Reads the MonkeyOCR server output (layouts: [{bbox, label, content}]) and emits
the canonical bakeoff-gemini artifact triple per page:

  out/<model>/<file_key>/p<N>.json  - {blocks:[{text,bbox,label}]}
  out/<model>/<file_key>/p<N>.md    - markdown rendering in reading order
  out/<model>/<file_key>/p<N>_layout.pdf - layout visualization (bbox overlay)

Coordinates are in PNG pixels (monkey_server already converts from 0-1000
normalized space at the server boundary, so we pass them through unchanged).

Reads pages from pre-rasterized PNGs at <bakeoff>/pages/<file_key>/p-N.png or
fresh-renders from the source PDF when the raster is missing.

Usage:
  python3 emit_final6.py [file_key]   # default: final6-pristine
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except Exception:
    requests = None  # type: ignore[assignment]
try:
    import fitz  # noqa: F401 - only needed if PNGs must be re-rendered
except Exception:
    fitz = None  # type: ignore[assignment]

BAKEOFF = Path("/var/lib/hermes/.hermes/cache/documents/bakeoff-gemini")
SRC = Path("/var/lib/hermes/.hermes/cache/documents/ocrmatrix5")
PAGES = BAKEOFF / "pages"
OUT_MODEL = BAKEOFF / "out" / "monkeyocrv2-official"

MONKEY_URL = os.environ.get("NC_OCR_MONKEY_URL", "http://serenity:8086")
TIMEOUT = int(os.environ.get("NC_OCR_MONKEY_TIMEOUT", "600"))

FILES = {
    "final6-pristine": "final6-pristine-m3.pdf",
    "egrn": "egrn-m3.pdf",
    "mo4521": "mo4521-m3.pdf",
}


def render_page_png(pdf: Path, page_idx_1: int) -> bytes:
    """Render a 1-based page to PNG bytes at 200 DPI (matches other artifacts)."""
    import fitz
    doc = fitz.open(str(pdf))
    page = doc[page_idx_1 - 1]
    pix = page.get_pixmap(dpi=200)
    return pix.tobytes("png")


def load_page_png(pdf: Path, page_idx_1: int, file_key: str) -> bytes:
    """Reuse pre-rasterized PNG if present, else render fresh."""
    pre = PAGES / file_key / f"p-{page_idx_1}.png"
    if pre.exists():
        return pre.read_bytes()
    return render_page_png(pdf, page_idx_1)


def call_monkey(png_bytes: bytes) -> dict:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    r = requests.post(
        f"{MONKEY_URL}/parse",
        json={"image_b64": b64},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def normalize_blocks(layouts: list[dict]) -> list[dict]:
    """Convert monkey_server layouts -> canonical bakeoff blocks format.

    Drops empty-content blocks (Picture/caption-only). Preserves order so the
    layout-driven reading order from upstream is not reshuffled.
    """
    out = []
    for b in layouts or []:
        text = (b.get("content") or "").strip()
        bbox = b.get("bbox")
        label = b.get("label", "Text")
        if not text:
            continue
        if not bbox or len(bbox) != 4:
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in bbox)
        except (TypeError, ValueError):
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        out.append({
            "text": text,
            "bbox": [int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))],
            "label": str(label),
        })
    return out


def render_markdown(blocks: list[dict]) -> str:
    """Render blocks to markdown in upstream reading order."""
    lines = []
    for b in blocks:
        label = (b.get("label") or "Text").lower()
        text = b.get("text", "").rstrip()
        if label == "title":
            lines.append(f"# {text}\n")
        elif label == "section-header":
            lines.append(f"## {text}\n")
        elif label == "formula":
            lines.append(f"$${text}$$\n")
        elif label == "table":
            lines.append(text + "\n")
        else:
            lines.append(text + "\n")
    return "\n".join(lines)


def render_layout_pdf(png_bytes: bytes, blocks: list[dict], out_path: Path,
                       page_w: int, page_h: int) -> None:
    """Overlay bbox rectangles on a copy of the page PNG; save as PDF."""
    from PIL import Image, ImageDraw, ImageFont
    import fitz

    img = Image.open(__import__("io").BytesIO(png_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/run/current-system/sw/share/X11/fonts/DejaVuSans.ttf", 14
        )
    except Exception:
        font = ImageFont.load_default()

    palette = [
        (255, 0, 0), (0, 128, 0), (0, 0, 255), (255, 128, 0),
        (128, 0, 255), (0, 128, 255), (200, 0, 100), (0, 200, 100),
    ]
    # bbox coords are in PNG pixels of the original render; img is the same
    # render so coordinates line up.
    for i, b in enumerate(blocks):
        x0, y0, x1, y1 = b["bbox"]
        color = palette[i % len(palette)]
        draw.rectangle([x0, y0, x1, y1], outline=color, width=3)
        draw.text((x0 + 4, max(0, y0 - 16)),
                  f"{i+1}:{b.get('label','Text')}", fill=color, font=font)

    doc = fitz.open()
    rect = fitz.Rect(0, 0, page_w, page_h)
    page = doc.new_page(width=page_w, height=page_h)
    # Render PIL img into a fresh pixmap at the same size, then insert
    tmp_png = out_path.with_suffix(".tmp.png")
    img.save(tmp_png)
    page.insert_image(rect, filename=str(tmp_png))
    tmp_png.unlink(missing_ok=True)
    doc.save(str(out_path))
    doc.close()


def emit_file(file_key: str, model: str = "monkeyocrv2-official",
              page_limit: int | None = None) -> dict:
    src = SRC / FILES[file_key]
    if not src.exists():
        raise FileNotFoundError(f"source PDF missing: {src}")
    import fitz
    doc = fitz.open(str(src))
    n_pages = len(doc)
    pages_to_process = list(range(1, n_pages + 1))
    if page_limit is not None:
        pages_to_process = pages_to_process[:page_limit]

    out_dir = BAKEOFF / "out" / model / file_key
    out_dir.mkdir(parents=True, exist_ok=True)

    timings = []
    total_blocks = 0
    for n in pages_to_process:
        t0 = time.time()
        png = load_page_png(src, n, file_key)
        render_w, render_h = __import__("PIL.Image", fromlist=["Image"]).open(
            __import__("io").BytesIO(png)
        ).size
        resp = call_monkey(png)
        elapsed = time.time() - t0
        layouts = resp.get("layouts") or []
        blocks = normalize_blocks(layouts)
        total_blocks += len(blocks)
        # Emit JSON
        (out_dir / f"p{n}.json").write_text(
            json.dumps({"blocks": blocks, "source": "monkeyocrv2-official",
                        "page_w": render_w, "page_h": render_h,
                        "elapsed_s": resp.get("elapsed_s")},
                       ensure_ascii=False, indent=2)
        )
        # Emit MD
        (out_dir / f"p{n}.md").write_text(render_markdown(blocks), encoding="utf-8")
        # Emit layout viz PDF
        render_layout_pdf(png, blocks, out_dir / f"p{n}_layout.pdf",
                          render_w, render_h)
        timings.append((n, elapsed, len(blocks)))
        print(f"  p{n}: {elapsed:.1f}s, {len(blocks)} blocks", flush=True)

    (out_dir / "timings.tsv").write_text(
        "page\telapsed_s\tn_blocks\n" + "\n".join(
            f"{p}\t{e:.2f}\t{b}" for p, e, b in timings
        ) + "\n"
    )
    return {"file_key": file_key, "pages": len(pages_to_process),
            "total_blocks": total_blocks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file_key", nargs="?", default="final6-pristine")
    ap.add_argument("--model", default="monkeyocrv2-official")
    ap.add_argument("--limit", type=int, default=None,
                    help="only process first N pages (debug)")
    args = ap.parse_args()
    try:
        health = requests.get(f"{MONKEY_URL}/health", timeout=5).json()
        print(f"monkey health: {health}")
    except Exception as exc:
        print(f"WARN: monkey server unreachable: {exc}", file=sys.stderr)
    result = emit_file(args.file_key, args.model, page_limit=args.limit)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
