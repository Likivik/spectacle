"""Tests for TSV parsing and VLM-fallback decision logic.

No GPU, no ocrmypdf needed — pure unit tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from nc_ocr_flow.ocr import (
    PageMeta, _parse_tsv, _needs_vlm,
    PER_PAGE_CONF_FLOOR, PER_PAGE_MIN_CHARS,
)


# --- TSV parsing -------------------------------------------------------------

def test_parse_tsv_empty(tmp_path: Path):
    """Missing TSV → empty dict."""
    result = _parse_tsv(tmp_path / "nonexistent.tsv")
    assert result == {}


def test_parse_tsv_single_page(tmp_path: Path):
    """Single page with known confidence values."""
    tsv = tmp_path / "ocr.tsv"
    lines = [
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t95.0\tHello",
        "5\t1\t1\t1\t1\t2\t10\t10\t50\t20\t90.0\tWorld",
        "5\t1\t1\t1\t1\t3\t10\t10\t50\t20\t88.0\tTest",
    ]
    tsv.write_text("\n".join(lines) + "\n")

    result = _parse_tsv(tsv)
    assert 1 in result
    page = result[1]
    assert isinstance(page, PageMeta)
    assert page.page_idx == 0
    assert page.confidence_p10 == 88.0  # lowest of 3 = 88.0
    assert page.char_count == 14  # "HelloWorldTest"


def test_parse_tsv_multi_page(tmp_path: Path):
    """Multiple pages with different confidence levels."""
    tsv = tmp_path / "ocr.tsv"
    lines = [
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t95.0\tPage1",
        "5\t2\t1\t1\t1\t1\t10\t10\t50\t20\t30.0\tlow",
    ]
    tsv.write_text("\n".join(lines) + "\n")

    result = _parse_tsv(tsv)
    assert len(result) == 2
    assert result[1].confidence_p10 == 95.0
    assert result[2].confidence_p10 == 30.0
    assert result[1].page_idx == 0
    assert result[2].page_idx == 1


def test_parse_tsv_ignores_non_word_levels(tmp_path: Path):
    """Only level=5 (word) entries should be counted."""
    tsv = tmp_path / "ocr.tsv"
    lines = [
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        "1\t1\t1\t1\t1\t1\t0\t0\t0\t0\t-1\t",   # block level
        "2\t1\t1\t1\t1\t1\t0\t0\t0\t0\t-1\t",   # para level
        "5\t1\t1\t1\t1\t1\t10\t10\t50\t20\t95.0\tword",
    ]
    tsv.write_text("\n".join(lines) + "\n")

    result = _parse_tsv(tsv)
    assert len(result) == 1
    assert result[1].char_count == 4  # "word"


# --- VLM fallback decision ---------------------------------------------------

def test_needs_vlm_confident_page():
    """High-confidence page does not need VLM."""
    p = PageMeta(page_idx=0, confidence_p10=90.0, char_count=500)
    assert _needs_vlm(p) is False


def test_needs_vlm_low_confidence():
    """Low confidence → VLM."""
    p = PageMeta(page_idx=0, confidence_p10=50.0, char_count=500)
    assert _needs_vlm(p) is True


def test_needs_vlm_few_chars():
    """High confidence but very few chars → VLM (likely garbage)."""
    p = PageMeta(page_idx=0, confidence_p10=95.0, char_count=10)
    assert _needs_vlm(p) is True


def test_needs_vlm_threshold_boundary():
    """Page at exactly threshold → does NOT need VLM."""
    p = PageMeta(page_idx=0, confidence_p10=PER_PAGE_CONF_FLOOR, char_count=PER_PAGE_MIN_CHARS)
    assert _needs_vlm(p) is False


def test_needs_vlm_below_threshold():
    """Page just below threshold → needs VLM."""
    p = PageMeta(page_idx=0, confidence_p10=PER_PAGE_CONF_FLOOR - 1, char_count=PER_PAGE_MIN_CHARS)
    assert _needs_vlm(p) is True


def test_needs_vlm_min_chars_boundary():
    """Page at exactly min_chars → does NOT need VLM."""
    p = PageMeta(page_idx=0, confidence_p10=PER_PAGE_CONF_FLOOR, char_count=PER_PAGE_MIN_CHARS)
    assert _needs_vlm(p) is False


def test_needs_vlm_both_bad():
    """Both low conf and few chars → VLM."""
    p = PageMeta(page_idx=0, confidence_p10=30.0, char_count=5)
    assert _needs_vlm(p) is True
