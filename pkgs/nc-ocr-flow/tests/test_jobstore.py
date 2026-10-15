"""Tests for nc_ocr_flow.jobstore — stdlib-only.

Run on poweredge via ``/var/lib/nc-ocr/venv-v4/bin/python -m pytest
tests/test_jobstore.py -v`` or directly as ``python tests/test_jobstore.py``.

Each test creates its own tempdir + DB path under ``tmp_path`` and
points ``NC_OCR_STATE_DIR`` at it, so the suite is hermetic and
parallel-safe (separate files, no shared state).
"""
from __future__ import annotations

# Make the in-tree ``nc_ocr_flow`` package importable when this file is
# run as a plain script. Pytest installs the package via pyproject.toml
# so this is a no-op there.
import sys
from pathlib import Path  # noqa: E402
_HERE = Path(__file__).resolve().parent
_SRC = (_HERE.parent / "src").resolve()
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import importlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import traceback


class _Env:
    """Context manager: temporarily set env vars and restore on exit."""

    def __init__(self, **values):
        self.values = values
        self._saved: dict = {}

    def __enter__(self):
        for k, v in self.values.items():
            self._saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, prev in self._saved.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev
        return False


def _isolated_jobstore(tmp: Path, name: str = "jobstore"):
    """Reload the jobstore module with a clean DB under ``tmp/name``."""
    db_dir = tmp / name
    db_dir.mkdir(parents=True, exist_ok=True)
    for mod_name in list(sys.modules):
        if mod_name == "nc_ocr_flow.jobstore":
            del sys.modules[mod_name]
    with _Env(NC_OCR_STATE_DIR=str(db_dir)):
        mod = importlib.import_module("nc_ocr_flow.jobstore")
        mod._reset_for_tests()
        mod.init()
    return mod


def _make_job(i: int, status: str = "queued", **overrides) -> dict:
    j = {
        "id": i,
        "path": overrides.pop("path", f"/admin/files/Documents/doc-{i:04d}.pdf"),
        "nc_path": overrides.pop("nc_path", f"/admin/files/Documents/doc-{i:04d}.pdf"),
        "node_id": overrides.pop("node_id", 1000 + i),
        "engine": overrides.pop("engine", "google"),
        "force": overrides.pop("force", False),
        "status": status,
        "created": overrides.pop("created", 1_700_000_000.0 + i),
        "started": overrides.pop("started", None),
        "finished": overrides.pop("finished", None),
        "error": overrides.pop("error", None),
        "reason": overrides.pop("reason", None),
        "result": overrides.pop("result", None),
    }
    j.update(overrides)
    return j


# ---------------------------------------------------------------------------
# Regression tests for the audit findings
# ---------------------------------------------------------------------------


def test_partial_update_preserves_unmentioned_fields(tmp_path: Path) -> None:
    """A status-only update must not blank path/engine/created.

    The old implementation used ``INSERT OR REPLACE``, which wrote
    NULL into every column the caller did not pass.
    """
    mod = _isolated_jobstore(tmp_path, "partial")
    mod.record_enqueue(_make_job(1, engine="google", force=True))
    mod.record_update({"id": 1, "status": "running", "started": 123.0})
    mod.record_update({"id": 1, "status": "done", "finished": 124.0,
                       "result": {"chars": 7}})
    row = mod.get(1)
    assert row is not None
    assert row["path"] == "/admin/files/Documents/doc-0001.pdf"
    assert row["nc_path"] == "/admin/files/Documents/doc-0001.pdf"
    assert row["node_id"] == 1001
    assert row["engine"] == "google"
    assert bool(row["force"]) is True
    assert row["created"] == 1_700_000_001.0
    assert row["status"] == "done"
    assert row["started"] == 123.0
    assert row["finished"] == 124.0
    assert row["result"] == {"chars": 7}


