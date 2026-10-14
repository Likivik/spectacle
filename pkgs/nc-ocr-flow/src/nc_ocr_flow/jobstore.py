"""SQLite-backed job history for nc-ocr-flow.

Keeps a persistent record of every job that has flowed through the
service so the panel, the NC app, and ad-hoc triage scripts can query
history without depending on the in-memory ``_jobs`` dict (which is
capped at 500 entries and resets on restart).

Design rules (per task spec):

* Stdlib ``sqlite3`` only — no extra deps.
* Path resolves from ``NC_OCR_STATE_DIR`` then ``STATE_DIRECTORY``
  (systemd ``StateDirectory=`` convention), defaulting to
  ``/var/lib/nc-ocr/jobs.db``.
* WAL + ``synchronous=NORMAL`` for cheap, durable writes.
* One table ``jobs`` with the schema spelled out below; indexes on
  ``created`` and ``status``.
* **Never raise into the caller.** Any sqlite error logs a warning and
  yields an empty/None result — the OCR pipeline must not break
  because the history DB is unavailable.
* Thread-safe: a fresh connection per call (``check_same_thread=False``
  inside a per-call connection — see ``_connect()``). FastAPI request
  threads and the worker thread can call this freely without sharing a
  connection across threads.

Public API:

* ``init()`` — create the schema if missing. Called once at startup.
* ``record_enqueue(job_dict)`` — insert with status=queued (or whatever
  the caller provided). No-op on duplicate ``id``.
* ``record_update(job_dict)`` — upsert by ``id``. Use this on every
  status change.
* ``query(limit=100, status=None, since=None, path_contains=None)`` —
  list jobs newest-first. ``since`` is a unix epoch float (seconds).
* ``stats()`` — ``{status: count, ..., total: N}``.
* ``get(job_id)`` — fetch a single job by id, or ``None``.
* ``db_path()`` — the resolved file path (useful for diagnostics/tests).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# --- Path resolution --------------------------------------------------------

_DB_PATH: Path | None = None
_INITIALISED: bool = False


def _resolve_db_path() -> Path:
    """Resolve the DB file path from env, honouring systemd StateDirectory.

    Precedence:
      1. ``NC_OCR_STATE_DIR`` (project-specific override)
      2. ``STATE_DIRECTORY`` (systemd-set, colon-separated list; first
         entry is the primary writable location for the service)
      3. ``/var/lib/nc-ocr/jobs.db`` (production default)

    The directory is created with ``mkdir(parents=True, exist_ok=True)``
    on first use. If the configured directory is not a directory (e.g.
    someone pointed the env var at a regular file) we silently fall
    back to a per-user cache path under ``$XDG_CACHE_HOME`` or
    ``~/.cache`` so the service still starts in degraded mode.
    """
    env = os.environ.get("NC_OCR_STATE_DIR") or os.environ.get(
        "STATE_DIRECTORY", ""
    )
    env = env.split(":")[0] if env else ""
    primary = Path(env) / "jobs.db" if env else Path("/var/lib/nc-ocr/jobs.db")
    primary.parent.mkdir(parents=True, exist_ok=True)
    return primary


def db_path() -> Path:
    """Return the currently configured DB path. Resolves lazily."""
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _resolve_db_path()
    return _DB_PATH


def _connect() -> sqlite3.Connection:
    """Open a short-lived connection. Caller is responsible for close()."""
    # ``isolation_level=None`` → autocommit mode; we drive transactions
    # explicitly with BEGIN/COMMIT so partial writes never leak.
    conn = sqlite3.connect(
        str(db_path()),
        timeout=10.0,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


# --- Schema ----------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id       INTEGER PRIMARY KEY,
    path     TEXT,
    nc_path  TEXT,
    node_id  INTEGER,
    engine   TEXT,
    force    INTEGER,
    status   TEXT,
    created  REAL,
    started  REAL,
    finished REAL,
    error    TEXT,
    reason   TEXT,
    result   TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);

-- Per-file OCR state. Replaces the in-memory _ocr_index dict and the
-- _ocrd_paths set, which grew with the number of files in the account.
CREATE TABLE IF NOT EXISTS files (
    path     TEXT PRIMARY KEY,
    status   TEXT,
    engine   TEXT,
    reason   TEXT,
    node_id  INTEGER,
    finished REAL,
    size     INTEGER,
    etag     TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_node   ON files(node_id);

-- Recently-processed guard (replaces the in-memory _processed_ids dict).
CREATE TABLE IF NOT EXISTS processed (
    node_id INTEGER PRIMARY KEY,
    ts      REAL
);

-- Operator settings, editable from the panel. Precedence at read time
-- is env (nix) -> this table -> built-in default.
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Billable usage per engine per day. One unit = one page for Vision
-- (see cloud.google.com/vision/pricing: each page of a PDF counts as an
-- individual image, each feature applied is one unit).
CREATE TABLE IF NOT EXISTS usage (
    day    TEXT NOT NULL,
    engine TEXT NOT NULL,
    jobs   INTEGER NOT NULL DEFAULT 0,
    pages  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, engine)
);
"""


