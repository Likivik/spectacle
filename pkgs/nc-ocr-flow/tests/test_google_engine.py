"""Tests for google_engine._line_blocks — per-line grouping with native order."""
import fitz

from nc_ocr_flow.engines import google_engine


class _Sym:
    def __init__(self, t):
        self.text = t


class _V:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)


class _Box:
    def __init__(self, x0, y0, x1, y1):
        # bounding_box.vertices is a list of V (like the proto repeated field)
        self.vertices = [
            _V(x0, y0), _V(x1, y0), _V(x1, y1), _V(x0, y1),
        ]


def _w(text, x0, y0, x1, y1):
    return _Word([_Sym(text)], x0, y0, x1, y1)


class _Word:
    def __init__(self, symbols, x0, y0, x1, y1):
        self.symbols = symbols
        self.bounding_box = _Box(x0, y0, x1, y1)


class _Para:
    def __init__(self, words):
        self.words = words


class _Block:
    def __init__(self, paras):
        self.paragraphs = paras


def test_line_grouping_one_line_native_order():
    """Words on the same visual line join into one line, native order kept."""
    para = _Para([
        _w("Zebra", 10, 10, 40, 20),
        _w("Apple", 50, 10, 80, 20),
        _w("Lemon", 90, 10, 120, 20),
    ])
    block = _Block([para])
    lines = list(google_engine._line_blocks(block, 200, 200))
    assert len(lines) == 1
    text, bbox = lines[0]
    # Native order = the order we appended, NOT alphabetical sort.
    assert text == "Zebra Apple Lemon"
    assert bbox[0] == 10 and bbox[2] == 120


def test_line_grouping_two_lines_by_overlap():
    """Words at different y-heights split into separate lines."""
    para = _Para([
        _w("first", 10, 10, 40, 20),
        _w("line", 50, 10, 80, 20),
        _w("second", 10, 30, 50, 40),
        _w("line2", 60, 30, 90, 40),
    ])
    block = _Block([para])
    lines = list(google_engine._line_blocks(block, 200, 200))
    assert len(lines) == 2
    assert lines[0][0] == "first line"
    assert lines[1][0] == "second line2"


def test_line_grouping_skips_empty():
    """Empty symbols are dropped; only non-empty lines emitted."""
    para = _Para([
        _w("keep", 10, 10, 40, 20),
        _w(" ", 50, 10, 80, 20),
        _w("words", 90, 10, 120, 20),
    ])
    block = _Block([para])
    lines = list(google_engine._line_blocks(block, 200, 200))
    assert len(lines) == 1
    assert lines[0][0] == "keep words"


# --- process_pdf base-PDF seeding (regression test) ------------------------


def test_process_pdf_seeds_real_base_pdf(monkeypatch, tmp_path):
    """process_pdf must yield a real PDF (source pages) for the embedder."""
    # Build a 1-page source PDF with an image-less page.
    src = tmp_path / "src.pdf"
    doc = fitz.open()
    doc.new_page(
        width=595, height=842,
    ).insert_text((72, 72), "sample")
    doc.save(src)
    doc.close()

    # output under a different name; must be seeded with source content
    out = tmp_path / "out.pdf"

    # Mock the network call to return nothing (we only test PDF seeding)
    monkeypatch.setattr(google_engine, "_ocr_pdf", lambda *a, **k: [])
    google_engine._batch_bucket = None

    result = google_engine.process_pdf(str(src), str(out))

    # The output file must be a real PDF with the source's page count.
    assert out.exists()
    got = fitz.open(str(out))
    try:
        assert got.page_count == 1, "output PDF must have the source's pages"
    finally:
        got.close()
    assert result.output_pdf == str(out)