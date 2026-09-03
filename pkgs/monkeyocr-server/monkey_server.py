#!/usr/bin/env python3
"""MonkeyOCRv2-B HTTP server on serenity GPU (HF transformers, no vLLM).

POST /parse  {image_b64: <png>}  ->
  {"layouts": [{"bbox": [x0,y0,x1,y1], "label": ..., "content": ...}, ...],
   "page_width": W, "page_height": H, "elapsed_s": N}

Coordinates are normalized 0-1000 (model native), converted here to PNG
pixels. Single-model, single-GPU, sequential; queueing happens client-side.
"""
import base64
import io
import json
import sys
import time

import torch
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

MP = "/tmp/monkey_repo/model_weight/MonkeyOCRv2-B-Parsing"

print("loading model...", flush=True)
model = AutoModelForCausalLM.from_pretrained(
    MP, dtype=torch.float16, device_map="cuda", trust_remote_code=True,
)
model.eval()
processor = AutoProcessor.from_pretrained(MP, trust_remote_code=True)
print("model ready", flush=True)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="monkeyocrv2-b server")


class ParseReq(BaseModel):
    image_b64: str


def _run_parse(img: Image.Image) -> tuple[list[dict], float]:
    t0 = time.time()
    # TASK_PROMPTS style: layout + recognition end-to-end
    msgs = [{"role": "user", "content": [
        {"type": "image", "image": img},
        {"type": "text", "text": "Parse the document."},
    ]}]
    text = processor.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    enc = processor(text=[text], images=[img], return_tensors="pt").to("cuda")
    with torch.inference_mode():
        out = model.generate(**enc, max_new_tokens=4096, do_sample=False)
    gen = out[0][enc["input_ids"].shape[1]:]
    resp = processor.decode(gen, skip_special_tokens=True)
    return resp, time.time() - t0


@app.get("/health")
def health():
    return {"status": "ok", "model": "MonkeyOCRv2-B-Parsing", "device": "cuda"}


@app.post("/parse")
def parse(req: ParseReq):
    try:
        img = Image.open(io.BytesIO(base64.b64decode(req.image_b64))).convert("RGB")
    except Exception as exc:
        raise HTTPException(400, f"bad image: {exc}")

    w, h = img.size
    raw, elapsed = _run_parse(img)

    # The model emits JSON blocks; be tolerant to fences/prose.
    layouts = _extract_layouts(raw)
    # bbox 0-1000 normalized -> pixels
    for b in layouts:
        bb = b.get("bbox")
        if isinstance(bb, list) and len(bb) == 4:
            b["bbox"] = [
                bb[0] / 1000.0 * w, bb[1] / 1000.0 * h,
                bb[2] / 1000.0 * w, bb[3] / 1000.0 * h,
            ]
    return {
        "layouts": layouts,
        "page_width": w,
        "page_height": h,
        "elapsed_s": round(elapsed, 2),
        "raw_first_200": raw[:200] if not layouts else None,
    }


def _extract_layouts(raw: str) -> list[dict]:
    import re
    import ast as _ast
    s = raw.strip()
    # The model emits PYTHON-style reprs (single quotes) — try json, then ast.
    def _parse(txt):
        txt = txt.strip()
        if not txt:
            return None
        for loader in (json.loads, _ast.literal_eval):
            try:
                return loader(txt)
            except Exception:
                continue
        return None

    candidates = []
    m2 = re.search(r"```(?:json|python)?\s*(\[.*?\])\s*```", s, re.S)
    if m2:
        candidates.append(m2.group(1))
    m = re.search(r"\[\s*\{.*\}\s*\]", s, re.S)
    if m:
        candidates.append(m.group(0))
    for c in candidates:
        data = _parse(c)
        if isinstance(data, list):
            return [b for b in data if isinstance(b, dict) and "bbox" in b]
    # stream-parse: handles nested quotes + truncation; tolerate single quotes
    out = []
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
                    b = _parse(frag)
                    if not isinstance(b, dict):
                        try:
                            b = _parse(frag.replace("'", '"'))
                        except Exception:
                            b = None
                    if isinstance(b, dict) and "bbox" in b:
                        out.append(b)
    return out


if __name__ == "__main__":
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8086)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
