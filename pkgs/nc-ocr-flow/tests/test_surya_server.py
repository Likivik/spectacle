"""Integration tests for Surya server FastAPI app.

Tests the /ocr and /health endpoints with mocked Surya predictor.
No GPU needed — Surya predictor is mocked.
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def surya_app():
    """Create Surya server app with mocked predictor."""
    from nc_ocr_flow.surya_server import _create_app
    app = _create_app()
    return app


def test_health_endpoint(surya_app):
    """GET /health returns status ok."""
    from fastapi.testclient import TestClient
    client = TestClient(surya_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ocr_endpoint_missing_field(surya_app):
    """POST /ocr without image_b64 returns 422."""
    from fastapi.testclient import TestClient
    client = TestClient(surya_app)
    resp = client.post("/ocr", json={})
    assert resp.status_code == 422


def test_ocr_endpoint_with_mock_predictor(surya_app):
    """POST /ocr with valid image returns blocks."""
    from fastapi.testclient import TestClient
    from PIL import Image

    # Create a tiny test image
    img = Image.new("RGB", (100, 50), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    # Mock the predictor: inject a fake predictor into the app's closure
    # We patch the lazy import inside _get_predictor
    mock_block = MagicMock()
    mock_block.html = "<span>Привет</span>"
    mock_block.bbox = [10, 10, 80, 30]
    mock_block.confidence = 0.95
    mock_block.label = "Text"

    mock_pred = MagicMock()
    mock_pred.image_bbox = (0, 0, 100, 50)
    mock_pred.blocks = [mock_block]

    mock_predictor = MagicMock(return_value=[mock_pred])

    # Inject mock modules for surya
    mock_surya_mod = MagicMock()
    mock_surya_inf = MagicMock()
    mock_surya_inf.SuryaInferenceManager = MagicMock()
    mock_surya_rec = MagicMock()
    mock_surya_rec.RecognitionPredictor = MagicMock(return_value=mock_predictor)

    with patch.dict(sys.modules, {
        "surya": mock_surya_mod,
        "surya.inference": mock_surya_inf,
        "surya.recognition": mock_surya_rec,
    }):
        client = TestClient(surya_app)
        resp = client.post("/ocr", json={"image_b64": image_b64})
        assert resp.status_code == 200
        data = resp.json()
        assert "blocks" in data
        assert "page_width" in data
        assert "page_height" in data


def test_detect_endpoint_with_mock_predictor(surya_app):
    """POST /detect returns detector line geometry without recognition."""
    from fastapi.testclient import TestClient
    from PIL import Image

    img = Image.new("RGB", (100, 50), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    mock_box = MagicMock()
    mock_box.bbox = [10, 11, 80, 30]
    mock_box.polygon = [[10, 11], [80, 12], [79, 30], [11, 29]]
    mock_box.confidence = 0.87
    mock_pred = MagicMock(bboxes=[mock_box], image_bbox=[0, 0, 100, 50])
    mock_detector = MagicMock(return_value=[mock_pred])
    mock_detection = MagicMock(DetectionPredictor=MagicMock())
    mock_detection.DetectionPredictor.local.return_value = mock_detector

    with patch.dict(sys.modules, {"surya.detection": mock_detection}):
        resp = TestClient(surya_app).post("/detect", json={"image_b64": image_b64})

    assert resp.status_code == 200
    assert resp.json() == {
        "lines": [{
            "bbox": [10.0, 11.0, 80.0, 30.0],
            "polygon": [[10.0, 11.0], [80.0, 12.0], [79.0, 30.0], [11.0, 29.0]],
            "confidence": 0.87,
        }],
        "page_width": 100.0,
        "page_height": 50.0,
    }
    mock_detection.DetectionPredictor.local.assert_called_once_with()
    mock_detector.assert_called_once()


def test_detect_endpoint_missing_field(surya_app):
    from fastapi.testclient import TestClient
    assert TestClient(surya_app).post("/detect", json={}).status_code == 422


def test_ocr_endpoint_empty_blocks(surya_app):
    """POST /ocr with image that has no text returns empty blocks."""
    from fastapi.testclient import TestClient
    from PIL import Image

    img = Image.new("RGB", (100, 50), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    mock_pred = MagicMock()
    mock_pred.image_bbox = (0, 0, 100, 50)
    mock_pred.blocks = []

    mock_predictor = MagicMock(return_value=[mock_pred])

    mock_surya_mod = MagicMock()
    mock_surya_inf = MagicMock()
    mock_surya_inf.SuryaInferenceManager = MagicMock()
    mock_surya_rec = MagicMock()
    mock_surya_rec.RecognitionPredictor = MagicMock(return_value=mock_predictor)

    with patch.dict(sys.modules, {
        "surya": mock_surya_mod,
        "surya.inference": mock_surya_inf,
        "surya.recognition": mock_surya_rec,
    }):
        client = TestClient(surya_app)
        resp = client.post("/ocr", json={"image_b64": image_b64})
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocks"] == []
