"""Classifier: 2-stage doc-vs-photo detection.

Stage 1: fast tesseract --psm 11 sparse text pass (CPU, ~500ms).
Stage 2: CLIP L/14 zero-shot via serenity llama.cpp endpoint (only if
         stage 1 was ambiguous).
"""
from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass

import pytesseract
from PIL import Image
from pytesseract import Output

log = logging.getLogger(__name__)

MIN_CHARS = 40
TESSERACT_CONF_FLOOR = 60
CLIP_DOC_THRESHOLD = 0.6

CLIP_ENDPOINT = os.environ.get("NC_OCR_CLIP_ENDPOINT", "http://serenity:8084")
CLIP_MODEL = os.environ.get("NC_OCR_CLIP_MODEL", "clip-l14")


@dataclass
class ClassifyResult:
    is_document: bool
    confidence: float
    reason: str


def _tesseract_quick_pass(image: Image.Image) -> tuple[int, float]:
    """Run pytesseract --psm 11 sparse text mode.

    Returns (char_count, mean_word_confidence).
    """
    img_bytes = io.BytesIO()
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    try:
        data = pytesseract.image_to_data(
            img_bytes,
            output_type=Output.DICT,
            config="--psm 11 --oem 1",
            lang="rus+eng",
        )
    except pytesseract.TesseractError as exc:
        log.warning("tesseract failed: %s", exc)
        return (0, 0.0)

    words = []
    for conf_str, text in zip(data.get("conf", []), data.get("text", [])):
        try:
            conf = float(conf_str)
        except (ValueError, TypeError):
            continue
        if conf < 0 or not text.strip():
            continue
        words.append((conf, text))

    if not words:
        return (0, 0.0)

    char_count = sum(len(t) for _, t in words)
    mean_conf = sum(c for c, _ in words) / len(words)
    return (char_count, mean_conf)


def _clip_classify(image_bytes: bytes) -> float:
    """POST image to CLIP endpoint, return doc-vs-photo probability."""
    import requests

    resp = requests.post(
        f"{CLIP_ENDPOINT}/v1/clip/classify",
        files={"image": ("img.jpg", image_bytes, "image/jpeg")},
        json={
            "labels": ["a photograph of a document", "a photograph"],
            "model": CLIP_MODEL,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("scores", {}).get("a photograph of a document", 0.0)


def classify(image_path: str) -> ClassifyResult:
    with Image.open(image_path) as image:
        char_count, mean_conf = _tesseract_quick_pass(image)
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    if char_count >= MIN_CHARS and mean_conf >= TESSERACT_CONF_FLOOR:
        return ClassifyResult(
            is_document=True,
            confidence=mean_conf / 100.0,
            reason="tesseract_text",
        )

    clip_score = _clip_classify(image_bytes)
    is_doc = clip_score >= CLIP_DOC_THRESHOLD
    return ClassifyResult(
        is_document=is_doc,
        confidence=clip_score,
        reason="clip_doc" if is_doc else "clip_photo",
    )