def init() -> None:
    """Create the schema if missing. Safe to call repeatedly.

    Never raises — a broken DB path just logs a warning and leaves the
    module in a no-op state (subsequent calls also no-op silently).
    """
    global _INITIALISED
    try:
        with _connect() as conn:
            conn.executescript(_SCHEMA_SQL)
        _INITIALISED = True
        log.info("jobstore: schema ready at %s", db_path())
    except Exception as exc:  # noqa: BLE001 — spec: never raise
        log.warning("jobstore: init failed (%s) — history will be a no-op", exc)
        _INITIALISED = False


def _ready() -> bool:
    """True if init() succeeded at some point. Re-runs init() if not."""
    global _INITIALISED
    if not _INITIALISED:
        init()
    return _INITIALISED


# --- Field normalisation ---------------------------------------------------

_COLUMNS = (
    "id", "path", "nc_path", "node_id", "engine", "force", "status",
    "created", "started", "finished", "error", "reason", "result",
)


def _row_from_dict(job: dict[str, Any]) -> tuple:
    """Map a job dict to a tuple matching ``_COLUMNS``.

    ``result`` is JSON-encoded if it's a dict/list. ``force`` is coerced
    to 0/1. Timestamps (``created``/``started``/``finished``) are kept
    as floats; ``None`` is allowed for not-yet-started/finished.
    """
    force = job.get("force")
    if isinstance(force, bool):
        force_i = 1 if force else 0
    elif force is None:
        force_i = None
    else:
        force_i = 1 if force else 0

    node_id = job.get("node_id")
    if node_id is not None:
        try:
            node_id = int(node_id)
        except (TypeError, ValueError):
            node_id = None

    result = job.get("result")
    if isinstance(result, (dict, list)):
        try:
            result = json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            result = None

    return (
        job.get("id"),
        job.get("path"),
        job.get("nc_path"),
        node_id,
        job.get("engine"),
        force_i,
        job.get("status"),
        job.get("created"),
        job.get("started"),
        job.get("finished"),
        job.get("error"),
        job.get("reason"),
        result,
    )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Inverse of ``_row_from_dict`` — JSON-decodes ``result``."""
    out = {col: row[col] for col in row.keys()}
    raw = out.get("result")
    if raw:
        try:
            out["result"] = json.loads(raw)
        except (TypeError, ValueError):
            # Leave as string if it isn't valid JSON — never lose data.
            pass
    else:
        out["result"] = None
    return out


# --- Write API -------------------------------------------------------------


#: Hard cap on the SQL history so it cannot grow forever. 20k rows is
#: roughly 40 MB at ~2 KB per job; the oldest are pruned on insert.
_MAX_ROWS = 20000


def _prune(conn: "sqlite3.Connection") -> None:
    """Drop the oldest rows beyond ``_MAX_ROWS`` (best effort)."""
    conn.execute(
        "DELETE FROM jobs WHERE id IN ("
        " SELECT id FROM jobs ORDER BY created DESC, id DESC"
        " LIMIT -1 OFFSET ?)",
        (_MAX_ROWS,),
    )


def record_enqueue(job: dict[str, Any]) -> None:
    """Insert a freshly-enqueued job. No-op if ``id`` already exists.

    Spec wording: "call ``record_enqueue`` on enqueue". Insert-or-ignore
    is the safest semantics — if the worker has already written a status
    update for this id (e.g. on a fast restart), we don't clobber it.
    """
    if not _ready():
        return
    try:
        values = _row_from_dict(job)
        with _connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO jobs ("
                + ", ".join(_COLUMNS)
                + ") VALUES ("
                + ", ".join("?" for _ in _COLUMNS)
                + ")",
                values,
            )
            _prune(conn)
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: record_enqueue failed for id=%s (%s)",
                    job.get("id"), exc)


def record_update(job: dict[str, Any]) -> None:
    """Upsert by ``id``. Used on every status change.

    Spec wording: "call ``record_update`` on every job status change
    (queued/running/done/skipped/error) — best effort, never raising".

    Only the keys actually present in ``job`` are written; everything
    else is carried over from the stored row. A bare
    ``INSERT OR REPLACE`` wrote NULL into every omitted column, so a
    status-only update silently erased the job's path, engine and
    creation time.
    """
    if not _ready():
        return
    try:
        with _connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?",
                               (job.get("id"),)).fetchone()
            # Merge onto the stored row: a partial update must not
            # blank the fields it does not mention.
            merged = _row_to_dict(row) if row is not None else {}
            merged.update({k: v for k, v in job.items() if k in _COLUMNS})
            values = _row_from_dict(merged)
            conn.execute(
                "INSERT OR REPLACE INTO jobs ("
                + ", ".join(_COLUMNS)
                + ") VALUES ("
                + ", ".join("?" for _ in _COLUMNS)
                + ")",
                values,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: record_update failed for id=%s (%s)",
                    job.get("id"), exc)


# --- Read API --------------------------------------------------------------


def claim_next() -> dict | None:
    """Atomically move the oldest 'queued' job to 'running', return it.

    The work list lives in SQLite rather than in RAM, so the service
    can hold an arbitrarily large backlog without growing — workers
    pull one row at a time. ``BEGIN IMMEDIATE`` takes the write lock
    *before* the SELECT, so two workers can never claim the same row.
    Returns ``None`` when there is nothing to do (or the DB is down).
    """
    import time as _time

    if not _ready():
        return None
    try:
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'queued'"
                " ORDER BY id LIMIT 1",
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            started = _time.time()
            conn.execute(
                "UPDATE jobs SET status = 'running', started = ?"
                " WHERE id = ?",
                (started, row["id"]),
            )
            conn.execute("COMMIT")
            job = _row_to_dict(row)
            job["status"] = "running"
            job["started"] = started
            return job
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: claim_next failed (%s)", exc)
        return None


def requeue_stale() -> int:
    """Put jobs left in 'running' by a crash/restart back to 'queued'.

    Called once at startup: with no workers running yet, every
    'running' row is by definition abandoned.
    """
    if not _ready():
        return 0
    try:
        with _connect() as conn:
            cur = conn.execute(
                "UPDATE jobs SET status = 'queued', started = NULL"
                " WHERE status = 'running'",
            )
            return cur.rowcount or 0
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: requeue_stale failed (%s)", exc)
        return 0


def get(job_id: int) -> dict[str, Any] | None:
    """Fetch one job by id, or ``None`` if missing or on error."""
    if not _ready():
        return None
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return _row_to_dict(row) if row is not None else None
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: get(%s) failed (%s)", job_id, exc)
        return None


def query(
    limit: int = 100,
    status: str | None = None,
    since: float | int | str | None = None,
    path_contains: str | None = None,
) -> list[dict[str, Any]]:
    """Return jobs newest-first.

    Args:
        limit: max rows to return (default 100).
        status: optional exact-match filter on ``status``.
        since: optional cutoff — only jobs with ``created >= since``.
            Accepts a unix epoch (float/int) or an ISO-8601 string.
        path_contains: optional ``LIKE '%substring%'`` on ``path``.

    Returns an empty list on any error (never raises).
    """
    if not _ready():
        return []
    try:
        lim = max(1, min(int(limit), 5000))  # hard ceiling
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if since is not None:
            since_f = _coerce_since(since)
            if since_f is not None:
                clauses.append("created >= ?")
                params.append(since_f)
        if path_contains:
            # Escape LIKE metacharacters: a literal '%' or '_' in a
            # path must not turn into a wildcard.
            escaped = (str(path_contains)
                       .replace("\\", "\\\\")
                       .replace("%", "\\%")
                       .replace("_", "\\_"))
            clauses.append("path LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT * FROM jobs" + where +
            " ORDER BY created DESC, id DESC LIMIT ?"
        )
        params.append(lim)
        with _connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: query failed (%s)", exc)
        return []


def _coerce_since(value: Any) -> float | None:
    """Best-effort coercion of the ``since`` param to a float epoch."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            from datetime import datetime, timezone
            iso = s.replace("Z", "+00:00") if s.endswith("Z") else s
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            pass
        try:
            return float(s)
        except ValueError:
            return None
    return None


