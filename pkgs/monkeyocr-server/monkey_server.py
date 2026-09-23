#!/usr/bin/env python3
"""MonkeyOCRv2-B HTTP server on serenity GPU (HF transformers, no vLLM).

POST /parse  {image_b64: <png>}  ->
  {"layouts": [{"bbox": [x0,y0,x1,y1], "label": ..., "content": ...}, ...],
   "page_width": W, "page_height": H, "elapsed_s": N}

Official semantics from upstream:
- https://github.com/Yuliang-Liu/MonkeyOCR/blob/main/parse.py
- https://github.com/Yuliang-Liu/MonkeyOCR/blob/main/magic_pdf/model/batch_analyze_llm.py
- https://github.com/Yuliang-Liu/MonkeyOCRv2/blob/main/parsing/train/README.md
  (prompt/format recipes for v2-Parsing unified model)

Pipeline:
  1) layout: 1MP-cap resize -> layout prompt -> ordered blocks
  2) per-block: clamp/swap/expand bbox -> crop -> label-routed prompt
     (text-family / formula / table) with longest-edge<=1600 resize
  3) tolerant parser handles JSON / Python repr / fragmented outputs
  4) picture blocks: no recognition (model skips)
  5) /artifacts endpoint returns canonical final6 artifacts (JSON/MD/HTML
     /reading-order/summary) per the task spec
"""
import argparse
import ast as _ast
import base64
import io
import json
import os
import re
import sys
import time
from typing import Any

from PIL import Image, ImageFile  # noqa: E402

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Allow importing this module without booting the HF model (tests / tooling).
# Set MONKEY_LAZY_LOAD=1 to skip the module-level model init.
_LAZY = os.environ.get("MONKEY_LAZY_LOAD", "0") == "1"
model = None
processor = None

def _ensure_model():
    """Lazily load the HF model. Returns (model, processor)."""
    global model, processor
    if model is not None and processor is not None:
        return model, processor
    import torch  # local import: torch not needed for pure-helper tests
    from transformers import AutoModelForCausalLM, AutoProcessor
    print("loading model...", flush=True)
    model_path = "/tmp/monkey_repo/model_weight/MonkeyOCRv2-B-Parsing"
    model = AutoModelForCausalLM.from_pretrained(
        model_path, dtype=torch.float16, device_map="cuda", trust_remote_code=True,
    )
    model.eval()
    processor = AutoProcessor.from_pretrained(
        model_path, trust_remote_code=True,
    )
    print("model ready", flush=True)
    return model, processor


if not _LAZY:
    _ensure_model()

# --- Official prompts from upstream MonkeyOCR / MonkeyOCRv2 README ---------
# Text-family labels (no Markdown in v2-Parsing recipe).
TEXT_PROMPT = "Please output the text content from the image."
# Formula recognition.
FORMULA_PROMPT = "Please write out the expression of the formula in the image using LaTeX format."
# Table recognition (HTML).
TABLE_PROMPT = "This is the image of a table. Please output the table in HTML format."
# Layout detection: official prompt from upstream batch_analyze_llm.py /
# MonkeyOCRv2 layout instruction format. "Reading order" instructs the model
# to emit blocks in human reading sequence; we further validate/sort below.
LAYOUT_PROMPT = (
    "Please output the categories and coordinates of the document elements "
    "in reading order."
)
# Direct fallback when no valid layout blocks exist (upstream split_pages path).
DIRECT_TEXT_PROMPT = "Please output the text content from the image."

# --- Official label set (upstream parse.py TASK_INSTRUCTIONS / v2 README) ----
TEXT_LABELS = {
    "Text", "Title", "Section-header", "Caption", "Footnote",
    "List-item", "Page-header", "Page-footer", "Reference",
}
FORMULA_LABELS = {"Formula", "Equation"}
TABLE_LABELS = {"Table"}
PICTURE_LABELS = {"Picture", "Figure"}

# Upstream crop_paste_x/y defaults (magic_pdf/model/sub_modules/model_utils.py)
CROP_PAD_DEFAULT = 50
# Longest edge cap for per-block recognition (PaddleX/PP-DocLayout resize policy)
MAX_BLOCK_EDGE = 1600
# Layout image cap (upstream resize to fit in memory on small VRAM)
MAX_LAYOUT_EDGE = 1280


