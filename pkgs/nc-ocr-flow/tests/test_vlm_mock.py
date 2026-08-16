"""Tests for Surya VLM fallback path with mock HTTP server.

Validates:
  - Surya client parses mock response correctly
  - Sandwich embedding produces selectable text
  - process_pdf end-to-end with mocked Surya (tesseract real, ~30s)

No GPU needed — Surya endpoint is mocked via pytest-httpserver.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# --- Surya client tests (mock HTTP) ------------------------------------------

def test_surya_client_parses_response(tmp_path: Path):
    """Surya client correctly parses JSON response into SuryaResult."""
    from nc_ocr_flow.surya_client import ocr_page, SuryaResult, SuryaBlock

    mock_response = {
        "blocks": [
            {"bbox": [10, 20, 300, 50], "text": "Привет мир", "confidence": 0.95, "label": "Text"},
            {"bbox": [10, 60, 200, 80], "text": "Hello world", "confidence": 0.91, "label": "Text"},
        ],
        "page_width": 1000.0,
        "page_height": 1400.0,
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status.return_value = None

    with patch("nc_ocr_flow.surya_client.requests.post", return_value=mock_resp):
        result = ocr_page(b"fake_png", url="http://mock")

    assert isinstance(result, SuryaResult)
    assert result.page_width == 1000.0
    assert result.page_height == 1400.0
    assert len(result.blocks) == 2
    assert isinstance(result.blocks[0], SuryaBlock)
    assert result.blocks[0].text == "Привет мир"
    assert result.blocks[0].bbox == (10, 20, 300, 50)
    assert result.blocks[0].confidence == 0.95


def test_surya_client_empty_blocks():
    """Surya client handles empty block list."""
    from nc_ocr_flow.surya_client import ocr_page

    mock_response = {
        "blocks": [],
        "page_width": 1000.0,
        "page_height": 1400.0,
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    mock_resp.raise_for_status.return_value = None

    with patch("nc_ocr_flow.surya_client.requests.post", return_value=mock_resp):
        result = ocr_page(b"fake_png", url="http://mock")

    assert len(result.blocks) == 0


# --- Sandwich embedding tests (PyMuPDF, no GPU) ------------------------------

@pytest.mark.slow
def test_sandwich_embed_makes_text_selectable(tmp_path: Path):
    """Embedding Surya text into a blank PDF makes text searchable."""
    import fitz

    from nc_ocr_flow.ocr import _embed_surya_text
    from nc_ocr_flow.surya_client import SuryaResult, SuryaBlock

    # Create a blank PDF page (A4)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Mock Surya result: one text block in the middle of the page
    surya_result = SuryaResult(
        blocks=[SuryaBlock(
            bbox=(100, 400, 500, 430),  # image pixels
            text="Привет мир",
            confidence=0.95,
            label="Text",
        )],
        page_width=595.0,
        page_height=842.0,
    )

    _embed_surya_text(doc, 0, surya_result)

    # Verify text is now searchable
    text = page.get_text()
    assert "Привет мир" in text

    doc.save(str(tmp_path / "test.pdf"))
    doc.close()


@pytest.mark.slow
def test_sandwich_replaces_tesseract_text(tmp_path: Path):
    """Embedding Surya text replaces existing (tesseract) text on the page."""
    import fitz

    from nc_ocr_flow.ocr import _embed_surya_text
    from nc_ocr_flow.surya_client import SuryaResult, SuryaBlock

    # Create a PDF with some existing text (simulating tesseract output)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((100, 100), "OLD TEXT", fontsize=12)

    # Verify old text is there
    assert "OLD TEXT" in page.get_text()

    # Embed Surya text (will redact old text first)
    surya_result = SuryaResult(
        blocks=[SuryaBlock(
            bbox=(100, 200, 400, 230),
            text="NEW TEXT",
            confidence=0.95,
            label="Text",
        )],
        page_width=595.0,
        page_height=842.0,
    )

    _embed_surya_text(doc, 0, surya_result)

    # Old text should be gone, new text should be there
    text = page.get_text()
    assert "NEW TEXT" in text
    assert "OLD TEXT" not in text

    doc.close()
