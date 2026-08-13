"""Classifier + 2-pass tesseract OCR for NC images.

API:
    classify(image_path) -> ClassifyResult(is_document, reason)
    ocr_image(image_path, output_pdf) -> OcrResult(text, confidence_p10)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DOC = "document"
PHOTO = "photo"

# tesseract --psm values
_PSM_DOC = "6"   # uniform block of text (clean scans)
_PSM_PHOTO = "11"  # sparse text (mixed layouts, photos)

# tesseract --dpi (200 avoids the 300-DPI Cyrillic regression)
_TESSERACT_DPI = "200"

# MobileNetV2 input: 224x224 normalized with ImageNet mean/std
_MOBILENET_SIZE = 224
_MOBILENET_MEAN = [0.485, 0.456, 0.406]
_MOBILENET_STD = [0.229, 0.224, 0.225]

_MOBILENET_SESSION = None


@dataclass(frozen=True)
class ClassifyResult:
    is_document: bool
    reason: str  # "mobilenet" | "no_text" | "short_text" | "error"


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence_p10: float  # 10th-percentile word confidence
    char_count: int


def _get_mobilenet_session():
    """Lazy-init ONNX session, cached at module level."""
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


def _classify_mobilenet(image_path: Path) -> bool:
    """Run MobileNetV2 doc/photo classifier. Returns True if document."""
    import numpy as np
    from PIL import Image

    img = Image.open(image_path).convert("RGB").resize(
        (_MOBILENET_SIZE, _MOBILENET_SIZE), Image.Resampling.BILINEAR
    )
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - _MOBILENET_MEAN) / _MOBILENET_STD
    arr = arr.transpose(2, 0, 1)[None]  # HWC → NCHW

    sess = _get_mobilenet_session()
    out = sess.run(None, {sess.get_inputs()[0].name: arr.astype(np.float32)})[0]
    return int(out[0].argmax()) == 0


def _ocr_text(image_path: Path, psm: str) -> OcrResult:
    """Run tesseract once, return text + confidence + char count."""
    import pytesseract

    image = pytesseract.image_to_pdf_or_hocr(
        str(image_path),
        extension="hocr",
        config=f"--psm {psm} --oem 1 --dpi {_TESSERACT_DPI} -l rus+eng",
    )
    # hocr is HTML; for text we use a separate call
    text = pytesseract.image_to_string(
        image_path,
        config=f"--psm {psm} --oem 1 --dpi {_TESSERACT_DPI} -l rus+eng",
    )
    data = pytesseract.image_to_data(
        image_path,
        config=f"--psm {psm} --oem 1 --dpi {_TESSERACT_DPI} -l rus+eng",
        output_type=pytesseract.Output.DICT,
    )
    confs = [int(c) for c in data["conf"] if int(c) >= 0]
    conf_p10 = sorted(confs)[len(confs) // 10] if confs else 0
    return OcrResult(text=text.strip(), confidence_p10=conf_p10, char_count=len(text.strip()))


def classify(image_path: str | Path) -> ClassifyResult:
    """Classify image as document or photo.

    Pipeline:
      1. MobileNetV2 binary classifier (~100ms CPU)
      2. Returns DOC or PHOTO with reason for logging

    Failures fall back to conservative "photo" so we never OCR a photo
    by mistake (false negative is worse than false positive here because
    photos end up in user-facing search results if wrongly OCR'd).
    """
    path = Path(image_path)
    try:
        is_doc = _classify_mobilenet(path)
        return ClassifyResult(is_document=is_doc, reason="mobilenet")
    except Exception as exc:
        log.warning("classifier failed: %s; defaulting to photo", exc)
        return ClassifyResult(is_document=False, reason=f"error:{type(exc).__name__}")


def ocr_image(image_path: str | Path, output_pdf_path: str | Path) -> OcrResult:
    """Run 2-pass tesseract on a document image, write PDF with text layer.

    Pass 1: --psm 11 sparse text probe (fast, ~500ms)
    Pass 2: --psm 6 uniform block (full OCR, ~3-10s)

    Writes PDF via img2pdf (lossless) + ocrmypdf (text layer embed).
    Returns aggregated text + confidence for downstream VLM gating.
    """
    path = Path(image_path)
    out_pdf = Path(output_pdf_path)

    # Pass 1: probe
    probe = _ocr_text(path, _PSM_PHOTO)

    if probe.char_count < 40:
        # Treat as ambiguous: skip (we already classified via MobileNetV2).
        # If we get here, MobileNetV2 said "doc" but tesseract found no text —
        # probably a clean scan with bad PSM; force PSM 6 for extraction.
        result = _ocr_text(path, _PSM_DOC)
    else:
        result = _ocr_text(path, _PSM_DOC)

    # Write PDF with text layer
    import img2pdf
    import ocrmypdf

    out_pdf.write_bytes(img2pdf.convert(str(path)))
    ocrmypdf.ocr(
        str(out_pdf),
        str(out_pdf),
        language="rus+eng",
        skip_text=True,
        progress_bar=False,
        output_type="pdf",
    )

    return result


__all__ = ["ClassifyResult", "OcrResult", "classify", "ocr_image", "DOC", "PHOTO"]