def _resize_for_layout(img: Image.Image) -> Image.Image:
    """Cap longest edge so layout detection stays tractable on small VRAM."""
    w, h = img.size
    longest = max(w, h)
    if longest <= MAX_LAYOUT_EDGE:
        return img
    scale = MAX_LAYOUT_EDGE / float(longest)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def _resize_for_recognition(img: Image.Image) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= MAX_BLOCK_EDGE:
        return img
    scale = MAX_BLOCK_EDGE / float(longest)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def _generate(img: Image.Image, prompt: str, max_new_tokens: int = 4096) -> str:
    """Single inference round; do_sample=False to match upstream deterministic mode."""
    m, proc = _ensure_model()
    import torch  # local: not needed for pure-helper tests
    msgs = [{"role": "user", "content": [
        {"type": "image", "image": img},
        {"type": "text", "text": prompt},
    ]}]
    text = proc.apply_chat_template(
        msgs, tokenize=False, add_generation_prompt=True,
    )
    enc = proc(text=[text], images=[img], return_tensors="pt").to("cuda")
    with torch.inference_mode():
        out = m.generate(
            **enc, max_new_tokens=max_new_tokens, do_sample=False,
        )
    gen = out[0][enc["input_ids"].shape[1]:]
    return proc.decode(gen, skip_special_tokens=True).strip()


# --- Official bbox clamp/swap/expand ----------------------------------------
def _norm_to_px(bbox: list[float], w: int, h: int) -> tuple[int, int, int, int]:
    """Convert 0-1000 normalized coords (model native) to pixel ints and clamp.

    Matches upstream crop_img's expectations: integer pixel coords in [0, dim].
    """
    x0, y0, x1, y1 = bbox
    x0 = max(0, min(w, int(round(x0 / 1000.0 * w))))
    y0 = max(0, min(h, int(round(y0 / 1000.0 * h))))
    x1 = max(0, min(w, int(round(x1 / 1000.0 * w))))
    y1 = max(0, min(h, int(round(y1 / 1000.0 * h))))
    return x0, y0, x1, y1


def _swap_and_expand(
    bbox: list[float], w: int, h: int, expand_px: int = CROP_PAD_DEFAULT,
) -> tuple[int, int, int, int]:
    """Clamp to image bounds, swap inverted axes, and expand by pad pixels.

    Upstream crop_img in magic_pdf/model/sub_modules/model_utils.py creates a
    white canvas with 50px pad on each side, then pastes the crop offset by
    (pad, pad). For table blocks (label 'Table' upstream / category_id==5 in
    PaddleX), the pad is 0; for all others, 50. Mirrors that here.
    """
    x0, y0, x1, y1 = _norm_to_px(bbox, w, h)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if expand_px > 0:
        x0 = max(0, x0 - expand_px)
        y0 = max(0, y0 - expand_px)
        x1 = min(w, x1 + expand_px)
        y1 = min(h, y1 + expand_px)
    return x0, y0, x1, y1


def _pad_for_label(label: str) -> int:
    """Upstream rule: tables skip pad (category_id 5 -> crop_paste 0)."""
    if label in TABLE_LABELS:
        return 0
    return CROP_PAD_DEFAULT


# --- P1: asymmetric crop padding -------------------------------------------
# Official core_runner does a bare image.crop() with NO padding; the layout
# decoder emits tight 0..1000 boxes that clip Cyrillic line starts (dropped
# first char: 'Добро' -> 'бро'). We expand asymmetric: more on the left
# (line start / ascender overhang) and top, less right/bottom. Re-clamped.
CROP_PAD_LEFT = 60
CROP_PAD_RIGHT = 30
CROP_PAD_TOP = 30
CROP_PAD_BOTTOM = 30


def _swap_and_expand_asym(
    bbox: list[float], w: int, h: int,
    left: int = CROP_PAD_LEFT, right: int = CROP_PAD_RIGHT,
    top: int = CROP_PAD_TOP, bottom: int = CROP_PAD_BOTTOM,
) -> tuple[int, int, int, int]:
    """Clamp/swap, then expand asymmetrically (Russian line-start overhang)."""
    x0, y0, x1, y1 = _norm_to_px(bbox, w, h)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    x0 = max(0, x0 - left)
    y0 = max(0, y0 - top)
    x1 = min(w, x1 + right)
    y1 = min(h, y1 + bottom)
    return x0, y0, x1, y1


