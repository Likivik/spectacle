"""Document orientation classifier (stage-1 of preorientation).

Backed by PP-LCNet_x1_0_doc_ori — a 4-class document-image
orientation classifier published by PaddleOCR (PaddlePaddle).

Reference: paddleocr doc_img_orientation_classification module.
Model card (Top-1 acc 99.06%, 6.7 MB INT8 ONNX):
  https://huggingface.co/PaddleOcrNet/PaddleOcrNet-models
  -> PP-LCNet_x1_0_doc_ori.onnx

Why this model, not Tesseract OSD:
  Empirically Tesseract OSD reports 0.0–1.5 confidence on
  real Russian-scanned PDFs and routinely gets the angle wrong
  (we measured: reported 180° conf 0.14 on a 90° scan, and 90°
  conf 1.56 on a 0° scan — those led to upsidedown or sideways
  OCR). PP-LCNet is content-based and converges on a real
  probability over {0°, 90°, 180°, 270°}.

Inference pipeline (verified empirically on PaddlePaddle/
PP-LCNet_x1_0_doc_ori/inference.yml + measured against rotations
on synthetic test pages):

    1. Resize so the short side = 256, keep aspect (BILINEAR).
    2. Center crop 224×224.
    3. Cast to float32, divide by 255.
    4. (x - mean) / std with mean=[0.485,0.456,0.406],
       std=[0.229,0.224,0.225].  Order is HWC at this point
       (mean/std apply to per-channel RGB).
    5. HWC -> CHW.
    6. Prepend a batch dim -> (1, 3, 224, 224) float32 NCHW.

Output: 4 logits.  Softmax -> 4 probabilities.
Class index -> CCW rotation needed to make the page upright
(PaddleOCR labels are "rotation to make upright, CW"; we
negate them into CCW here — verified empirically against a
30-PDF real-scan sweep):

        0 -> 0°   (already upright)
        1 -> 270° (= 90° CW)
        2 -> 180°
        3 -> 90°  (= 270° CW)

The model file is fetched and packaged by the Nix module
``modules/aspects/server/workflow-ocr/default.nix`` into
``/etc/static/nc-ocr-flow/pp_lcnet_x1_0_doc_ori.onnx`` and
the path is exposed via the env var
``NC_OCR_ORIENTATION_MODEL``. If the file is missing or
onnxruntime isn't installed, this module degrades gracefully
(returns ``None``) and the caller falls back to the OCR
vote / Tesseract OSD path.
"""
from __future__ import annotations

import io
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# Model IO spec (verified).
_INPUT_SIZE = 224
_SHORT_SIDE = 256
_MEAN = (0.485, 0.456, 0.406)
_STD = (0.229, 0.224, 0.225)
# index -> CCW rotation to make page upright.
#
# Verified empirically against a transpose-based (unambiguous CCW)
# rotation series on real scans: for the page needing 270° CCW the
# model's argmax is index 3, and for the one needing 90° CCW it is
# index 1. The previous mapping (0, 270, 180, 90) was inverted for
# the 90/270 pair — it made pages come out 180° off.
_INDEX_TO_CCW = (0, 90, 180, 270)

DEFAULT_MODEL_PATH = "/etc/static/nc-ocr-flow/pp_lcnet_x1_0_doc_ori.onnx"
ENV_VAR = "NC_OCR_ORIENTATION_MODEL"


# --- Session cache (one ONNX session per process) --------------------------

_session_lock = threading.Lock()
_session = None   # None or onnxruntime.InferenceSession
_model_path_used: str | None = None


def _default_model_path() -> str:
    return os.environ.get(ENV_VAR, DEFAULT_MODEL_PATH)