def stats() -> dict[str, Any]:
    """Return ``{status: count, ..., total: N}`` over the full table.
    Never raises — returns ``{"total": 0, ...}`` on error.
    """
    out: dict[str, Any] = {"total": 0}
    if not _ready():
        return out
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
            ).fetchall()
        for r in rows:
            out[r["status"] or "unknown"] = r["n"]
            out["total"] += r["n"]
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: stats failed (%s)", exc)
        return out


# --- Test-only helpers -----------------------------------------------------

# --- File index -------------------------------------------------------------


def file_put(record: dict[str, Any]) -> None:
    """Upsert one file's OCR state. Never raises."""
    if not _ready():
        return
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO files"
                " (path, status, engine, reason, node_id, finished, size, etag)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (record.get("path"), record.get("status"),
                 record.get("engine"), record.get("reason"),
                 record.get("node_id"), record.get("finished"),
                 record.get("size"), record.get("etag")),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: file_put failed for %s (%s)",
                    record.get("path"), exc)


def file_get(path: str) -> dict[str, Any] | None:
    """One file's stored state, or ``None``."""
    if not _ready():
        return None
    try:
        with _connect() as conn:
            row = conn.execute("SELECT * FROM files WHERE path = ?",
                               (path,)).fetchone()
            return dict(row) if row is not None else None
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: file_get failed (%s)", exc)
        return None


