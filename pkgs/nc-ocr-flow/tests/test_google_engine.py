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


class _BoxNorm:
    """Word bounding box carrying ONLY normalized_vertices ([0, 1] floats).

    Mirrors the whole-document batch path Vision actually uses: it
    populates ``normalized_vertices`` and leaves ``vertices`` empty.
    Pre-fix the parser silently dropped every such Word.
    """

    def __init__(self, nx0, ny0, nx1, ny1):
        self.vertices = []  # explicitly empty — matches the bug path.
        self.normalized_vertices = [
            _V(nx0, ny0), _V(nx1, ny0), _V(nx1, ny1), _V(nx0, ny1),
        ]


class _BoxEmpty:
    """Word bounding box with NEITHER vertices nor normalized_vertices.

    Used to drive the "drop with warning" path — both lists present but
    truncated/empty.
    """

    def __init__(self):
        self.vertices = []
        self.normalized_vertices = []


def _w(text, x0, y0, x1, y1):
    return _Word([_Sym(text)], x0, y0, x1, y1)


def _w_norm(text, nx0, ny0, nx1, ny1):
    """Word whose bounding_box carries only normalized_vertices ([0, 1])."""
    w = _Word.__new__(_Word)
    w.symbols = [_Sym(text)]
    w.bounding_box = _BoxNorm(nx0, ny0, nx1, ny1)
    return w


def _w_empty(text):
    """Word whose bounding_box has neither vertices nor normalized_vertices."""
    w = _Word.__new__(_Word)
    w.symbols = [_Sym(text)]
    w.bounding_box = _BoxEmpty()
    return w


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


# --- Unicode normalisation (regression: decomposed Cyrillic -> mojibake) ----
#
# Background: Vision can report a word as a base letter followed by a
# separate COMBINING MARK symbol. Joining those symbol texts verbatim
# and writing the result into the sandwich text layer produced text that
# every reader extracted as mojibake: 0 Cyrillic characters and a pile
# of U+0300-U+036F combining marks. The parser must emit NFC.


def test_decomposed_symbols_are_normalised_to_nfc():
    """A word built from base+combining symbols comes out precomposed."""
    # "и" + U+0306 (combining breve) == "й" once composed.
    para = _Para([
        _Word([_Sym("\u0438"), _Sym("\u0306")], 10, 10, 40, 20),
    ])
    block = _Block([para])
    lines = list(google_engine._line_blocks(block, 200, 200))
    assert len(lines) == 1
    text, _bbox = lines[0]
    assert text == "\u0439"  # precomposed, not "и" + U+0306
    assert "\u0306" not in text


def test_decomposed_line_has_no_combining_marks():
    """Whole-line NFC: decomposed Cyrillic comes back with zero marks.

    "Таймыр" decomposes under NFD (й -> и + U+0306), so this test is
    NOT vacuous — unlike plain-letter words such as "СГР", whose NFD
    form is identical to NFC and would pass with or without the fix.
    """
    import unicodedata

    nfd = unicodedata.normalize("NFD", "Таймыр")
    assert nfd != "Таймыр", "test input does not actually decompose"
    assert any(0x0300 <= ord(c) <= 0x036F for c in nfd)

    words = [
        _w("СГР", 10, 10, 40, 20),
        _w(nfd, 50, 10, 90, 20),
    ]
    block = _Block([_Para(words)])
    lines = list(google_engine._line_blocks(block, 200, 200))
    assert len(lines) == 1
    text, _bbox = lines[0]
    assert text == "СГР Таймыр"
    marks = [c for c in text if 0x0300 <= ord(c) <= 0x036F]
    assert marks == []
    cyrillic = [c for c in text if "А" <= c <= "я" or c in "Ёё"]
    assert len(cyrillic) == len("СГРТаймыр")


# --- normalized_vertices handling (regression: Google bbox-parser bug) -----
#
# Background: the live Google Vision whole-document PDF batch path
# populates ``normalized_vertices`` ([0, 1] floats) and leaves
# ``vertices`` empty. Pre-fix the parser only read ``vertices``, so
# every Word was silently dropped and the engine returned zero blocks
# — masking every OCR result as empty. These tests pin both directions
# of the fix.