def _get_session():
    """Load the ONNX session lazily and cache it.

    Returns ``None`` if the model file is missing (so that the
    caller can degrade gracefully) or if loading fails for any
    reason. We never raise from here — orientation is a
    best-effort pre-step.
    """
    global _session, _model_path_used
    path = _default_model_path()
    if _session is not None and path == _model_path_used:
        return _session
    with _session_lock:
        if _session is not None and path == _model_path_used:
            return _session
        if not Path(path).is_file():
            log.info("doc_ori: model file %s not found; stage-1 disabled", path)
            _session = None
            _model_path_used = path
            return None
        try:
            import onnxruntime as ort  # local import: not all envs have it
            sess = ort.InferenceSession(
                path, providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            log.warning("doc_ori: failed to load %s (%s); stage-1 disabled",
                        path, exc)
            _session = None
            _model_path_used = path
            return None
        _session = sess
        _model_path_used = path
        return sess


def reset_session() -> None:
    """Drop the cached session (test helper / model hot-swap)."""
    global _session, _model_path_used
    with _session_lock:
        _session = None
        _model_path_used = None


# --- Preprocessing ---------------------------------------------------------


def _preprocess(png_bytes: bytes):
    """PP-LCNet doc_ori preprocessing (see module docstring for spec).

    Returns ``(input_array, (orig_w, orig_h))`` where
    ``input_array`` is a (1, 3, 224, 224) float32 ndarray.

    Raises if the PNG is unreadable.
    """
    import numpy as np
    from PIL import Image

    with Image.open(io.BytesIO(png_bytes)) as im:
        im = im.convert("RGB")
        w, h = im.size
        if w < h:
            nw, nh = _SHORT_SIDE, int(round(h * _SHORT_SIDE / w))
        else:
            nw, nh = int(round(w * _SHORT_SIDE / h)), _SHORT_SIDE
        im = im.resize((nw, nh), Image.Resampling.BILINEAR)
        left = (nw - _INPUT_SIZE) // 2
        top = (nh - _INPUT_SIZE) // 2
        im = im.crop((left, top, left + _INPUT_SIZE, top + _INPUT_SIZE))
        arr = np.asarray(im, dtype=np.float32) / 255.0    # HWC, in [0,1]
        mean = np.array(_MEAN, dtype=np.float32)
        std = np.array(_STD, dtype=np.float32)
        arr = (arr - mean) / std                          # per channel
        arr = arr.transpose(2, 0, 1)[None]                # HWC -> NCHW
    return np.ascontiguousarray(arr, dtype=np.float32), (w, h)


# --- Public API ------------------------------------------------------------


def is_available() -> bool:
    """Return True if the model + onnxruntime are loadable right now."""
    return _get_session() is not None


def classify(png_bytes: bytes) -> tuple[int, float, list[float]] | None:
    """Run PP-LCNet on a single rendered page.

    Returns ``(ccw_degrees, confidence, probabilities)`` or ``None``
    when the model / session is unavailable.

    ``ccw_degrees`` ∈ {0, 90, 180, 270}: rotate the input that
    many degrees counter-clockwise to make it upright. ``confidence``
    is the softmax probability of the chosen class. ``probabilities``
    is the full softmax distribution over the 4 classes (mostly for
    logging / debugging).

    Failures (PNG unreadable, session error) return ``None`` so the
    caller can try the next detector.
    """
    sess = _get_session()
    if sess is None:
        return None
    try:
        x, _ = _preprocess(png_bytes)
    except Exception as exc:
        log.debug("doc_ori: preprocess failed (%s)", exc)
        return None
    try:
        logits = sess.run(
            None, {sess.get_inputs()[0].name: x}
        )[0][0]
    except Exception as exc:
        log.warning("doc_ori: inference failed (%s); stage-1 disabled", exc)
        reset_session()
        return None
    # Stable softmax
    import numpy as np
    z = logits - logits.max()
    p = np.exp(z) / np.exp(z).sum()
    idx = int(p.argmax())
    return _INDEX_TO_CCW[idx], float(p[idx]), [float(x) for x in p]


__all__ = [
    "classify",
    "is_available",
    "reset_session",
    "DEFAULT_MODEL_PATH",
    "ENV_VAR",
]