def file_done_paths() -> set[str]:
    """Every path already OCR'd successfully (for ``skip_ocrd``)."""
    if not _ready():
        return set()
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT path FROM files WHERE status = 'done'").fetchall()
            return {r[0] for r in rows if r[0]}
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: file_done_paths failed (%s)", exc)
        return set()


def file_all() -> dict[str, dict[str, Any]]:
    """The whole index as ``{path: record}`` (used by the NC app)."""
    if not _ready():
        return {}
    try:
        with _connect() as conn:
            return {r["path"]: dict(r) for r in
                    conn.execute("SELECT * FROM files").fetchall()}
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: file_all failed (%s)", exc)
        return {}


def file_count() -> int:
    if not _ready():
        return 0
    try:
        with _connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: file_count failed (%s)", exc)
        return 0


def file_forget(path: str) -> None:
    """Drop one path from the index (``/rescan`` clears it first)."""
    if not _ready():
        return
    try:
        with _connect() as conn:
            conn.execute("DELETE FROM files WHERE path = ?", (path,))
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: file_forget failed (%s)", exc)


def file_import(mapping: dict[str, Any]) -> int:
    """One-time import of the legacy ``ocr_index.json`` mapping."""
    if not mapping or not _ready():
        return 0
    try:
        with _connect() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO files"
                " (path, status, engine, reason, node_id, finished, size, etag)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(p, m.get("status"), m.get("engine"), m.get("reason"),
                  m.get("node_id"), m.get("finished"), m.get("size"),
                  m.get("etag")) for p, m in mapping.items()],
            )
        return len(mapping)
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: file_import failed (%s)", exc)
        return 0


# --- Recently-processed guard ----------------------------------------------


