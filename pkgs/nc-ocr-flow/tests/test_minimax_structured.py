"""Tests for M3 tool-use structured blocks in minimax_client."""
import base64
import json

import pytest

from nc_ocr_flow import minimax_client as mc
from nc_ocr_flow.minimax_client import (
    _blocks_from_toolcall,
    _html_table_to_text,
)


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def _png_bytes(w=1654, h=2338):
    from PIL import Image
    import io
    img = Image.new("RGB", (w, h), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_html_table_to_text():
    html = ("<table><tr><th>Колонка</th></tr>"
            "<tr><td>Полы</td><td>Удовлетворительно</td></tr></table>")
    text = _html_table_to_text(html)
    assert "Полы | Удовлетворительно" in text
    assert "<td>" not in text


def test_blocks_from_toolcall_scales_bbox():
    blocks = _blocks_from_toolcall(json.dumps({
        "blocks": [
            {"type": "text", "bbox": [100, 200, 500, 300],
             "text": "hello", "conf": 0.9},
            {"type": "table", "bbox": [0, 0, 1000, 100],
             "text": "<table><tr><td>a</td><td>b</td></tr></table>", "conf": 0.8},
            {"type": "handwritten", "bbox": [700, 50, 950, 100],
             "text": "01 марта 2023 г.", "conf": 0.95},
        ]
    }), 1654, 2338)
    assert len(blocks) == 3
    b0 = blocks[0]
    # 100/1000 of 1654 px wide
    assert abs(b0.bbox[0] - 165.4) < 0.5
    assert abs(b0.bbox[1] - 0.2 * 2338) < 0.5
    assert b0.text == "hello"
    assert b0.confidence == 0.9
    # table HTML stripped
    assert blocks[1].text == "a | b"
    assert blocks[1].label == "table"
    assert blocks[2].label == "handwritten"
    assert "марта" in blocks[2].text


def test_blocks_from_toolcall_empty_and_bad():
    blocks = _blocks_from_toolcall(json.dumps({"blocks": [
        {"type": "text", "bbox": [1, 2, 3, 4], "text": "", "conf": 0.9},
        {"type": "text", "bbox": [5], "text": "bad bbox", "conf": 0.5},
    ]}), 100, 100)
    assert len(blocks) == 1
    # bad bbox → full page
    assert blocks[0].bbox == (0.0, 0.0, 100.0, 100.0)


def test_ocr_page_minimax_structured(monkeypatch):
    png = _png_bytes()
    captured = {}

    def fake_chat(body):
        captured["body"] = body
        return {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "write_ocr_blocks",
                            "arguments": json.dumps({"blocks": [
                                {"type": "header", "bbox": [0, 0, 1000, 80],
                                 "text": "АКТ", "conf": 0.95},
                            ]}),
                        }
                    }],
                },
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

    monkeypatch.setattr(mc, "_chat", fake_chat)
    monkeypatch.setenv("NC_OCR_MINIMAX_KEY", "test-key")
    res = mc.ocr_page_minimax(png)
    # tool_choice forced
    assert captured["body"]["tool_choice"]["function"]["name"] == "write_ocr_blocks"
    assert len(res.blocks) == 1
    assert res.blocks[0].text == "АКТ"
    assert res.blocks[0].label == "header"
    assert res.page_width == 1654.0


def test_ocr_page_minimax_fallback_plain(monkeypatch):
    png = _png_bytes()
    calls = {"n": 0}

    def fake_chat(body):
        calls["n"] += 1
        if "tools" in body:
            # tool call returns garbage JSON → parse failure → retry plain
            return {
                "choices": [{"message": {"tool_calls": [{
                    "function": {"arguments": "not-json{"},
                }]}}],
                "usage": {},
            }
        return {
            "choices": [{"message": {"content": "строка 1\nстрока 2"}}],
            "usage": {},
        }

    monkeypatch.setattr(mc, "_chat", fake_chat)
    monkeypatch.setenv("NC_OCR_MINIMAX_KEY", "test-key")
    res = mc.ocr_page_minimax(png)
    assert calls["n"] == 2  # structured attempt + plain retry
    assert len(res.blocks) == 1
    assert "строка 1" in res.blocks[0].text
    assert res.blocks[0].label == "minimax-plain"
