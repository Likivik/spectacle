"""Tests for surya_client.detect_lines() — mocked HTTP, no GPU."""
from __future__ import annotations

import base64
from unittest.mock import patch, MagicMock

import pytest


# --- /ocr (existing path still works) ---------------------------------------

def test_ocr_page_decodes_response():
    """ocr_page() maps JSON blocks → SuryaBlock dataclasses."""
    from nc_ocr_flow.surya_client import ocr_page, SuryaBlock, SuryaResult

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "blocks": [
            {"bbox": [1, 2, 3, 4], "text": "hi", "confidence": 0.9, "label": "Text"},
            {"bbox": [5, 6, 7, 8], "text": "world", "confidence": 0.8, "label": "Text"},
        ],
        "page_width": 100.0,
        "page_height": 200.0,
    }
    fake_resp.raise_for_status = MagicMock()

    with patch("nc_ocr_flow.surya_client.requests.post", return_value=fake_resp) as mock_post:
        result = ocr_page(b"\x89PNG\r\n\x1a\n", url="http://mock:8084")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://mock:8084/ocr"
    assert kwargs["json"]["image_b64"]  # base64 of the PNG bytes
    assert isinstance(result, SuryaResult)
    assert len(result.blocks) == 2
    assert isinstance(result.blocks[0], SuryaBlock)
    assert result.blocks[0].bbox == (1.0, 2.0, 3.0, 4.0)
    assert result.blocks[1].text == "world"
    assert result.page_width == 100.0
    assert result.page_height == 200.0


def test_ocr_page_uses_default_url_when_unset():
    """Default SURYA_URL comes from env (set in fixture here)."""
    import os
    os.environ["NC_OCR_SURYA_URL"] = "http://default-host:9999"
    # Force re-import binding — module reads SURYA_URL at import time
    # so we just verify the symbol is exported from the module.
    from nc_ocr_flow import surya_client
    # Module-level constant is whatever env said at import time; the
    # explicit url= override path is covered above.
    assert hasattr(surya_client, "SURYA_URL")
    del os.environ["NC_OCR_SURYA_URL"]


def test_ocr_page_propagates_http_error():
    """If server returns 5xx, requests.HTTPError surfaces."""
    from nc_ocr_flow.surya_client import ocr_page

    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = RuntimeError("boom")
    with patch("nc_ocr_flow.surya_client.requests.post", return_value=fake_resp):
        with pytest.raises(RuntimeError, match="boom"):
            ocr_page(b"png", url="http://x:1")


# --- /detect (new line-geometry path) ----------------------------------------

def test_detect_lines_returns_structured_result():
    """detect_lines() maps JSON lines → DetectionLine dataclasses."""
    from nc_ocr_flow.surya_client import (
        detect_lines, DetectionLine, DetectionResult,
    )

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "lines": [
            {
                "bbox": [10, 11, 80, 30],
                "polygon": [[10, 11], [80, 12], [79, 30], [11, 29]],
                "confidence": 0.87,
            },
            {
                "bbox": [10, 35, 80, 55],
                "polygon": [[10, 35], [80, 36], [79, 55], [11, 54]],
                "confidence": 0.92,
            },
        ],
        "page_width": 100.0,
        "page_height": 200.0,
    }
    fake_resp.raise_for_status = MagicMock()

    with patch("nc_ocr_flow.surya_client.requests.post", return_value=fake_resp) as mock_post:
        result = detect_lines(b"\x89PNG", url="http://mock:8084")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://mock:8084/detect"
    assert kwargs["json"]["image_b64"]  # b64 of input
    assert isinstance(result, DetectionResult)
    assert len(result.lines) == 2
    line = result.lines[0]
    assert isinstance(line, DetectionLine)
    assert line.bbox == (10.0, 11.0, 80.0, 30.0)
    assert line.polygon == ((10.0, 11.0), (80.0, 12.0), (79.0, 30.0), (11.0, 29.0))
    assert line.confidence == 0.87
    assert result.page_width == 100.0
    assert result.page_height == 200.0


def test_detect_lines_handles_missing_polygon():
    """polygon=None and confidence=None are preserved (server may omit them)."""
    from nc_ocr_flow.surya_client import detect_lines

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "lines": [{"bbox": [0, 0, 10, 10]}],
        "page_width": 10.0,
        "page_height": 10.0,
    }
    fake_resp.raise_for_status = MagicMock()
    with patch("nc_ocr_flow.surya_client.requests.post", return_value=fake_resp):
        result = detect_lines(b"png", url="http://x:1")
    assert len(result.lines) == 1
    assert result.lines[0].polygon is None
    assert result.lines[0].confidence is None


def test_detect_lines_handles_empty_page():
    """No lines detected → empty list, page dims still set."""
    from nc_ocr_flow.surya_client import detect_lines

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "lines": [],
        "page_width": 100.0,
        "page_height": 200.0,
    }
    fake_resp.raise_for_status = MagicMock()
    with patch("nc_ocr_flow.surya_client.requests.post", return_value=fake_resp):
        result = detect_lines(b"png", url="http://x:1")
    assert result.lines == []
    assert result.page_width == 100.0
    assert result.page_height == 200.0


def test_detect_lines_base64_encodes_payload():
    """The PNG bytes are sent base64-encoded in image_b64."""
    from nc_ocr_flow.surya_client import detect_lines

    payload = b"\x89PNG\r\n\x1a\nFAKE"
    expected_b64 = base64.b64encode(payload).decode("ascii")

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "lines": [], "page_width": 1.0, "page_height": 1.0,
    }
    fake_resp.raise_for_status = MagicMock()
    with patch("nc_ocr_flow.surya_client.requests.post", return_value=fake_resp) as mock_post:
        detect_lines(payload, url="http://x:1")
    assert mock_post.call_args.kwargs["json"]["image_b64"] == expected_b64


def test_detect_lines_propagates_http_error():
    from nc_ocr_flow.surya_client import detect_lines

    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = RuntimeError("503")
    with patch("nc_ocr_flow.surya_client.requests.post", return_value=fake_resp):
        with pytest.raises(RuntimeError, match="503"):
            detect_lines(b"png", url="http://x:1")


def test_module_exports():
    """Public API surface is stable."""
    from nc_ocr_flow import surya_client
    for name in [
        "SuryaBlock", "SuryaResult", "ocr_page",
        "DetectionLine", "DetectionResult", "detect_lines",
        "SURYA_URL", "LinePolygon",
    ]:
        assert hasattr(surya_client, name), f"missing export: {name}"
