"""Tests for M3 tool-use structured blocks in minimax_client (shim → engine)."""
import base64
import json
from pathlib import Path

import pytest

from nc_ocr_flow import minimax_client as mc
from nc_ocr_flow.engines import minimax_engine as engine
# The shim re-exports _blocks_from_toolcall, _html_table_to_text, and
# ocr_page_minimax; the actual implementations live in minimax_engine.
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

    # Patch the engine module's _chat (where the implementation lives),
    # not the shim — the shim only re-exports symbols, so patching the
    # shim's attribute doesn't change what ocr_page_minimax calls.
    monkeypatch.setattr(engine, "_chat", fake_chat)
    monkeypatch.setenv("NC_OCR_MINIMAX_KEY", "test-key")
    res = engine.ocr_page_minimax(png)
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

    monkeypatch.setattr(engine, "_chat", fake_chat)
    monkeypatch.setenv("NC_OCR_MINIMAX_KEY", "test-key")
    res = engine.ocr_page_minimax(png)
    assert calls["n"] == 2  # structured attempt + plain retry
    assert len(res.blocks) == 1
    assert "строка 1" in res.blocks[0].text
    assert res.blocks[0].label == "minimax-plain"


def test_minimax_client_shim_re_exports_ocr_page_minimax():
    """Backwards-compat: nc_ocr_flow.minimax_client.ocr_page_minimax still works."""
    from nc_ocr_flow import minimax_client
    assert minimax_client.ocr_page_minimax is engine.ocr_page_minimax
    assert minimax_client._blocks_from_toolcall is engine._blocks_from_toolcall
    assert minimax_client._html_table_to_text is engine._html_table_to_text
    assert minimax_client.MiniMaxError is engine.MiniMaxError


# --- End-to-end (D1 regression) -------------------------------------------
#
# The previous engine implementation in engines/minimax_engine.py
# computed ``out_path`` but never created the file: it opened the
# INPUT PDF, embedded text into that document, then called
# ``saveIncr()`` which writes back to the path the document was
# loaded from — i.e. the input, not ``out_path``. The orchestrator
# then tried to ``fitz.open(out_pdf)`` for the embed step and
# raised FileNotFoundError for every job.
#
# This test runs the real engine + orchestrator glue on a real
# (tiny) PDF with the network call monkeypatched, and asserts that
# ``out_pdf`` exists and carries a text layer. The existing
# tests/test_minimax_structured.py tests only exercise
# ``ocr_page_minimax`` / ``_blocks_from_toolcall`` in isolation
# (which is why CI never caught the bug).


def _make_engine_input_pdf(tmp_path) -> "Path":
    """1-page PDF with a flat color raster, no text layer."""
    import fitz
    import io
    from PIL import Image
    pdf = tmp_path / "in.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), (220, 220, 220)).save(buf, format="PNG")
    page.insert_image(fitz.Rect(50, 50, 250, 250), stream=buf.getvalue())
    doc.save(str(pdf))
    doc.close()
    return pdf


def test_minimax_engine_seeds_output_pdf_end_to_end(monkeypatch, tmp_path):
    """End-to-end: engine must seed ``output_pdf`` from the input
    and the orchestrator's :func:`_finalize` must embed the text
    layer on top.

    Without D1 the engine never creates ``output_pdf`` and writes
    back to the input instead. This test runs the engine first and
    asserts the file was created by the engine (not by a defensive
    orchestrator fallback), then runs ``_finalize`` to embed the
    text layer. With D1 alone the end-to-end assertion is satisfied.
    """
    import fitz
    from nc_ocr_flow import ocr as ocr_mod

    in_pdf = _make_engine_input_pdf(tmp_path)
    out_pdf = tmp_path / "out.pdf"

    def fake_chat(body):
        return {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "write_ocr_blocks",
                            "arguments": json.dumps({"blocks": [
                                {"type": "text", "bbox": [50, 50, 500, 200],
                                 "text": "АКТ", "conf": 0.95},
                            ]}),
                        }
                    }],
                },
            }],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

    monkeypatch.setattr(engine, "_chat", fake_chat)
    monkeypatch.setenv("NC_OCR_MINIMAX_KEY", "test-key")

    # 1. Engine: must seed out_pdf from the input. Without D1 the
    #    engine writes back to the input file and out_pdf never
    #    appears on disk — the orchestrator's _finalize would then
    #    raise FileNotFoundError.
    engine_result = engine.process_pdf(in_pdf, out_pdf)
    assert out_pdf.exists(), (
        f"engine never created out_pdf at {out_pdf} — orchestrator "
        f"would have raised FileNotFoundError before the fix"
    )

    # 2. Orchestrator finalize: embeds the text layer on the seeded
    #    base document. After this, the text layer must be present.
    ocr_mod._finalize(engine_result, "minimax", str(out_pdf), str(in_pdf))

    post = fitz.open(str(out_pdf))
    try:
        text = post[0].get_text()
    finally:
        post.close()
    assert "АКТ" in text, f"text layer was not embedded: {text!r}"


def test_minimax_engine_writes_output_to_seeded_path(monkeypatch, tmp_path):
    """Direct engine call: out_path must be a real, valid PDF that
    is a copy of the input — independent of the orchestrator's
    _finalize seed-on-missing fallback. This is the contract every
    engine that produces OcrResults is expected to honour, and
    it's the precondition for ``_finalize`` to work."""
    import fitz
    from nc_ocr_flow.engines import minimax_engine as engine_mod

    in_pdf = _make_engine_input_pdf(tmp_path)
    out_pdf = tmp_path / "out.pdf"

    def fake_chat(body):
        return {
            "choices": [{"message": {"tool_calls": [{
                "function": {"name": "write_ocr_blocks",
                             "arguments": json.dumps({"blocks": [
                                 {"type": "text", "bbox": [0, 0, 1000, 200],
                                  "text": "х", "conf": 0.5},
                             ]})},
            }]}}],
            "usage": {},
        }

    monkeypatch.setattr(engine_mod, "_chat", fake_chat)
    monkeypatch.setenv("NC_OCR_MINIMAX_KEY", "test-key")

    result = engine_mod.process_pdf(in_pdf, out_pdf)

    # Engine wrote the file (was the bug — it didn't).
    assert out_pdf.exists(), "minimax engine did not seed output_pdf"
    # And what it wrote is a real PDF that the orchestrator can open.
    assert len(fitz.open(str(out_pdf))) == 1
    assert result.output_pdf == str(out_pdf)