# --- P1: IoU / containment suppression -------------------------------------
# Upstream does NO overlap suppression after layout decode; the generative
# layout LLM emits duplicated/nested blocks (100%-nested same-label boxes).
# We sort by area desc and drop any later box that overlaps an earlier one
# beyond thresholds, or is fully contained in a same-label earlier box.
def _iou(a: list[int], b: list[int]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def _containment(a: list[int], b: list[int]) -> float:
    """Fraction of box a that is inside box b (area(a∩b) / area(a))."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    area_a = (ax1 - ax0) * (ay1 - ay0)
    if area_a <= 0:
        return 0.0
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    return inter / area_a if inter > 0 else 0.0


def _suppress_overlaps(
    blocks: list[dict], iou_thr: float = 0.30, contain_thr: float = 0.85,
) -> list[dict]:
    """Drop duplicated/nested layout blocks. Sorts by area desc so a large
    parent that contains many small children is kept, children dropped (or
    the small overlapper dropped in favor of the larger earlier box)."""
    if not blocks:
        return blocks
    # First normalize bboxes to pixels so IoU is meaningful (already done by
    # caller), copy work list with area index.
    idx = sorted(
        range(len(blocks)),
        key=lambda i: (blocks[i]["bbox"][2] - blocks[i]["bbox"][0])
        * (blocks[i]["bbox"][3] - blocks[i]["bbox"][1]),
        reverse=True,
    )
    kept: list[dict] = []
    for i in idx:
        cur = blocks[i]
        drop = False
        for k in kept:
            if _iou(cur["bbox"], k["bbox"]) >= iou_thr:
                drop = True
                break
            if cur["label"] == k["label"] and _containment(cur["bbox"], k["bbox"]) >= contain_thr:
                drop = True
                break
        if not drop:
            kept.append(cur)
    # Restore model emission order (kept were appended in area-desc order).
    order = {id(b): j for j, b in enumerate(kept)}
    return sorted(kept, key=lambda b: order[id(b)])


# --- P1: literal junk-block filter ------------------------------------------
# The generative layout LLM hallucinates filler text (e.g. a full English
# pangram 'The quick brown fox...') as a Text block on Russian pages. No
# upstream filter exists (official --retry-repeat only catches suffix repeat).
# Drop any block whose text matches a literal blocklist or has zero
# characters from the page alphabet (detect Cyrillic vs Latin).
import unicodedata

_JUNK_PATTERNS = re.compile(
    r"(quick brown fox|lorem ipsum|placeholder|sample text|dolor sit|"
    r"jumps over the lazy|the quick|todo|xxxx+|yyy+|zzz+)", re.I,
)
# We evaluate junk on the RECOGNIZED content AND on the label+the raw layout
# item (which carries no text yet at layout stage). So this filter runs after
# recognition, on block['content'].
def _is_junk_content(text: str) -> bool:
    if not text:
        return True
    if _JUNK_PATTERNS.search(text):
        return True
    # Heuristic: page has heavy Cyrillic; a block whose words are ALL Latin
    # with high confidence of being filler is suspicious. But legit Latin
    # (numbers, units) exists. Only flag full-sentence filler.
    # Collapse whitespace and check word count + marker phrases above.
    return False


def _label_is_textlike(label: str) -> bool:
    return (label or "").lower() in {
        "text", "title", "section-header", "caption", "footnote",
        "list-item", "page-header", "page-footer", "reference", "",
    }


# --- P2: retry-repeat on recognition ---------------------------------------
# Official detect_repeat_token catches suffix repetition of a single
# substring. We combine with a length/repetition heuristic and retry with a
# temperature ramp (upstream core_runner.py:792,932 retry_temperature).

def _is_bad_recognition(text: str) -> bool:
    """True if a recognition result should be considered garbage and retried."""
    if not text or not text.strip():
        return True
    s = text.strip()
    if s.lower() in {"undefined", "none", "null", "[]", "[1,2,3]", "{}", "{'a': 1}", '{"a":1}'}:
        return True
    if _JUNK_PATTERNS.search(s):
        return True
    # suffix repetition of a short token (model collapse)
    if len(s) >= 12:
        half = s[len(s) // 2:]
        if half and s.endswith(half * 2):
            return True
    return False


def _generate_with_retry(img: Image.Image, prompt: str, max_new_tokens: int = 4096,
                         repeats: int = 2) -> str:
    """Try recognition; retry with a temperature ramp when result is garbage.

    Upstream ramps temperature 0.2..0.8 (top_p 0.95) across retries
    (core_runner.py:792,932); we do the same to break collapse loops but
    keep the first attempt deterministic (do_sample=False).
    """
    out = _generate(img, prompt, max_new_tokens=max_new_tokens)
    if not _is_bad_recognition(out):
        return out
    for r in range(1, repeats + 1):
        temp = min(0.2 * (r + 1), 0.8)
        out = _generate_with_temp(
            img, prompt, max_new_tokens=max_new_tokens, temperature=temp,
        )
        if not _is_bad_recognition(out):
            return out
    return out


def _generate_with_temp(img: Image.Image, prompt: str, max_new_tokens: int,
                        temperature: float) -> str:
    """Non-deterministic generation (temperature + top_p 0.95)."""
    import torch  # local: not needed for pure-helper tests
    m, proc = _ensure_model()
    msgs = [{"role": "user", "content": [
        {"type": "image", "image": img}, {"type": "text", "text": prompt},
    ]}]
    text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    enc = proc(text=[text], images=[img], return_tensors="pt").to("cuda")
    with torch.inference_mode():
        out_t = m.generate(
            **enc, max_new_tokens=max_new_tokens, do_sample=True,
            temperature=temperature, top_p=0.95,
        )
    gen = out_t[0][enc["input_ids"].shape[1]:]
    return proc.decode(gen, skip_special_tokens=True).strip()


# --- Tolerant parser: JSON / Python repr / fragmented ---------------------
def _try_loads(txt: str) -> Any:
    txt = txt.strip()
    if not txt:
        return None
    # JSON first (double quotes, escapes); then ast.literal_eval for
    # Python repr (single quotes) which the upstream model emits.
    for loader in (json.loads, _ast.literal_eval):
        try:
            return loader(txt)
        except Exception:
            continue
    return None


def _extract_layouts(raw: str) -> list[dict]:
    """Parse the layout prompt output into [{'bbox': [x0,y0,x1,y1], 'label': ...}, ...]."""
    s = raw.strip()
    candidates: list[str] = []
    # fenced block (```json or ```python)
    m_fence = re.search(r"```(?:json|python)?\s*(\[.*?\])\s*```", s, re.S)
    if m_fence:
        candidates.append(m_fence.group(1))
    # top-level bracketed list
    m_list = re.search(r"\[\s*\{.*\}\s*\]", s, re.S)
    if m_list:
        candidates.append(m_list.group(0))
    for c in candidates:
        data = _try_loads(c)
        if isinstance(data, list):
            return [b for b in data if isinstance(b, dict) and "bbox" in b]
    # stream-parse: tolerate nested quotes + truncation; swap single->double
    # quotes when literal_eval chokes on apostrophes inside English text.
    out: list[dict] = []
    depth = 0
    start = None
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    frag = s[start:i + 1]
                    b = _try_loads(frag)
                    if not isinstance(b, dict):
                        # try forcing JSON quotes
                        try:
                            b = json.loads(frag.replace("'", '"'))
                        except Exception:
                            b = None
                    if isinstance(b, dict) and "bbox" in b:
                        out.append(b)
    return out


def _route_prompt(label: str) -> str:
    if label in FORMULA_LABELS:
        return FORMULA_PROMPT
    if label in TABLE_LABELS:
        return TABLE_PROMPT
    if label in PICTURE_LABELS:
        return ""  # no recognition for pictures
    return TEXT_PROMPT


def _recognize_block(img: Image.Image, label: str) -> str:
    """Crop, resize, route by label, and run the recognition LMM call."""
    prompt = _route_prompt(label)
    if not prompt:
        return ""
    crop = _resize_for_recognition(img)
    return _generate(crop, prompt, max_new_tokens=1024)


# --- Reading-order validation ---------------------------------------------
def _reading_order_score(blocks: list[dict]) -> dict:
    """Top-to-bottom, left-to-right monotonicity score for the block sequence.

    Returns a small dict the /parse endpoint surfaces under "reading_order"
    so callers can detect when the model mis-ordered blocks. We use a simple
    monotonicity check on (y0, x0) — not strict sort, but flags obvious
    out-of-order blocks. The canonical final6 artifact sorts by (y0, x0)
    to provide a stable reading sequence even if the model emitted out of
    order.
    """
    if not blocks:
        return {"ok": True, "violations": 0, "n": 0}
    n = len(blocks)
    pts = [(b["bbox"][1], b["bbox"][0], i) for i, b in enumerate(blocks)]
    sorted_pts = sorted(pts)
    violations = sum(1 for i, (_, _, orig_i) in enumerate(sorted_pts) if orig_i != i)
    return {"ok": violations == 0, "violations": violations, "n": n}


# --- Core parse ------------------------------------------------------------
def _run_parse(img: Image.Image) -> tuple[list[dict], float, str, int]:
    """Single-stage parse: layout detection + per-block recognition.

    Returns ordered blocks (model order) with bbox converted to pixels,
    label, and content (empty for Picture).
    """
    t0 = time.time()
    layout_img = _resize_for_layout(img)
    raw = _generate(layout_img, LAYOUT_PROMPT)
    layouts = _extract_layouts(raw)

    w, h = img.size
    # Convert all layout bboxes to pixel space first (needed for IoU).
    valid = []
    for block in layouts:
        label = block.get("label", "")
        if not isinstance(block.get("bbox"), list) or len(block["bbox"]) != 4:
            continue
        pad = _pad_for_label(label)
        if label in TABLE_LABELS:
            x0, y0, x1, y1 = _swap_and_expand(block["bbox"], w, h, expand_px=0)
        else:
            x0, y0, x1, y1 = _swap_and_expand_asym(block["bbox"], w, h)
        block["bbox"] = [x0, y0, x1, y1]
        block["label"] = label
        valid.append(block)

    # P1: drop duplicated/nested layout boxes before recognition.
    n_raw = len(valid)
    valid = _suppress_overlaps(valid)

    for block in valid:
        label = block["label"]
        if label in PICTURE_LABELS:
            block["content"] = ""
            continue
        x0, y0, x1, y1 = block["bbox"]
        crop = img.crop((x0, y0, x1, y1))
        prompt = _route_prompt(label)
        if not prompt:
            block["content"] = ""
            continue
        content = _generate_with_retry(
            _resize_for_recognition(crop), prompt, max_new_tokens=1024,
        )
        if _is_junk_content(content):
            block["content"] = ""
            block["junk"] = True
            continue
        block["content"] = content
    valid = [b for b in valid if not b.pop("junk", False)]
    return valid, time.time() - t0, raw, n_raw


# --- FastAPI app ------------------------------------------------------------
from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

app = FastAPI(title="monkeyocrv2-b server")


class ParseReq(BaseModel):
    image_b64: str


class ArtifactsReq(BaseModel):
    image_b64: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": "MonkeyOCRv2-B-Parsing", "device": "cuda"}


@app.post("/parse")
def parse(req: ParseReq) -> dict:
    try:
        img = Image.open(io.BytesIO(base64.b64decode(req.image_b64))).convert("RGB")
    except Exception as exc:
        raise HTTPException(400, f"bad image: {exc}")

    w, h = img.size
    layouts, elapsed, raw, n_raw = _run_parse(img)
    order = _reading_order_score(layouts)
    return {
        "layouts": layouts,
        "page_width": w,
        "page_height": h,
        "elapsed_s": round(elapsed, 2),
        "reading_order": order,
        "layout_blocks_raw": n_raw,
        "raw_first_200": raw[:200] if not layouts else None,
    }


# --- Canonical final6 artifacts per page ------------------------------------
def _block_to_md(block: dict) -> str:
    """Render a single block to a Markdown fragment (official semantic)."""
    label = block.get("label", "")
    content = block.get("content", "")
    if label == "Title":
        return f"# {content}\n\n" if content else ""
    if label == "Section-header":
        return f"## {content}\n\n" if content else ""
    if label == "List-item":
        return f"- {content}\n" if content else ""
    if label == "Formula":
        return f"{content}\n\n" if content else ""  # already wrapped in $
    if label == "Table":
        return f"{content}\n\n" if content else ""
    if label == "Picture":
        return ""  # pictures are not part of markdown content
    if label in {"Page-header", "Page-footer"}:
        return f"_{content}_\n\n" if content else ""
    if label == "Footnote":
        return f"[^fn]: {content}\n\n" if content else ""
    return f"{content}\n\n" if content else ""


def _build_markdown(blocks: list[dict]) -> str:
    return "".join(_block_to_md(b) for b in blocks).rstrip() + "\n"


def _build_html(blocks: list[dict], w: int, h: int) -> str:
    """Semantic HTML with bbox coords in data-bbox for layout fidelity."""
    out = [f'<!doctype html><html><head><meta charset="utf-8">'
           f'<title>MonkeyOCR page</title></head><body>']
    out.append(f'<div class="page" data-w="{w}" data-h="{h}">')
    for b in blocks:
        x0, y0, x1, y1 = b.get("bbox", [0, 0, 0, 0])
        label = b.get("label", "")
        content = b.get("content", "")
        esc = (content.replace("&", "&").replace("<", "<")
               .replace(">", ">")) if content else ""
        bbox = f'data-bbox="{x0},{y0},{x1},{y1}"'
        if label == "Title":
            out.append(f'<h1 {bbox}>{esc}</h1>')
        elif label == "Section-header":
            out.append(f'<h2 {bbox}>{esc}</h2>')
        elif label == "List-item":
            out.append(f'<li {bbox}>{esc}</li>')
        elif label == "Formula":
            out.append(f'<p class="formula" {bbox}>{esc}</p>')
        elif label == "Table":
            out.append(f'<div class="table" {bbox}>{esc}</div>')
        elif label == "Picture":
            out.append(f'<figure {bbox}></figure>')
        elif label in {"Page-header", "Page-footer"}:
            tag = "header" if label == "Page-header" else "footer"
            out.append(f'<{tag} {bbox}>{esc}</{tag}>')
        elif label == "Footnote":
            out.append(f'<aside class="footnote" {bbox}>{esc}</aside>')
        else:
            out.append(f'<p {bbox}>{esc}</p>')
    out.append('</div></body></html>')
    return "".join(out)


def _reading_order_blocks(blocks: list[dict]) -> list[dict]:
    """Stable top-to-bottom, left-to-right sequence by (y0, x0)."""
    return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))


def _summary(blocks: list[dict], w: int, h: int) -> dict:
    by_label: dict[str, int] = {}
    for b in blocks:
        lbl = b.get("label", "")
        by_label[lbl] = by_label.get(lbl, 0) + 1
    total_area = sum(
        max(0, b["bbox"][2] - b["bbox"][0]) * max(0, b["bbox"][3] - b["bbox"][1])
        for b in blocks
    )
    page_area = max(1, w * h)
    coverage = round(total_area / page_area, 4)
    order = _reading_order_score(blocks)
    return {
        "block_count": len(blocks),
        "by_label": by_label,
        "coverage": coverage,
        "reading_order": order,
    }


@app.post("/artifacts")
def artifacts(req: ArtifactsReq) -> dict:
    """Return the canonical final6 artifacts in one payload."""
    try:
        img = Image.open(io.BytesIO(base64.b64decode(req.image_b64))).convert("RGB")
    except Exception as exc:
        raise HTTPException(400, f"bad image: {exc}")

    w, h = img.size
    blocks, elapsed, _, _ = _run_parse(img)
    md = _build_markdown(blocks)
    html = _build_html(blocks, w, h)
    ordered = _reading_order_blocks(blocks)
    summary = _summary(blocks, w, h)
    return {
        "layout": [  # layout.json — geometry only (no content)
            {"bbox": b["bbox"], "label": b["label"]}
            for b in blocks
        ],
        "blocks": blocks,        # blocks.json — full per-block detail
        "markdown": md,          # page-N.markdown
        "html": html,            # page-N.html
        "reading_order": ordered,  # reading-order.json
        "summary": summary,      # summary.json
        "page_width": w,
        "page_height": h,
        "elapsed_s": round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8086)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
