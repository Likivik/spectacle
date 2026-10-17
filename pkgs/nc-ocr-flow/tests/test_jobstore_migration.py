"""Regression: a pre-C6 ``jobs`` table must migrate cleanly on ``init()``.

The first production rollout of the retry columns put
``CREATE INDEX ... ON jobs(next_run_at)`` in the schema script, which runs
BEFORE ``_migrate_add_retry_columns``. On a database created before those
columns existed the index statement raised ``no such column: next_run_at``,
which aborted ``init()`` and left jobstore permanently in the no-op state:
no job history, no file index, an empty /stats — while the DB itself was
intact. Every test DB was freshly created (so it already had the columns),
so the whole suite passed while production was broken.

This test builds the OLD schema by hand, then runs the real ``init()``.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = (_HERE.parent / "src").resolve()
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# The jobs table exactly as it looked before the retry columns were added.
_PRE_C6_JOBS = """
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    nc_path TEXT,
    node_id INTEGER DEFAULT 0,
    engine TEXT,
    force INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    created REAL,
    started REAL,
    finished REAL,
    error TEXT,
    reason TEXT,
    result TEXT
);
"""


def _load_jobstore(db_dir: Path):
    """Import nc_ocr_flow.jobstore against ``db_dir`` and run init()."""
    for name in list(sys.modules):
        if name == "nc_ocr_flow.jobstore":
            del sys.modules[name]
    prev = os.environ.get("NC_OCR_STATE_DIR")
    os.environ["NC_OCR_STATE_DIR"] = str(db_dir)
    try:
        mod = importlib.import_module("nc_ocr_flow.jobstore")
        # NB: deliberately NOT mod._reset_for_tests() — it unlinks the DB
        # file, which would destroy the legacy database we just built.
        mod.init()
    finally:
        if prev is None:
            os.environ.pop("NC_OCR_STATE_DIR", None)
        else:
            os.environ["NC_OCR_STATE_DIR"] = prev
    return mod


def test_pre_c6_database_migrates_and_stays_ready(tmp_path: Path) -> None:
    db_dir = tmp_path / "legacy"
    db_dir.mkdir(parents=True)
    db = db_dir / "jobs.db"

    con = sqlite3.connect(db)
    con.executescript(_PRE_C6_JOBS)
    con.execute(
        "INSERT INTO jobs (path, nc_path, node_id, engine, force, status,"
        " created) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("/admin/files/old.pdf", "/admin/files/old.pdf", 42, "google", 0,
         "done", 1_700_000_000.0),
    )
    con.commit()
    con.close()

    mod = _load_jobstore(db_dir)

    assert mod._ready() is True, (
        "init() must survive a database that predates the retry columns"
    )

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
    indexes = {
        row[0] for row in
        con.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    con.close()

    assert {"attempts", "next_run_at"} <= cols, "migration must add both columns"
    assert "idx_jobs_next_run" in indexes, "retry index must exist after init"

    # The pre-existing row survived and is visible through the module —
    # the failure mode this guards against was an empty history.
    assert mod.stats().get("total") == 1
