"""Document vs photo classifier for uploaded images.

Uses MobileNetV2 ONNX model (CPU, ~100ms) to decide:
  - document → convert to PDF, run OCR pipeline
  - photo → skip (stays in Nextcloud untouched, NOT moved to immich)

API:
    classify(image_path) -> ClassifyResult(is_document, reason)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DOC = "document"
PHOTO = "photo"

# MobileNetV2 input: 224x224 normalized with ImageNet mean/std
_MOBILENET_SIZE = 224
_MOBILENET_MEAN = [0.485, 0.456, 0.406]
_MOBILENET_STD = [0.229, 0.224, 0.225]

_MOBILENET_SESSION = None


@dataclass(frozen=True)
class ClassifyResult:
    is_document: bool
    reason: str  # "mobilenet" | "error:ClassName"


def _get_session():
    global _MOBILENET_SESSION
    if _MOBILENET_SESSION is None:
        import onnxruntime as ort
        model_path = os.environ.get(
            "NC_OCR_MOBILENET_MODEL",
            "/etc/static/nc-ocr/mobilenetv2_doc_photo_quant.onnx",
        )
        _MOBILENET_SESSION = ort.InferenceSession(
            model_path, providers=["CPUExecutionProvider"]
        )
    return _MOBILENET_SESSION


def classify(image_path: str | Path) -> ClassifyResult:
    """Classify image as document or photo.

    Failures default to PHOTO (skip) — false negative is worse than false
    positive because wrongly-OCR'd photos pollute search results.
    """
    path = Path(image_path)
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(path).convert("RGB").resize(
            (_MOBILENET_SIZE, _MOBILENET_SIZE), Image.Resampling.BILINEAR
        )
        arr = np.asarray(img, dtype=np.float32) / 255.0
        arr = (arr - _MOBILENET_MEAN) / _MOBILENET_STD
        arr = arr.transpose(2, 0, 1)[None]  # HWC → NCHW

        sess = _get_session()
        out = sess.run(None, {sess.get_inputs()[0].name: arr.astype(np.float32)})[0]
        is_doc = int(out[0].argmax()) == 0
        return ClassifyResult(is_document=is_doc, reason="mobilenet")

    except Exception as exc:
        log.warning("classifier failed: %s; defaulting to photo", exc)
        return ClassifyResult(is_document=False, reason=f"error:{type(exc).__name__}")


__all__ = ["ClassifyResult", "classify", "DOC", "PHOTO"]
