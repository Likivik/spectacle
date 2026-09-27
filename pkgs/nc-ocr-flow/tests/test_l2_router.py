"""Tests for the L2 handwriting router (WritingtypeAPI) integration."""
import pytest

from nc_ocr_flow import ocr as ocr_mod  # noqa: F401  (kept for engine smoke tests)
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


class _FakeBlock:
    pass


class _FakeResult:
    pass


def _fake_result():
    return _FakeResult()
