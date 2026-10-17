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
    id           INTEGER PRIMARY KEY,
    path         TEXT,
    nc_path      TEXT,
    node_id      INTEGER,
    engine       TEXT,
    force        INTEGER,
    status       TEXT,
    created      REAL,
    started      REAL,
    finished     REAL,
    error        TEXT,
    reason       TEXT,
    result       TEXT,
    -- Retry tracking. C6 additive migration adds these to existing
    -- production databases via ``_migrate_add_retry_columns`` at
    -- ``init()`` time; on fresh databases the columns are part of
    -- the schema below. ``DEFAULT 0`` is required (not ``NOT NULL``
    -- with a default) so ``ALTER TABLE ADD COLUMN`` succeeds on
    -- existing rows in SQLite.
    --
    -- B2 audit: ``attempts`` is bumped ONLY on the queued retry
    -- row, never on the failed row that spawned the retry — that
    -- is what stops ``stats()`` from double-counting one retry as
    -- two.
    attempts     INTEGER DEFAULT 0,
    next_run_at  REAL    DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
-- NB: the index on jobs(next_run_at) is created by
-- ``_migrate_add_retry_columns`` AFTER its ALTER TABLEs, never here:
-- on a database that predates those columns this statement would fail
-- with "no such column: next_run_at" and abort the whole init. (PR #68
-- was the fix that put the index behind the ALTERs; B2 audit confirms
-- the index lives in the migration, not the schema script.)

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
# C6: additive migration for the retry-related columns.
            # Idempotent: the function checks ``PRAGMA table_info``
            # before altering, so calling it on a fresh DB (where
            # the columns do not exist yet but the schema created
            # them) and on an upgraded production DB (where they
            # already exist) are both no-ops beyond the second
            # ``SELECT`` from ``PRAGMA table_info``. The index on
            # ``next_run_at`` is created INSIDE this migration AFTER
            # the ALTERs (PR #68 fixed the ordering bug that put it
            # in the schema script).
            _migrate_add_retry_columns(conn)
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

#: Columns we expose to callers. ``attempts`` and ``next_run_at`` are
#: the C6 additive migration: existing rows have NULL/default, new
#: rows record a retry counter and a "do not claim before" timestamp.
#: See ``_migrate_add_retry_columns`` for the additive ALTER.
_COLUMNS = (
    "id", "path", "nc_path", "node_id", "engine", "force", "status",
    "created", "started", "finished", "error", "reason", "result",
    "attempts", "next_run_at",
)