def test_path_contains_escapes_like_wildcards(tmp_path: Path) -> None:
    """A literal '%' or '_' in path_contains must not act as a wildcard."""
    mod = _isolated_jobstore(tmp_path, "like")
    mod.record_enqueue(_make_job(1, path="/admin/files/Documents/100%_done.pdf"))
    mod.record_enqueue(_make_job(2, path="/admin/files/Documents/other.pdf"))
    assert [j["id"] for j in mod.query(path_contains="%")] == [1]
    assert [j["id"] for j in mod.query(path_contains="_")] == [1]
    assert [j["id"] for j in mod.query(path_contains="100%_done")] == [1]
    assert [j["id"] for j in mod.query(path_contains="other")] == [2]


def test_retention_prunes_oldest_rows(tmp_path: Path, monkeypatch) -> None:
    """``record_enqueue`` must drop rows beyond the cap."""
    mod = _isolated_jobstore(tmp_path, "retention")
    monkeypatch.setattr(mod, "_MAX_ROWS", 5)
    for i in range(1, 13):
        mod.record_enqueue(_make_job(i))
    ids = sorted(j["id"] for j in mod.query(limit=100))
    assert ids == [8, 9, 10, 11, 12], ids


def test_files_index_roundtrip(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, "files")
    mod.file_put({"path": "/u/files/a.pdf", "status": "done",
                  "engine": "google", "reason": None, "node_id": 7,
                  "finished": 1.5, "size": 10, "etag": "abc"})
    got = mod.file_get("/u/files/a.pdf")
    assert got and got["status"] == "done" and got["etag"] == "abc"
    assert mod.file_get("/u/files/missing.pdf") is None
    assert mod.file_done_paths() == {"/u/files/a.pdf"}
    assert mod.file_count() == 1
    assert set(mod.file_all()) == {"/u/files/a.pdf"}
    # Re-queueing a file makes it stop counting as done.
    mod.file_put({"path": "/u/files/a.pdf", "status": "queued"})
    assert mod.file_get("/u/files/a.pdf")["status"] == "queued"
    assert mod.file_done_paths() == set()
    mod.file_forget("/u/files/a.pdf")
    assert mod.file_count() == 0


def test_file_import_migrates_the_old_json_index(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, "import")
    n = mod.file_import({"/u/files/a.pdf": {"status": "done",
                                            "engine": "google",
                                            "reason": None, "node_id": 1,
                                            "finished": 1.0, "size": 5,
                                            "etag": "e"}})
    assert n == 1
    assert mod.file_get("/u/files/a.pdf")["status"] == "done"


def test_claim_node_is_exclusive_and_expires(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, "claimnode")
    assert mod.claim_node(42, 60.0) is True
    assert mod.claim_node(42, 60.0) is False   # second caller loses
    assert mod.claim_node(0, 60.0) is True     # no node id -> always allowed
    assert mod.claim_node(42, 0.0) is True     # ttl expired -> reclaimable
    mod.node_forget(42)
    assert mod.claim_node(42, 60.0) is True


