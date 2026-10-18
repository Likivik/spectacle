"""The invisible text layer must be written with a Cyrillic-capable font.

Guards a failure that is invisible in the output: the visible layer of a
processed PDF is the original raster, so if ``_get_font`` silently falls back to
the built-in Helvetica the document still looks perfect while its searchable
text is Latin-only - useless for the Russian scans this pipeline exists for.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from nc_ocr_flow.ocr import FONT_PATH_ENV, _get_font

# Upper and lower case, including the letters stripped-down fonts drop most
# often (Ё/ё) and a couple of ordinary ones.
CYRILLIC_SAMPLE = "АБВГПЁабвгпё"


def test_resolved_font_covers_cyrillic():
    font = _get_font()
    # A real TTF was loaded, not the built-in base-14 font (which has no
    # buffer and no Cyrillic).
    assert font.buffer is not None, (
        "the text layer font resolved to a built-in font; set "
        f"{FONT_PATH_ENV} to a Cyrillic TTF"
    )
    missing = [ch for ch in CYRILLIC_SAMPLE if not font.has_glyph(ord(ch))]
    assert not missing, f"font {font.name!r} cannot encode {missing!r}"


def test_configured_path_is_authoritative(tmp_path, monkeypatch):
    """A set-but-missing NC_OCR_FONT_PATH is an error, never a fallback."""
    monkeypatch.setenv(FONT_PATH_ENV, str(tmp_path / "missing.ttf"))
    with pytest.raises(RuntimeError, match=FONT_PATH_ENV):
        _get_font()


def test_unset_env_falls_back_without_raising(monkeypatch):
    """Dev convenience: unset means 'search the fallback list'."""
    monkeypatch.delenv(FONT_PATH_ENV, raising=False)
    assert _get_font() is not None


def test_ci_uses_the_same_mechanism_as_prod():
    """dev==prod for fonts: CI must configure the font like the service does.

    Without this the suite would exercise the Latin-only fallback while
    production uses a configured Cyrillic font, i.e. the guarantee above would
    be untested exactly where it matters.
    """
    if not os.environ.get("CI"):
        pytest.skip("only meaningful in CI")
    configured = os.environ.get(FONT_PATH_ENV)
    assert configured, f"CI must set {FONT_PATH_ENV} (see .github/workflows/ci.yml)"
    assert Path(configured).exists(), f"{configured} does not exist in CI"
