"""Tests for monkey_client parsing and backend wiring."""
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


def test_backend_wiring_monkey(monkeypatch):
    called = {}

    def fake_ocr_page(png_bytes, url=None):
        called["png"] = png_bytes
        return SuryaResult(blocks=[SuryaBlock((0, 0, 1, 1), "x", 1.0, "Text")],
                           page_width=1, page_height=1)

    import nc_ocr_flow.monkey_client as m
    monkeypatch.setattr(m, "ocr_page", fake_ocr_page)
    monkeypatch.setenv("NC_OCR_VLM_BACKEND", "monkey")
    res = ocr_mod._surya_ocr_page(b"png-bytes")
    assert called["png"] == b"png-bytes"
    assert res.blocks[0].text == "x"


def test_backend_default_minimax(monkeypatch):
    monkeypatch.setenv("NC_OCR_VLM_BACKEND", "minimax")
    # minimax path imports minimax_client; just verify it doesn't route to monkey
    import nc_ocr_flow.minimax_client as mmc

    def fake_mm(png_bytes):
        return SuryaResult([], 1, 1)

    monkeypatch.setattr(mmc, "ocr_page_minimax", fake_mm)
    res = ocr_mod._surya_ocr_page(b"png")
    assert isinstance(res, SuryaResult)
