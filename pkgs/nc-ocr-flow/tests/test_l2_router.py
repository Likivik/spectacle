"""Tests for the L2 handwriting router (WritingtypeAPI) integration."""
import json

import pytest

from nc_ocr_flow import ocr as ocr_mod
from nc_ocr_flow import writingtype_client as wt


class _FakeSession:
    class _In:
        name = "input"
        shape = ["batch", 3, 224, 224]

    def __init__(self, probs):
        self._probs = probs
        self.inputs = [self._In()]

    def get_inputs(self):
        return self.inputs

    def run(self, _none, _feed):
        import numpy as np
        logits = np.log(np.array(self._probs, dtype=np.float32) + 1e-9)[None]
        return [logits]


@pytest.fixture
def fake_session_typed(monkeypatch):
    """typewritten 0.95 / combination 0.04 / handwritten 0.01"""
    s = _FakeSession([0.01, 0.95, 0.04])
    monkeypatch.setattr(wt, "_get_session", lambda: s)
    return s


def test_classify_typed_no_escalate(fake_session_typed):
    png = _png()
    r = wt.classify_page_writingtype(png)
    assert r.label == "typewritten"
    assert not r.escalate
    assert r.confidence > 0.9


def test_classify_handwritten_escalates(monkeypatch):
    s = _FakeSession([0.80, 0.05, 0.15])
    monkeypatch.setattr(wt, "_get_session", lambda: s)
    r = wt.classify_page_writingtype(_png())
    assert r.label == "handwritten"
    assert r.escalate


def test_classify_combination_escalates(monkeypatch):
    s = _FakeSession([0.30, 0.30, 0.40])
    monkeypatch.setattr(wt, "_get_session", lambda: s)
    r = wt.classify_page_writingtype(_png())
    assert r.label == "combination"
    assert r.escalate  # 0.30 + 0.40 >= 0.30 threshold


def test_model_available_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(wt, "MODEL_PATH", str(tmp_path / "nope.onnx"))
    assert not wt.model_available()


def _png(w=320, h=440):
    from PIL import Image
    import io
    img = Image.new("RGB", (w, h), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_process_pdf_l2_router_escalates(monkeypatch, tmp_path):
    """L2 router verdict forces a page into vlm_pages regardless of conf."""
    from pathlib import Path

    # 2-page PDF, no text (scan-like)
    import fitz
    src = tmp_path / "scan.pdf"
    d = fitz.open()
    d.new_page(width=595, height=842)
    d.new_page(width=595, height=842)
    d.save(str(src))
    d.close()

    # fake ocrmypdf+tesseract pass: copy input, empty TSV
    monkeypatch.setattr(ocr_mod, "_run_ocrmypdf",
                        lambda i, o, t: Path(o).write_bytes(Path(i).read_bytes()))
    monkeypatch.setattr(ocr_mod, "_generate_tsv",
                        lambda o, t: t.write_text(""))

    # L2: page 0 typed, page 1 handwritten
    verdicts = iter([
        wt.WritingTypeResult("typewritten", 0.9, {}, False, 5.0),
        wt.WritingTypeResult("handwritten", 0.85, {}, True, 5.0),
    ])
    monkeypatch.setattr(wt, "model_available", lambda: True)
    monkeypatch.setattr(wt, "classify_page_writingtype", lambda png: next(verdicts))

    # VLM embed: no-op
    monkeypatch.setattr(ocr_mod, "_render_page_png", lambda *a, **k: b"png")
    monkeypatch.setattr(ocr_mod, "_surya_ocr_page", lambda png: _fake_result())

    class _Doc:
        def __len__(self):
            return 2

        def __getitem__(self, i):
            return self

        def get_text(self):
            return ""

        def saveIncr(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(fitz, "open", lambda *a, **k: _Doc())

    res = ocr_mod.process_pdf(str(src), engine="auto")
    # page 1 escalated by L2; page 0 has no tesseract meta (empty TSV) →
    # conf gate also fires. L2 adds escalation on top, never removes.
    assert res.vlm_pages == [0, 1]
    assert res.l2_pages[0]["label"] == "typewritten"
    assert res.l2_pages[0]["escalate"] is False
    assert res.l2_pages[1]["escalate"] is True


class _FakeBlock:
    def __init__(self):
        self.bbox = (0.0, 0.0, 100.0, 100.0)
        self.text = "test"
        self.confidence = 0.9
        self.label = "text"


class _FakeResult:
    def __init__(self):
        self.blocks = [_FakeBlock()]
        self.page_width = 100.0
        self.page_height = 100.0


def _fake_result():
    return _FakeResult()
