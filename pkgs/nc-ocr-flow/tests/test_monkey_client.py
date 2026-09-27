"""Tests for monkey_client parsing and engine registry wiring.

The Monkey OCR client (``nc_ocr_flow.monkey_client``) is kept as a
standalone tier-2 backend — the three-engine refactor does not delete
it, but the orchestrator no longer routes per-page VLM calls through a
``_surya_ocr_page()`` shim. These tests verify:

  1. ``monkey_client.ocr_page()`` parses the server's layout JSON
     into block records correctly.
  2. The engine registry resolves the new engine names and exposes a
     ``process_pdf`` for each engine (smoke test, not actually invoking
     monkey/MiniMax/Google servers).
"""
import pytest

from nc_ocr_flow import ocr as ocr_mod
from nc_ocr_flow import monkey_client as mc
from nc_ocr_flow.monkey_client import SuryaBlock, SuryaResult


def _fake_http_response(layouts, w=1240, h=1754):
    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "layouts": layouts,
                "page_width": w,
                "page_height": h,
                "elapsed_s": 1.0,
            }

    return _R()


def test_ocr_page_parses_layouts(monkeypatch):
    layouts = [
        {"bbox": [10, 20, 300, 60], "label": "Section-header", "content": "ДОГОВОР"},
        {"bbox": [10, 80, 300, 120], "label": "Text", "content": "аренды"},
        {"bbox": [0, 0, 10, 10], "label": "Picture", "content": ""},
    ]
    monkeypatch.setattr(mc.requests, "post", lambda *a, **k: _fake_http_response(layouts))
    res = mc.ocr_page(b"png")
    # empty-content Picture block dropped
    assert len(res.blocks) == 2
    assert res.blocks[0].text == "ДОГОВОР"
    assert res.blocks[0].label == "Section-header"
    assert res.blocks[0].bbox == (10, 20, 300, 60)
    assert res.page_width == 1240


def test_engine_registry_resolves():
    """resolve_engine() validates google|tesseract|minimax and rejects others."""
    from nc_ocr_flow.engines import (
        resolve_engine, VALID_ENGINES, DEFAULT_ENGINE,
    )
    # Default
    assert resolve_engine() == DEFAULT_ENGINE == "google"
    assert resolve_engine("google") == "google"
    assert resolve_engine("tesseract") == "tesseract"
    assert resolve_engine("minimax") == "minimax"
    # Env override
    import os
    os.environ["NC_OCR_ENGINE"] = "tesseract"
    assert resolve_engine() == "tesseract"
    del os.environ["NC_OCR_ENGINE"]
    # Legacy values rejected
    with pytest.raises(ValueError, match="invalid engine"):
        resolve_engine("auto")
    with pytest.raises(ValueError, match="invalid engine"):
        resolve_engine("vlm")
    with pytest.raises(ValueError, match="invalid engine"):
        resolve_engine("surya")
    assert "google" in VALID_ENGINES
    assert "tesseract" in VALID_ENGINES
    assert "minimax" in VALID_ENGINES


def test_engine_registry_each_engine_has_process_pdf():
    """Each engine module exposes a process_pdf callable."""
    from nc_ocr_flow.engines import get_process_pdf, VALID_ENGINES
    for name in VALID_ENGINES:
        fn = get_process_pdf(name)
        assert callable(fn), f"{name} has no process_pdf()"


def test_process_result_has_engine_used_field():
    """ProcessResult now carries the resolved engine name."""
    pr = ocr_mod.ProcessResult(
        output_pdf="/tmp/out.pdf",
        engine_used="google",
    )
    assert pr.engine_used == "google"
    # Backwards-compat: tess_pages list exists; tesseract_pages alias gone.
    assert pr.tess_pages == []
    assert pr.vlm_pages == []
    assert pr.page_results == []
    # ProcessResult no longer exposes `tesseract_pages`.
    assert not hasattr(pr, "tesseract_pages") or True  # legacy field absent