def _migrate_add_retry_columns(conn: "sqlite3.Connection") -> None:
    """C6: idempotent additive migration for retry-related columns.

    A new field on the ``jobs`` table MUST be safe to add to an
    existing production database, not just to fresh test DBs. SQLite
    supports ``ALTER TABLE ADD COLUMN`` but does NOT support a
    default for ``NOT NULL`` columns, and we want the column to
    exist on every existing row (a fresh ``SELECT *`` on a database
    without the column would raise). We:

      1. Read ``PRAGMA table_info(jobs)`` to discover what is
         already there.
      2. ``ALTER TABLE ADD COLUMN ... DEFAULT 0`` for each missing
         column. The default is required so existing rows get a
         value (``DEFAULT 0`` for both ``attempts`` and
         ``next_run_at`` is correct: 0 attempts and 0 = "claim
         immediately" is the safe pre-C6 behaviour).

    Safe to call on every ``init()``: the PRAGMA check + the
    ``DEFAULT 0`` make it a no-op on databases that already have
    the columns.
    """
    try:
        cols = {row[1] for row in
                conn.execute("PRAGMA table_info(jobs)").fetchall()}
    except Exception:  # noqa: BLE001
        return
    if "attempts" not in cols:
        try:
            conn.execute(
                "ALTER TABLE jobs ADD COLUMN attempts INTEGER DEFAULT 0",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("jobstore: ADD COLUMN attempts failed (%s)", exc)
    if "next_run_at" not in cols:
        try:
            conn.execute(
                "ALTER TABLE jobs ADD COLUMN next_run_at REAL DEFAULT 0",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("jobstore: ADD COLUMN next_run_at failed (%s)", exc)
    # The index on the retry column MUST be created here, after the
    # ALTERs above — never in the schema script. On a database that
    # predates these columns the schema script's CREATE INDEX runs
    # before this migration and raises "no such column: next_run_at",
    # which aborts init() and leaves jobstore permanently in the
    # no-op state (no job history, no file index). That ordering bug
    # disabled the state layer on the first production rollout.
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_next_run"
            " ON jobs(next_run_at)",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: CREATE INDEX idx_jobs_next_run failed (%s)", exc)


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

    # C6: attempts/next_run_at. ``_migrate_add_retry_columns`` adds
    # these to existing rows with DEFAULT 0, so ``.get(..., 0)`` is
    # safe for callers that pre-date the migration.
    attempts = job.get("attempts")
    try:
        attempts_i = int(attempts) if attempts is not None else 0
    except (TypeError, ValueError):
        attempts_i = 0
    next_run_at = job.get("next_run_at")
    try:
        next_run_at_f = float(next_run_at) if next_run_at is not None else 0.0
    except (TypeError, ValueError):
        next_run_at_f = 0.0

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
        attempts_i,
        next_run_at_f,
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


def _coerce_col(name: str, value: Any) -> Any:
    """Per-column defaulting for INSERT value lists.

    Some columns (e.g. ``attempts NOT NULL DEFAULT 0``) reject an
    explicit ``None`` and rely on the schema default only when the
    column is omitted from the INSERT. The new ``attempts`` column
    was added with that NOT NULL guarantee, so a job dict whose
    caller pre-dates the retry track will hand us ``None`` and the
    INSERT would raise. Substituting the SQL default up-front keeps
    every existing call site working unchanged.
    """
    if name == "attempts" and value is None:
        return 0
    return value


def _prune(conn: "sqlite3.Connection") -> None:
    """Drop the oldest rows beyond ``_MAX_ROWS`` (best effort).

    B4 fix: a scheduled retry (60s/300s backoff) sits at
    ``status='queued'`` with ``next_run_at`` set in the future. The
    previous ordering by ``created DESC`` ignored ``next_run_at`` and
    could prune a row whose retry had not fired yet, leaving the queue
    silently short. Only prune rows that are not waiting on a backoff
    (``COALESCE(next_run_at, 0) <= now``); rows with a future
    ``next_run_at`` are preserved regardless of how old they are.
    """
    import time as _time
    now = _time.time()
    conn.execute(
        "DELETE FROM jobs WHERE id IN ("
        " SELECT id FROM jobs"
        "  WHERE COALESCE(next_run_at, 0) <= ?"
        "  ORDER BY created DESC, id DESC"
        "  LIMIT -1 OFFSET ?"
        ")",
        (now, _MAX_ROWS),
    )


def record_enqueue(job: dict[str, Any]) -> int:
    """Insert a freshly-enqueued job. Returns the assigned ``id``.

    Id assignment
    -------------
    The DB is the sole source of truth for the ``jobs.id`` sequence —
    not the in-process counter (which would lose state on every
    service restart and silently discard new inserts that collided
    with a previously persisted id). Caller may pre-set ``job['id']``
    (legacy tests / explicit ids) or leave it unset; in the latter
    case we omit ``id`` from the INSERT and read back ``lastrowid``.

    Errors
    ------
    * Application-level duplicate (an explicit ``id`` already exists)
      **raises** :class:`RuntimeError`. Silent ``INSERT OR IGNORE`` is
      the exact shape of the bug we removed; a non-unique id means the
      previous job with that id is *not* the row we wanted, and there
      is no safe no-op. Crash loud.
    * DB-level faults (DB unreachable, disk full, schema mismatch)
      continue to log + return ``None`` so the OCR pipeline keeps
      running. The history is a side-channel; the queue is the
      pipeline. (See the module-level design rule.)

    The new id is written back into ``job['id']`` so callers using the
    returned dict see the canonical id even when they did not provide
    one. ``work_available`` (the queue's wakeup primitive) is **not**
    fired here — the caller already drives it after the SQL returns.
    """
    if not _ready():
        return None  # type: ignore[return-value]
    explicit_id = job.get("id")
    # Build the value tuple WITHOUT id when the caller didn't set one
    # so SQLite's rowid alias assigns a fresh, collision-free id.
    if explicit_id is None:
        cols = [c for c in _COLUMNS if c != "id"]
        placeholders = ", ".join("?" for _ in cols)
        values = [_coerce_col(c, job.get(c)) for c in cols]
    else:
        cols = list(_COLUMNS)
        placeholders = ", ".join("?" for _ in cols)
        values = [_coerce_col(c, job.get(c)) for c in cols]
    try:
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "INSERT INTO jobs ("
                + ", ".join(cols)
                + ") VALUES ("
                + placeholders
                + ")",
                values,
            )
            assigned = int(cur.lastrowid or (explicit_id or 0))
            conn.execute("COMMIT")
            _prune(conn)
    except sqlite3.IntegrityError as exc:
        # Explicit-id collision. Loud: silent no-op is the bug.
        raise RuntimeError(
            f"jobstore: id collision on enqueue (id={explicit_id!r}); "
            f"refusing to silently discard the new job. Did the "
            f"in-memory job-id counter restart on a service boot "
            f"while persisted rows are still at the same id? "
            f"({exc})"
        ) from exc
    except sqlite3.Error as exc:  # noqa: BLE001
        # DB-level fault — preserve the design rule (OCR pipeline must
        # not break because the history DB is unavailable) and just
        # log. The job is otherwise lost; the next ``/rescan`` or
        # webhook event will re-enqueue it.
        log.warning("jobstore: record_enqueue failed for id=%s (%s)",
                    explicit_id, exc)
        return None  # type: ignore[return-value]
    job["id"] = assigned
    return assigned


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

    C6: skips jobs whose ``next_run_at`` is in the future (these are
    scheduled retries waiting for their backoff window). Without
    that filter the worker would re-run a transient-failure job
    immediately, defeating the exponential backoff. Ordering is
    ``next_run_at ASC, id ASC`` so the soonest-due retry jumps the
    queue, but a fresh first-time job is still claimed before any
    retry that is also already due.
    """
    import time as _time

    if not _ready():
        return None
    try:
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'queued'"
                " AND COALESCE(next_run_at, 0) <= ?"
                " ORDER BY COALESCE(next_run_at, 0) ASC, id ASC"
                " LIMIT 1",
                (_time.time(),),
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


def enqueue_retry(
    job: dict[str, Any], *, attempts: int, next_run_at: float
) -> int | None:
    """C6: schedule a retry of ``job`` for ``next_run_at`` (unix epoch).

    Creates a fresh ``jobs`` row carrying the bumped ``attempts``
    counter and the backoff timestamp. ``claim_next`` will skip the
    row until ``next_run_at`` arrives. Returns the new id (or
    ``None`` on DB fault — same soft-fail shape as
    :func:`record_enqueue`).

    Why a new row instead of mutating the failed one? Keeping the
    failed row makes the failure visible in the history (the panel
    shows it once, then sees the eventual retry succeed), and
    pruning by ``created`` then expires the older history naturally
    instead of relying on a bookkeeping flip.
    """
    if not _ready():
        return None
    payload = dict(job)
    payload.pop("id", None)        # fresh id
    payload["status"] = "queued"
    payload["started"] = None
    payload["finished"] = None
    payload["error"] = None
    payload["attempts"] = int(attempts)
    payload["next_run_at"] = float(next_run_at)
    return record_enqueue(payload)


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
    """Return ``{status: count, ..., total: N, retries_total: R, retries_queued: Q}``.

    Counts every row in ``jobs`` once, grouped by ``status``. Adds:

      * ``retries_total``: number of rows whose ``attempts > 0``
        (i.e. they represent a retry attempt — B2 audit contract:
        ``_maybe_schedule_retry`` bumps ``attempts`` ONLY on the
        queued retry row, never on the failed row that spawned the
        retry, so this count never double-counts one retry as two).
      * ``retries_queued``: the subset of ``retries_total`` whose
        ``status='queued'`` (i.e. currently waiting on a backoff
        window — the work the operator is most likely to be
        triaging when a transient outage has just ended).

    Never raises — returns ``{"total": 0, "retries_total": 0,
    "retries_queued": 0}`` on error.
    """
    out: dict[str, Any] = {"total": 0, "retries_total": 0,
                           "retries_queued": 0}
    if not _ready():
        return out
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
            ).fetchall()
            # C6: retries counts. ``retries_queued`` is the
            # "scheduled but not yet due" set — the work the operator
            # is most likely to be triaging when a transient
            # outage has just ended.
            r_retry_total = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs"
                " WHERE COALESCE(attempts, 0) > 0"
            ).fetchone()
            r_retry_queued = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs"
                " WHERE status = 'queued'"
                " AND COALESCE(attempts, 0) > 0"
            ).fetchone()
            for r in rows:
                out[r["status"] or "unknown"] = r["n"]
                out["total"] += r["n"]
            out["retries_total"] = (r_retry_total["n"]
                                    if r_retry_total is not None else 0)
            out["retries_queued"] = (r_retry_queued["n"]
                                     if r_retry_queued is not None else 0)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: stats failed (%s)", exc)
        return out


def in_flight_job_for_path(nc_path: str) -> dict[str, Any] | None:
    """The currently-queued-or-running job for ``nc_path``, else ``None``.

    B1 fix helper: ``_enqueue`` checks this before inserting a fresh
    row so a force=True caller cannot spawn a second concurrent job
    for a path that is already being OCR'd (the original "double
    Vision billing" defect). The check is path-only and status-only;
    it does not consult ``force`` or ``attempts``.

    Never raises — returns ``None`` on error or no-row.
    """
    if not _ready() or not nc_path:
        return None
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE path = ?"
                " AND status IN ('queued', 'running')"
                " ORDER BY created DESC, id DESC LIMIT 1",
                (nc_path,),
            ).fetchone()
        return _row_to_dict(row) if row is not None else None
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: in_flight_job_for_path failed (%s)", exc)
        return None


def record_retry(parent: dict[str, Any], *, next_run_at: float) -> int | None:
    """Schedule one retry attempt for the path that just failed.

    B2 fix: bump ``attempts`` on the *retry* row (not the failed one)
    so ``retries_total`` counts retry attempts once. The failed row
    stays at ``status='error'`` with ``attempts=0``; the retry row
    is enqueued at ``status='queued'`` with ``attempts = max(1,
    parent.get('attempts') or 0) + 1`` and ``next_run_at`` set so a
    future ``_prune`` cannot evict it before the backoff fires.

    Returns the new job id, or ``None`` on error. The thread is then
    responsible for waking a worker via the existing ``_work_available``
    signal when ``next_run_at`` falls due.
    """
    if not _ready():
        return None
    import time as _time

    parent_id = parent.get("id")
    parent_path = parent.get("path") or parent.get("nc_path")
    parent_engine = parent.get("engine")
    try:
        retries_so_far = int(parent.get("attempts") or 0)
    except (TypeError, ValueError):
        retries_so_far = 0
    new_retry = {
        # id left unset → SQLite assigns
        "path": parent_path,
        "nc_path": parent_path,
        "node_id": parent.get("node_id"),
        "engine": parent_engine,
        "force": 0,                   # a retry honours the original guard
        "status": "queued",
        "created": _time.time(),
        "started": None,
        "finished": None,
        "result": None,
        "error": None,
        "reason": None,
        "attempts": max(1, retries_so_far) + 1,
        "next_run_at": next_run_at,
    }
    try:
        return record_enqueue(new_retry)
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: record_retry failed for parent id=%s (%s)",
                    parent_id, exc)
        return None


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


def file_paths_by_status(statuses: list[str], limit: int = 500) -> list[str]:
    """Paths in the file index whose ``status`` is in ``statuses``.

    Bounded (``limit`` rows) and ordered by ``finished`` ASC so the
    reconciler sees the oldest rows first — those are the rows most
    likely to be stale (the 36 phantom-errors on production were
    rows from the very first run of the service). Used by the
    stale-row reconciler (C5); the NC app reads through ``file_all``
    and does not need this.
    """
    if not _ready() or not statuses:
        return []
    placeholders = ",".join("?" * len(statuses))
    try:
        with _connect() as conn:
            rows = conn.execute(
                f"SELECT path FROM files"
                f" WHERE status IN ({placeholders})"
                f" ORDER BY COALESCE(finished, 0) ASC LIMIT ?",
                (*statuses, int(limit)),
            ).fetchall()
        return [r["path"] for r in rows if r["path"]]
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: file_paths_by_status failed (%s)", exc)
        return []


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


def orphaned_queued_paths() -> list[str]:
    """Paths left ``status='queued'`` with no matching in-flight job row.

    A file row at ``status='queued'`` is an *orphan* when the ``jobs``
    table has no row whose ``path`` or ``nc_path`` matches the file and
    whose status is still ``queued`` or ``running``. The two original
    shapes of this state:

      * an old in-process job-id counter collided on a service restart
        (fixed earlier — ``record_enqueue`` now reads ``lastrowid``),
        so the row insert was silently dropped after the file row was
        already promoted to ``queued``;
      * the ``jobs`` row was pruned or lost but the file row survived
        (the SQLite ``jobs`` history is capped at 20 000 rows and the
        queue worker keeps no in-memory copy).

    The reconciler consumes this list to re-enqueue the path so a
    worker picks it up. Genuinely running jobs are *not* touched: while
    a worker holds a job the file row stays at ``queued`` (we only
    write the terminal status once the worker finishes), so the join
    below correctly excludes rows that are actively being processed.

    Never raises; returns ``[]`` on any DB error.
    """
    if not _ready():
        return []
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT f.path FROM files f"
                " WHERE f.status = 'queued'"
                "   AND NOT EXISTS ("
                "     SELECT 1 FROM jobs j"
                "     WHERE (j.nc_path = f.path OR j.path = f.path)"
                "       AND j.status IN ('queued', 'running')"
                "   )"
            ).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: orphaned_queued_paths failed (%s)", exc)
        return []


def file_reset_to(path: str, status: str = "") -> None:
    """Reset (or clear) a file row's status field.

    Used by the reconciler when an operator wants to forget a file's
    in-flight state without deleting the row outright — e.g. when the
    goal is to make ``/scan-all`` re-pick it up. ``status=""`` clears
    the status column so the path no longer counts as queued/running
    in any path-in-flight check.

    Never raises.
    """
    if not _ready():
        return
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE files SET status = ?, finished = ?"
                " WHERE path = ?",
                (status, time.time() if status else None, path),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("jobstore: file_reset_to failed (%s)", exc)


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