def test_claim_node_is_atomic_under_concurrency(tmp_path: Path) -> None:
    import threading

    mod = _isolated_jobstore(tmp_path, "claimrace")
    wins: list[int] = []
    lock = threading.Lock()

    def _try():
        if mod.claim_node(99, 60.0):
            with lock:
                wins.append(1)

    threads = [threading.Thread(target=_try) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(wins) == 1, f"exactly one claim must win, got {len(wins)}"


def test_settings_roundtrip(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, "settings")
    assert mod.settings_all() == {}
    mod.setting_put("NC_OCR_WORKERS", "3")
    assert mod.settings_all()["NC_OCR_WORKERS"] == "3"
    mod.setting_put("NC_OCR_WORKERS", "5")          # overwrite
    assert mod.settings_all()["NC_OCR_WORKERS"] == "5"
    mod.setting_delete("NC_OCR_WORKERS")
    assert "NC_OCR_WORKERS" not in mod.settings_all()


def test_usage_counters_accumulate(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, "usage")
    assert mod.usage_month("google") == {"jobs": 0, "pages": 0}
    mod.usage_add("google", pages=12)
    mod.usage_add("google", pages=3)
    mod.usage_add("minimax", pages=5)
    g = mod.usage_month("google")
    assert g["jobs"] == 2 and g["pages"] == 15, g
    assert mod.usage_month()["pages"] == 20      # both engines
    rows = mod.usage_summary(7)
    assert rows and rows[0]["engine"] == "google" and rows[0]["pages"] == 15, rows
    assert mod.usage_month("tesseract") == {"jobs": 0, "pages": 0}


def test_usage_add_never_raises_on_broken_db(tmp_path: Path) -> None:
    """A broken DB path must stay silent, not raise into the caller."""
    import importlib
    import sys

    bad = tmp_path / "not-a-dir"
    bad.write_text("file, not a directory")
    old = os.environ.get("NC_OCR_STATE_DIR")
    os.environ["NC_OCR_STATE_DIR"] = str(bad)      # a FILE, not a directory
    try:
        for name in ("nc_ocr_flow.jobstore", "nc_ocr_flow.webhook_server"):
            sys.modules.pop(name, None)
        mod = importlib.import_module("nc_ocr_flow.jobstore")
        mod.usage_add("google", pages=1)           # must not raise
        assert mod.usage_month("google") == {"jobs": 0, "pages": 0}
    finally:
        if old is None:
            os.environ.pop("NC_OCR_STATE_DIR", None)
        else:
            os.environ["NC_OCR_STATE_DIR"] = old
        for name in ("nc_ocr_flow.jobstore", "nc_ocr_flow.webhook_server"):
            sys.modules.pop(name, None)


def test_claim_next_is_atomic_under_concurrency(tmp_path: Path) -> None:
    """Several workers claiming at once must never get the same job."""
    mod = _isolated_jobstore(tmp_path, "claim")
    for i in range(1, 31):
        mod.record_enqueue(_make_job(i))

    claimed: list = []
    lock = threading.Lock()

    def _worker():
        for _ in range(300):
            job = mod.claim_next()
            if job is None:
                with lock:
                    if len(claimed) >= 30:
                        return
                time.sleep(0.02)
                continue
            with lock:
                claimed.append(job["id"])

    threads = [threading.Thread(target=_worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(claimed) == list(range(1, 31)), sorted(claimed)
    assert len(claimed) == len(set(claimed)), "a job was claimed twice"


def test_requeue_stale_returns_abandoned_jobs(tmp_path: Path) -> None:
    """A restart must put jobs stuck in 'running' back in the queue."""
    mod = _isolated_jobstore(tmp_path, "stale")
    mod.record_enqueue(_make_job(1))
    mod.record_enqueue(_make_job(2))
    first = mod.claim_next()
    assert first is not None and first["status"] == "running"
    assert mod.stats().get("running") == 1
    assert mod.requeue_stale() == 1
    assert mod.stats().get("queued") == 2
    assert mod.stats().get("running", 0) == 0


def test_claim_next_empty_queue_returns_none(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, "empty")
    assert mod.claim_next() is None


# ---------------------------------------------------------------------------
# Pure-stdlib mini test framework — works without pytest.
# ---------------------------------------------------------------------------

_TESTS_RUN: list = []


def _run(test_fn) -> None:
    name = test_fn.__name__
    try:
        test_fn()
        _TESTS_RUN.append((name, True, None))
    except Exception:
        _TESTS_RUN.append((name, False, traceback.format_exc()))


# ---------------------------------------------------------------------------
# Actual tests
# ---------------------------------------------------------------------------


def test_init_creates_db(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, name="test_init_creates_db")
    assert mod.db_path().exists(), f"DB not created at {mod.db_path()}"
    con = sqlite3.connect(str(mod.db_path()))
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        ).fetchall()
    finally:
        con.close()
    assert rows == [("jobs",)], f"jobs table missing: {rows}"
    mod.init()
    mod.init()  # idempotent


def test_record_enqueue_and_query_roundtrip(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, name="test_record_enqueue_and_query_roundtrip")
    for i in range(1, 6):
        mod.record_enqueue(_make_job(i, status="queued"))
    rows = mod.query(limit=10)
    assert len(rows) == 5, f"expected 5 rows, got {len(rows)}"
    assert rows[0]["id"] == 5
    assert rows[-1]["id"] == 1
    for r in rows:
        assert isinstance(r["id"], int)
        assert r["status"] == "queued"
        assert r["path"].endswith(".pdf")


def test_record_update_upserts(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, name="test_record_update_upserts")
    j = _make_job(42, status="queued")
    mod.record_enqueue(j)
    j["status"] = "running"
    j["started"] = 1_700_000_100.0
    mod.record_update(j)
    j["status"] = "done"
    j["finished"] = 1_700_000_200.0
    j["result"] = {"engine": "google", "pages": 3}
    mod.record_update(j)
    rows = mod.query(status="done")
    assert len(rows) == 1
    got = rows[0]
    assert got["id"] == 42
    assert got["status"] == "done"
    assert got["started"] == 1_700_000_100.0
    assert got["finished"] == 1_700_000_200.0
    assert got["result"] == {"engine": "google", "pages": 3}, (
        f"result not round-tripped through JSON: {got['result']!r}"
    )
    assert len(mod.query(limit=100)) == 1


def test_query_by_status(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, name="test_query_by_status")
    statuses = ["queued", "running", "done", "error", "skipped"]
    for i, s in enumerate(statuses * 4, start=1):
        mod.record_update(_make_job(i, status=s))
    for s in statuses:
        rows = mod.query(status=s, limit=100)
        assert len(rows) == 4, f"status={s}: expected 4, got {len(rows)}"
    assert mod.query(status="nonexistent", limit=100) == []


def test_query_by_since(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, name="test_query_by_since")
    for i in range(10):
        mod.record_enqueue(_make_job(i, created=1000.0 + i))
    rows = mod.query(since=1005.0, limit=100)
    assert len(rows) == 5, f"expected 5, got {len(rows)}"
    assert [r["id"] for r in rows] == [9, 8, 7, 6, 5]
    assert len(mod.query(since=999.0, limit=100)) == 10
    assert mod.query(since=2000.0, limit=100) == []
    # ISO date string — epoch 1005 is 1970-01-01T00:16:45Z
    rows = mod.query(since="1970-01-01T00:16:45", limit=100)
    assert len(rows) == 5


def test_query_by_path_contains(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, name="test_query_by_path_contains")
    paths = [
        "/admin/files/Work/contract.pdf",
        "/admin/files/Home/invoice-2024.pdf",
        "/admin/files/Work/report.pdf",
        "/admin/files/Home/invoice-2025.pdf",
        "/admin/files/Photos/IMG_0001.jpg",
    ]
    for i, p in enumerate(paths, start=1):
        mod.record_enqueue(_make_job(i, path=p, nc_path=p))
    assert {r["id"] for r in mod.query(path_contains="invoice", limit=100)} == {2, 4}
    assert {r["id"] for r in mod.query(path_contains="Work", limit=100)} == {1, 3}
    assert mod.query(path_contains="nope", limit=100) == []


def test_stats_correctness(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, name="test_stats_correctness")
    plan = {1: "queued", 2: "queued", 3: "running",
            4: "done", 5: "done", 6: "done",
            7: "error", 8: "skipped"}
    for i, s in plan.items():
        mod.record_update(_make_job(i, status=s))
    s = mod.stats()
    assert s["total"] == 8, f"total: {s}"
    assert s["queued"] == 2
    assert s["running"] == 1
    assert s["done"] == 3
    assert s["error"] == 1
    assert s["skipped"] == 1


def test_get_by_id(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, name="test_get_by_id")
    mod.record_enqueue(_make_job(7))
    got = mod.get(7)
    assert got is not None and got["id"] == 7
    assert mod.get(999) is None


def test_concurrent_writes(tmp_path: Path) -> None:
    mod = _isolated_jobstore(tmp_path, name="test_concurrent_writes")

    def writer(start: int, n: int) -> None:
        for i in range(start, start + n):
            mod.record_update(_make_job(i, status="queued"))
            mod.record_update(_make_job(i, status="done"))

    threads = [threading.Thread(target=writer, args=(t * 100, 50))
               for t in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    rows = mod.query(limit=1000)
    assert len(rows) == 200, f"expected 200 rows, got {len(rows)}"
    for r in rows:
        assert "id" in r and "status" in r


def test_record_enqueue_no_silent_collision_after_restart(tmp_path: Path) -> None:
    """Regression: an in-memory job-id counter that restarts at 1 used to
    collide with persisted ids after a service restart; the old code
    silently swallowed the conflict via ``INSERT OR IGNORE``, leaving the
    queue unobservable. The new contract must:

      * survive a simulated restart (cold reload of the module) without
        data loss for new enqueues;
      * raise on an explicit-id collision (loud, never no-op);
      * auto-assign a fresh, collision-free id when none is provided.

    See PR description for the diagnostic on poweredge.
    """
    db_dir = tmp_path / "restart"
    db_dir.mkdir(parents=True, exist_ok=True)
    # The Env stays open for the whole test: _isolated_jobstore would
    # tear it down on return, so a "restart" import that ran OUTSIDE the
    # env block would silently fall back to /var/lib/nc-ocr and lose
    # everything to a permission-denied no-op.
    with _Env(NC_OCR_STATE_DIR=str(db_dir)):
        # --- pass 1: 50 rows persisted by "process A". ---
        for name in list(sys.modules):
            if name == "nc_ocr_flow.jobstore":
                del sys.modules[name]
        mod = importlib.import_module("nc_ocr_flow.jobstore")
        mod._reset_for_tests()
        mod.init()
        for i in range(1, 51):
            mod.record_enqueue(_make_job(i, status="queued"))
        max_after_first = max(int(r["id"]) for r in mod.query(limit=1000))
        assert max_after_first == 50, (
            max_after_first,
            [r["id"] for r in mod.query(limit=1000)][:5],
        )

        # --- simulate a service restart: drop the module from
        # sys.modules so a fresh import (and a fresh interpreter-level
        # state) executes. The .db file and the rows persist on disk.
        # NB: do NOT call ``_reset_for_tests`` here — it unlinks the
        # DB file (``p.unlink()``), which would erase the simulated
        # "process A" rows we just persisted. Production has no such
        # reset step.
        for name in list(sys.modules):
            if name in ("nc_ocr_flow.jobstore",
                        "nc_ocr_flow.webhook_server"):
                del sys.modules[name]
        mod2 = importlib.import_module("nc_ocr_flow.jobstore")
        # Mark the (refreshed) module uninitialised so init() re-runs
        # CREATE TABLE IF NOT EXISTS; the 50 rows above are still on
        # disk and ``init`` will see them.
        mod2._INITIALISED = False
        mod2.init()
        # Sanity: the reloaded module opens the SAME DB file.
        assert str(mod2.db_path()).startswith(str(db_dir))

        # --- pass 2: "process B" enqueues without pre-setting an id
        # (the production contract — the in-memory counter is gone).
        # SQLite MUST assign ids > 50 (the previous process's
        # high-water mark) and every row MUST be claimable. The old
        # INSERT OR IGNORE would have left the queue silently empty
        # when the new ids collided with 1..50.
        enqueued: list[int] = []
        for i in range(1, 21):
            # The factory types id as int, but the new contract accepts
            # None; build the dict by hand so it is unambiguously
            # absent.
            job = {
                "id": None,
                "path": f"/admin/files/Documents/restart-{i:04d}.pdf",
                "nc_path": f"/admin/files/Documents/restart-{i:04d}.pdf",
                "node_id": 2000 + i,
                "engine": "google",
                "force": False,
                "status": "queued",
                "created": 1_700_000_000.0 + i,
                "started": None,
                "finished": None,
                "error": None,
                "reason": None,
                "result": None,
            }
            assigned = mod2.record_enqueue(job)
            assert assigned is not None, (
                "record_enqueue returned None — DB error during a "
                "happy-path restart. The fix should not regress this."
            )
            assert assigned > 50, (
                f"newly assigned id {assigned} collided with a row from "
                f"process A (max={max_after_first}). The restart-safety "
                f"fix is not in place."
            )
            enqueued.append(assigned)
            assert assigned == job["id"], (
                f"record_enqueue should write the assigned id back into "
                f"the job dict (got job['id']={job['id']}, returned "
                f"{assigned})"
            )

        # All 70 rows (50 old + 20 new) must be reachable; the old
        # INSERT-OR-IGNORE bug would have left the new 20 rows missing.
        rows = mod2.query(limit=100)
        assert len(rows) == 70, (
            f"restart-survival broken: expected 70 rows (50 old + 20 "
            f"new), got {len(rows)}. The old INSERT-OR-IGNORE bug "
            f"would have left the new 20 rows missing."
        )

        # And the 20 newly-enqueued rows must be claimable by the
        # worker.
        claimed_ids = set()
        while True:
            job = mod2.claim_next()
            if job is None:
                break
            claimed_ids.add(int(job["id"]))
        assert set(enqueued).issubset(claimed_ids), (
            f"only some new rows were claimable: not-claimed="
            f"{set(enqueued) - claimed_ids}; total claimed="
            f"{len(claimed_ids)}"
        )

        # --- pass 3: explicit-id collision must RAISE (loud, not
        # silent). Pick any id we already wrote and try to enqueue
        # with the same id. We avoid pytest.raises because the file is
        # stdlib-only; use unittest's assertRaises directly via the
        # module (available without import on Python 3.5+).
        reused = enqueued[0]
        raised = False
        try:
            mod2.record_enqueue(
                _make_job(reused, status="queued",
                          path="/admin/files/Documents/collide.pdf")
            )
        except RuntimeError as exc:
            raised = True
            assert "id collision" in str(exc), (
                f"unexpected RuntimeError message: {exc}"
            )
        else:
            raise AssertionError(
                "record_enqueue silently swallowed an explicit-id "
                "collision — the old INSERT-OR-IGNORE bug is back!"
            )
        assert raised, "RuntimeError was not raised"


def test_broken_db_path_silent(tmp_path: Path) -> None:
    """A non-creatable DB path must not break callers."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    cache = tmp_path / "cache"
    with _Env(NC_OCR_STATE_DIR=str(blocker), XDG_CACHE_HOME=str(cache)):
        for mod_name in list(sys.modules):
            if mod_name == "nc_ocr_flow.jobstore":
                del sys.modules[mod_name]
        mod = importlib.import_module("nc_ocr_flow.jobstore")
        mod._reset_for_tests()
        try:
            mod.init()
            mod.record_enqueue(_make_job(1))
            rows = mod.query()
            assert isinstance(rows, list), f"query did not return list: {rows!r}"
        except Exception as exc:
            raise AssertionError(f"jobstore raised on bad env: {exc}") from exc
        # Now break the DB harder: the blocker is a regular file, so
        # ``mkdir(parents=True)`` inside _resolve_db_path will raise
        # FileExistsError. The module must stay silent.
        with _Env(NC_OCR_STATE_DIR=str(blocker)):
            mod._reset_for_tests()
            try:
                mod.init()
                mod.record_enqueue(_make_job(99, status="done"))
                mod.record_update(_make_job(99, status="error"))
                rows = mod.query(limit=10)
                stats = mod.stats()
                assert isinstance(rows, list)
                assert isinstance(stats, dict)
            except Exception as exc:
                raise AssertionError(
                    f"jobstore raised when DB unreachable: {exc}"
                ) from exc


def test_db_path_resolution_env_precedence(tmp_path: Path) -> None:
    """NC_OCR_STATE_DIR wins over STATE_DIRECTORY."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    with _Env(NC_OCR_STATE_DIR=str(a), STATE_DIRECTORY=str(b)):
        for mod_name in list(sys.modules):
            if mod_name == "nc_ocr_flow.jobstore":
                del sys.modules[mod_name]
        mod = importlib.import_module("nc_ocr_flow.jobstore")
        mod._reset_for_tests()
        p = mod.db_path()
        assert p.parent == a, f"NC_OCR_STATE_DIR should win, got {p}"
    os.environ.pop("NC_OCR_STATE_DIR", None)
    with _Env(STATE_DIRECTORY=str(b)):
        for mod_name in list(sys.modules):
            if mod_name == "nc_ocr_flow.jobstore":
                del sys.modules[mod_name]
        mod = importlib.import_module("nc_ocr_flow.jobstore")
        mod._reset_for_tests()
        p = mod.db_path()
        assert p.parent == b, f"STATE_DIRECTORY: got {p}, expected under {b}"


def test_no_in_memory_job_mirror(tmp_path: Path) -> None:
    """Job history lives in SQLite; the in-memory mirror is gone.

    Skipped if ``requests`` is not available (the local erepx env
    lacks it; poweredge's venv-v4 has it).
    """
    try:
        import requests  # noqa: F401
    except ImportError:
        print(f"[SKIP] test_in_memory_jobs_cap_500: 'requests' missing")
        return
    sd = tmp_path / "state"
    sd.mkdir()
    with _Env(NC_OCR_STATE_DIR=str(sd)):
        for mod_name in list(sys.modules):
            if mod_name in ("nc_ocr_flow.webhook_server",
                            "nc_ocr_flow.jobstore"):
                del sys.modules[mod_name]
        ws = importlib.import_module("nc_ocr_flow.webhook_server")
        # The in-memory job mirror is gone: history lives in SQLite, so
        # a million-file backlog costs no RAM. _record_job is now a shim.
        assert not hasattr(ws, "_jobs"), "in-memory job mirror came back"
        assert not hasattr(ws, "_MAX_JOBS_HISTORY"), "obsolete cap came back"
        assert ws._record_job({"id": 1, "status": "done"}) is None
        # The in-memory job-id counter (``itertools.count(1)``) is also
        # gone: ids are now assigned by SQLite (``record_enqueue``
        # reads back ``lastrowid``) so they survive a service restart
        # without colliding with persisted rows. See the regression
        # test ``test_record_enqueue_no_silent_collision_after_restart``.
        assert not hasattr(ws, "_job_seq"), (
            "in-memory job-id counter came back — restart-safety lost"
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="jobstore-tests-") as td:
        tmp = Path(td)
        for name, obj in sorted(globals().items()):
            if name.startswith("test_") and callable(obj):
                try:
                    _run(lambda o=obj: o(tmp))
                except TypeError:
                    _run(obj)
    passed = sum(1 for _, ok, _ in _TESTS_RUN if ok)
    failed = sum(1 for _, ok, _ in _TESTS_RUN if not ok)
    print(f"\n{'='*60}\njobstore tests: {passed} passed, {failed} failed "
          f"({passed + failed} total)")
    print("=" * 60)
    for name, ok, tb in _TESTS_RUN:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        if tb:
            print(tb)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())