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


# --- B1 backstop migration: uq_jobs_inflight ------------------------------
#
# Build a pre-existing schema that already contains duplicate queued
# (or running) rows for the same NC path — the exact residue of the
# racy force=True ``_enqueue`` bug. ``_migrate_inflight_unique_index``
# must DEDUPE before creating the partial unique index, otherwise
# ``CREATE UNIQUE INDEX`` aborts ``init()`` and leaves ``_ready()``
# False. Same failure shape as PR #68's retry-index ordering bug.

_MODERN_JOBS = """
CREATE TABLE jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT NOT NULL,
    nc_path      TEXT,
    node_id      INTEGER DEFAULT 0,
    engine       TEXT,
    force        INTEGER DEFAULT 0,
    status       TEXT NOT NULL,
    created      REAL,
    started      REAL,
    finished     REAL,
    error        TEXT,
    reason       TEXT,
    result       TEXT,
    attempts     INTEGER DEFAULT 0,
    next_run_at  REAL    DEFAULT 0
);
"""


def _insert_job(
    con: sqlite3.Connection, *, jid: int | None, path: str,
    status: str, created: float,
) -> None:
    """Insert a jobs row matching the modern schema's column set."""
    con.execute(
        "INSERT INTO jobs (id, path, nc_path, node_id, engine, force,"
        " status, created, started, finished, error, reason, result,"
        " attempts, next_run_at)"
        " VALUES (?, ?, ?, 0, 'google', 0, ?, ?, NULL, NULL, NULL, NULL,"
        " NULL, 0, 0)",
        (jid, path, path, status, created),
    )


def _index_names(db: Path) -> set[str]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {
            row[0] for row in
            con.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    finally:
        con.close()


def _jobs_for_path(db: Path, path: str) -> list[tuple]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT id, status FROM jobs WHERE path = ?"
            " ORDER BY id ASC", (path,),
        ).fetchall()
    finally:
        con.close()
    return [(int(r[0]), str(r[1])) for r in rows]


def test_migration_dedupes_duplicate_queued_rows_before_creating_index(
        tmp_path: Path) -> None:
    """Path with two queued rows → migration dedupes, then creates index.

    Without dedupe, ``CREATE UNIQUE INDEX uq_jobs_inflight`` would
    fail on the pre-existing duplicate and abort ``init()``. The
    dedupe keeps the lowest-id queued row (matching ``claim_next``'s
    ``ORDER BY ... id ASC``) and deletes the rest.
    """
    db_dir = tmp_path / "dup-queued"
    db_dir.mkdir(parents=True)
    db = db_dir / "jobs.db"

    con = sqlite3.connect(db)
    con.executescript(_MODERN_JOBS)
    # Two queued rows for one path, plus an unrelated done row so the
    # migration has more than one path to consider.
    _insert_job(con, jid=1, path="/dup.pdf", status="queued",
                created=1_700_000_000.0)
    _insert_job(con, jid=2, path="/dup.pdf", status="queued",
                created=1_700_000_001.0)
    _insert_job(con, jid=3, path="/unrelated.pdf", status="done",
                created=1_700_000_002.0)
    con.commit()
    con.close()

    mod = _load_jobstore(db_dir)

    assert mod._ready() is True, (
        "init() must survive a DB with duplicate queued rows for the"
        " same path — a failing migration would leave the service in"
        " the no-op state (ready=False, every counter at zero)"
    )
    # The lower-id queued row survived; the higher-id duplicate is gone.
    assert _jobs_for_path(db, "/dup.pdf") == [(1, "queued")], (
        "dedupe must keep the lowest-id queued row (matches claim_next"
        " ordering) and drop the rest"
    )
    # Unrelated rows are untouched.
    assert _jobs_for_path(db, "/unrelated.pdf") == [(3, "done")]
    # And the partial unique index landed.
    assert "uq_jobs_inflight" in _index_names(db), (
        "uq_jobs_inflight must exist after init() — the cross-process"
        " in-flight backstop"
    )


def test_migration_dedupes_running_over_queued(tmp_path: Path) -> None:
    """Path with one running + one queued → keep running, drop queued.

    The dedupe preserves a worker mid-flight (status='running') over
    a queued duplicate. Losing the running row would orphan a worker
    holding the OCR engine slot; losing the queued duplicate is the
    safer trade.
    """
    db_dir = tmp_path / "running-wins"
    db_dir.mkdir(parents=True)
    db = db_dir / "jobs.db"

    con = sqlite3.connect(db)
    con.executescript(_MODERN_JOBS)
    # Lower id is queued, higher id is running — proves the dedupe
    # is status-aware, not just lowest-id.
    _insert_job(con, jid=1, path="/x.pdf", status="queued",
                created=1_700_000_000.0)
    _insert_job(con, jid=2, path="/x.pdf", status="running",
                created=1_700_000_001.0)
    con.commit()
    con.close()

    mod = _load_jobstore(db_dir)
    assert mod._ready() is True
    assert _jobs_for_path(db, "/x.pdf") == [(2, "running")], (
        "dedupe must keep the running row over the queued duplicate"
    )


def test_migration_creates_index_without_duplicates(
        tmp_path: Path) -> None:
    """Clean DB → no dedupe work, index lands, all rows survive."""
    db_dir = tmp_path / "clean"
    db_dir.mkdir(parents=True)
    db = db_dir / "jobs.db"

    con = sqlite3.connect(db)
    con.executescript(_MODERN_JOBS)
    _insert_job(con, jid=1, path="/a.pdf", status="done",
                created=1_700_000_000.0)
    _insert_job(con, jid=2, path="/b.pdf", status="queued",
                created=1_700_000_001.0)
    con.commit()
    con.close()

    mod = _load_jobstore(db_dir)
    assert mod._ready() is True
    # No rows touched.
    assert _jobs_for_path(db, "/a.pdf") == [(1, "done")]
    assert _jobs_for_path(db, "/b.pdf") == [(2, "queued")]
    # Index landed.
    assert "uq_jobs_inflight" in _index_names(db)


def test_migration_is_idempotent(tmp_path: Path) -> None:
    """Second init() against an already-migrated DB is a no-op.

    The IF NOT EXISTS clause on CREATE UNIQUE INDEX makes the
    migration safe to re-run; ``_ready()`` stays True and no rows
    disappear.
    """
    db_dir = tmp_path / "idempotent"
    db_dir.mkdir(parents=True)
    db = db_dir / "jobs.db"

    con = sqlite3.connect(db)
    con.executescript(_MODERN_JOBS)
    _insert_job(con, jid=1, path="/a.pdf", status="queued",
                created=1_700_000_000.0)
    con.commit()
    con.close()

    mod = _load_jobstore(db_dir)
    assert mod._ready() is True
    first_jobs = _jobs_for_path(db, "/a.pdf")
    assert first_jobs == [(1, "queued")]

    # Second init() — should be a complete no-op.
    mod.init()
    assert mod._ready() is True
    assert _jobs_for_path(db, "/a.pdf") == first_jobs
    assert "uq_jobs_inflight" in _index_names(db)