def claim_node(node_id: int, ttl: float) -> bool:
    """Atomically claim ``node_id`` for processing.

    Returns ``False`` when the node was already claimed within ``ttl``,
    i.e. a job for it is queued or running. On a DB error it returns
    ``True`` (fail open): without a store we would rather process a file
    twice than skip it forever.
    """
    if not node_id or not _ready():
        return True
    import time as _time

    now = _time.time()
    try:
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT ts FROM processed WHERE node_id = ?",
                               (node_id,)).fetchone()
            if row is not None and now - row[0] <= ttl:
                conn.execute("COMMIT")
                return False
            conn.execute(
                "INSERT OR REPLACE INTO processed (node_id, ts)"
                " VALUES (?, ?)", (node_id, now))
            conn.execute("DELETE FROM processed WHERE ts < ?", (now - ttl,))
            conn.execute("COMMIT")
            return True
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: claim_node failed (%s)", exc)
        return True


def node_forget(node_id: int) -> None:
    """Clear a node's claim (``/rescan`` must be able to re-OCR)."""
    if not node_id or not _ready():
        return
    try:
        with _connect() as conn:
            conn.execute("DELETE FROM processed WHERE node_id = ?", (node_id,))
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: node_forget failed (%s)", exc)


# --- Settings ---------------------------------------------------------------


def settings_all() -> dict[str, str]:
    if not _ready():
        return {}
    try:
        with _connect() as conn:
            return {r["key"]: r["value"] for r in
                    conn.execute("SELECT key, value FROM settings").fetchall()}
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: settings_all failed (%s)", exc)
        return {}


def setting_put(key: str, value: str) -> None:
    if not _ready():
        return
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)))
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: setting_put failed (%s)", exc)


def setting_delete(key: str) -> None:
    if not _ready():
        return
    try:
        with _connect() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: setting_delete failed (%s)", exc)


# --- Billable usage ---------------------------------------------------------


def usage_add(engine: str | None, pages: int = 0, jobs: int = 1) -> None:
    """Add one finished job's billable usage. Never raises.

    For Vision one unit = one page (each PDF page counts as an individual
    image), so ``pages`` is what costs money, not the request count.
    """
    if not _ready():
        return
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO usage (day, engine, jobs, pages) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(day, engine) DO UPDATE SET"
                "   jobs = jobs + excluded.jobs,"
                "   pages = pages + excluded.pages",
                (time.strftime("%Y-%m-%d", time.gmtime()), engine or "unknown",
                 max(0, int(jobs)), max(0, int(pages))),
            )
    except Exception as exc:
        log.warning("jobstore: usage_add failed (%s)", exc)


def usage_summary(days: int = 7) -> list[dict[str, Any]]:
    """Per-day usage rows, newest first."""
    if not _ready():
        return []
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT day, engine, jobs, pages FROM usage"
                " ORDER BY day DESC, engine ASC LIMIT ?",
                (max(1, min(int(days) * 4, 500)),),
            ).fetchall()
        return [{"day": r[0], "engine": r[1], "jobs": r[2], "pages": r[3]}
                for r in rows]
    except Exception as exc:
        log.warning("jobstore: usage_summary failed (%s)", exc)
        return []


def usage_month(engine: str | None = None) -> dict[str, int]:
    """Jobs and pages for the current calendar month, optionally per engine."""
    empty = {"jobs": 0, "pages": 0}
    if not _ready():
        return empty
    try:
        sql = ("SELECT COALESCE(SUM(jobs), 0), COALESCE(SUM(pages), 0)"
               " FROM usage WHERE day LIKE ?")
        args: list[Any] = [time.strftime("%Y-%m", time.gmtime()) + "%"]
        if engine:
            sql += " AND engine = ?"
            args.append(engine)
        with _connect() as conn:
            row = conn.execute(sql, args).fetchone()
        return {"jobs": int(row[0] or 0), "pages": int(row[1] or 0)}
    except Exception as exc:
        log.warning("jobstore: usage_month failed (%s)", exc)
        return empty


def _reset_for_tests() -> None:
    """Drop all rows. Only meaningful in tests."""
    global _INITIALISED, _DB_PATH
    _INITIALISED = False
    _DB_PATH = None
    try:
        p = db_path()
        if p.exists():
            p.unlink()
    except Exception:
        pass