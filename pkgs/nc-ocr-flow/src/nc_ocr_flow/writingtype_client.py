"""WritingtypeAPI DenseNet-121 handwriting detector for nc-ocr-flow.

L2 page classifier: handwritten / typewritten / combination (ONNX, CPU,
~20-40ms/page). Bake-off on our real pages: 7.5/9 vs ocrsieve 4.5/9 —
wins on photographed akts with handwritten dates and plans with
handwritten annotations; stamps correctly stay "typewritten".

Model: https://github.com/DALAI-project/WritingtypeAPI (Apache-2.0)
Provisioned via environment.etc."nc-ocr/writing_type_v1.onnx".

Env:
    NC_OCR_WRITINGTYPE_MODEL   default /etc/static/nc-ocr/writing_type_v1.onnx
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MODEL_PATH = os.environ.get(
    "NC_OCR_WRITINGTYPE_MODEL",
    "/etc/static/nc-ocr/writing_type_v1.onnx",
)

# Class order per WritingtypeAPI DenseNet output
LABELS = ("handwritten", "typewritten", "combination")

# Page routes to the VLM tier if p(handwritten)+p(combination) exceeds this.
# Calibrated on bake-off set: pure-print pages scored <=0.26, mixed pages
# >=0.34; stamps stayed <0.01. 0.30 sits in the gap.
ESCALATION_THRESHOLD = 0.30

_SESSION = None


@dataclass(frozen=True)
class WritingTypeResult:
    label: str            # handwritten | typewritten | combination
    confidence: float
    probs: dict[str, float]
    escalate: bool        # True → route page to the VLM (M3) tier
    latency_ms: float


def _get_session():
    global _SESSION
    if _SESSION is None:
        import onnxruntime as ort
        _SESSION = ort.InferenceSession(
            MODEL_PATH, providers=["CPUExecutionProvider"]
        )
    return _SESSION


def classify_page_writingtype(png_bytes: bytes) -> WritingTypeResult:
    """Classify one page PNG (bytes) for handwriting content."""
    import io
    import time

    import numpy as np
    from PIL import Image

    t0 = time.time()
    sess = _get_session()
    inp = sess.get_inputs()[0]
    ishape = inp.shape
    # DenseNet-121 expects 224x224; read actual dims when static
    h = ishape[2] if isinstance(ishape[2], int) else 224
    w = ishape[3] if isinstance(ishape[3], int) else 224

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB").resize((w, h), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    a = (a - mean) / std
    a = a.transpose(2, 0, 1)[None]

    logits = sess.run(None, {inp.name: a})[0]
    # softmax
    probs = np.exp(logits - logits.max(axis=-1, keepdims=True))
    probs = probs / probs.sum(axis=-1, keepdims=True)
    probs = probs.flatten()

    pd = {LABELS[i]: float(probs[i]) for i in range(min(len(LABELS), len(probs)))}
    top = max(pd, key=lambda k: pd[k])
    escalate = pd.get("handwritten", 0.0) + pd.get("combination", 0.0) >= ESCALATION_THRESHOLD
    dt = (time.time() - t0) * 1000
    return WritingTypeResult(
        label=top,
        confidence=pd[top],
        probs=pd,
        escalate=escalate,
        latency_ms=dt,
    )


def model_available() -> bool:
    return Path(MODEL_PATH).exists()


__all__ = [
    "WritingTypeResult", "classify_page_writingtype",
    "model_available", "ESCALATION_THRESHOLD", "MODEL_PATH",
]