def test_line_blocks_accepts_normalized_vertices_only():
    """Words with only normalized_vertices are emitted at absolute coords.

    Fixture: page is 200x200. Two Words on one line carry [0,1] floats
    ``(0.05, 0.05)→(0.20, 0.10)`` and ``(0.25, 0.05)→(0.40, 0.10)``.
    Expect ONE line containing both words; expected absolute bboxes
    ``(10, 10, 80, 20)`` for word1 and ``(50, 10, 80, 20)`` for word2.
    Pre-fix this test produced an empty list (the original bug).
    """
    para = _Para([
        _w_norm("Hello", 0.05, 0.05, 0.20, 0.10),
        _w_norm("World", 0.25, 0.05, 0.40, 0.10),
    ])
    block = _Block([para])
    lines = list(google_engine._line_blocks(block, 200, 200))
    assert len(lines) == 1, (
        "Words with only normalized_vertices must NOT be silently "
        "dropped (regression: pre-PR the parser discarded them all)."
    )
    text, bbox = lines[0]
    # Words on the same y-band join into one line.
    assert text == "Hello World"
    # Absolute bboxes derived by multiplying normalized by (page_w, page_h).
    assert bbox == (10.0, 10.0, 80.0, 20.0), (
        f"expected absolute bbox (10,10,80,20) for the line, got {bbox!r}"
    )


def test_line_blocks_normalized_two_lines():
    """Same fix, two visual lines, different y-bands."""
    para = _Para([
        # Line 1: top of page, normalized y in [0.10, 0.15]
        _w_norm("first",  0.05, 0.10, 0.20, 0.15),
        _w_norm("line",   0.25, 0.10, 0.40, 0.15),
        # Line 2: middle of page, normalized y in [0.45, 0.50]
        _w_norm("second", 0.05, 0.45, 0.20, 0.50),
        _w_norm("line2",  0.25, 0.45, 0.40, 0.50),
    ])
    block = _Block([para])
    # Pass a 1000x1000 page so the math is grep-friendly.
    lines = list(google_engine._line_blocks(block, 1000, 1000))
    assert len(lines) == 2
    assert lines[0][0] == "first line"
    assert lines[0][1] == (50.0, 100.0, 400.0, 150.0)
    assert lines[1][0] == "second line2"
    assert lines[1][1] == (50.0, 450.0, 400.0, 500.0)


def test_line_blocks_normalized_page_dims_required():
    """If the page is zero-dimensional, we cannot scale normalized coords.

    Words with only normalized_vertices and page_w=0 must be DROPPED
    (with warning), NOT silently written as bbox (0, 0, 0, 0) — which
    would corrupt the line bbox and downstream clip / merge logic.
    """
    para = _Para([_w_norm("lose", 0.1, 0.1, 0.5, 0.5)])
    block = _Block([para])
    # page_w=0, page_h=0 — we cannot scale, so drop (with warning).
    lines = list(google_engine._line_blocks(block, 0.0, 0.0))
    assert lines == [], (
        "normalized_vertices with zero page dims must be dropped, not "
        f"turned into bbox (0,0,0,0); got {lines!r}"
    )


def test_line_blocks_vertices_path_unchanged():
    """Regression control: the ``vertices`` (absolute coords) path is
    unchanged. Same fixture as ``test_line_grouping_one_line_native_order``
    above; absolute coords should produce identical bboxes.
    """
    para = _Para([
        _w("Zebra", 10, 10, 40, 20),
        _w("Apple", 50, 10, 80, 20),
        _w("Lemon", 90, 10, 120, 20),
    ])
    block = _Block([para])
    lines = list(google_engine._line_blocks(block, 200, 200))
    assert len(lines) == 1
    text, bbox = lines[0]
    assert text == "Zebra Apple Lemon"
    assert bbox == (10.0, 10.0, 120.0, 20.0)


def test_line_blocks_warning_when_no_geometry(caplog):
    """Words with NEITHER vertices NOR normalized_vertices are dropped,
    with a WARNING, not silently.

    The pre-fix code dropped them silently AND ALSO dropped any word
    with only normalized_vertices — so the warn-on-silent path was
    useless. Pin both directions here: the warning fires once per
    _line_blocks call (rate-limited), and the partial result (zero
    surviving words) does not corrupt the line bboxes.
    """
    para = _Para([
        _w_empty("orphan"),
        _w_empty("also-orphan"),
    ])
    block = _Block([para])
    with caplog.at_level("WARNING", logger="nc_ocr_flow.engines.google_engine"):
        lines = list(google_engine._line_blocks(block, 200, 200))
    assert lines == [], "no-geometry words must produce no lines"
    # Once-per-call rate limit: one warning covering both Words, NOT one
    # warning per Word (that would spam the log on a bad response).
    warns = [
        r for r in caplog.records
        if r.levelname == "WARNING"
        and "vertices or normalized_vertices" in r.getMessage()
    ]
    assert len(warns) == 1, (
        f"expected exactly one (rate-limited) WARNING, got {len(warns)}: "
        f"{[r.getMessage() for r in warns]}"
    )


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