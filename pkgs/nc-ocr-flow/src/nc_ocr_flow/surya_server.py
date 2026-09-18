"""FastAPI server wrapping Surya RecognitionPredictor. Run on GPU host.

    nc-ocr-flow serve  (or: python -m nc_ocr_flow.surya_server)

Environment:
    SURYA_INFERENCE_URL — point at existing vLLM server (optional)
    PORT — listen port (default 8084)
"""
from __future__ import annotations

import base64
import io
import logging
import os
import re

from pydantic import BaseModel

log = logging.getLogger(__name__)


class OcrRequest(BaseModel):
    image_b64: str


class BlockOut(BaseModel):
    bbox: list[float]
    text: str
    confidence: float
    label: str


class OcrResponse(BaseModel):
    blocks: list[BlockOut]
    page_width: float
    page_height: float


class DetectionLineOut(BaseModel):
    bbox: list[float]
    polygon: list[list[float]] | None = None
    confidence: float | None = None


class DetectionResponse(BaseModel):
    lines: list[DetectionLineOut]
    page_width: float
    page_height: float


def _create_app():
    from fastapi import FastAPI
    from PIL import Image

    app = FastAPI(title="Surya OCR Server")
    _predictor = None

    def _get_predictor():
        nonlocal _predictor
        if _predictor is None:
            from surya.inference import SuryaInferenceManager
            from surya.recognition import RecognitionPredictor
            manager = SuryaInferenceManager()
            _predictor = RecognitionPredictor(manager)
        return _predictor

    _detector = None

    def _get_detector():
        nonlocal _detector
        if _detector is None:
            from surya.detection import DetectionPredictor
            # Use the in-process predictor: DetectionPredictor() is a client
            # for Surya's separate detection server in current Surya releases.
            _detector = DetectionPredictor.local()
        return _detector

    @app.post("/detect", response_model=DetectionResponse)
    def detect(req: OcrRequest):
        img = Image.open(io.BytesIO(base64.b64decode(req.image_b64)))
        pred = _get_detector()([img])[0]
        lines = []
        for box in pred.bboxes:
            polygon = getattr(box, "polygon", None)
            lines.append(DetectionLineOut(
                bbox=list(box.bbox),
                polygon=[list(point) for point in polygon] if polygon is not None else None,
                confidence=getattr(box, "confidence", None),
            ))

        return DetectionResponse(
            lines=lines,
            page_width=float(pred.image_bbox[2]),
            page_height=float(pred.image_bbox[3]),
        )

    @app.post("/ocr", response_model=OcrResponse)
    def ocr(req: OcrRequest):
        img = Image.open(io.BytesIO(base64.b64decode(req.image_b64)))
        predictor = _get_predictor()
        preds = predictor([img])
        pred = preds[0]

        blocks = []
        for block in pred.blocks:
            text = re.sub(r"<[^>]+>", "", block.html or "").strip()
            if not text:
                continue
            blocks.append(BlockOut(
                bbox=list(block.bbox),
                text=text,
                confidence=block.confidence,
                label=block.label,
            ))

        return OcrResponse(
            blocks=blocks,
            page_width=float(pred.image_bbox[2]),
            page_height=float(pred.image_bbox[3]),
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def main() -> int:
    import uvicorn
    port = int(os.environ.get("PORT", "8084"))
    app = _create_app()
    uvicorn.run(app, host="0.0.0.0", port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
