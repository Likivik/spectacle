"""A transient failure must leave a real retry behind (C6 ordering).

Regression for a bug found live on poweredge. ``_is_transient_failure`` marks
HTTP 408/429/5xx and transport errors retry-eligible, but ``_run_job`` scheduled
the retry while the failing row was still ``running``. ``uq_jobs_inflight`` is
UNIQUE on ``jobs(path) WHERE status IN ('queued','running')``, so the retry
insert was rejected, ``enqueue_retry`` returned ``None`` and the failure was
recorded as permanent. The journal showed, in this order:

    WebDAV GET ... failed after 3 attempts: 429 Client Error: Too Many Requests
    jobstore: insert skipped, path already in flight (UNIQUE constraint failed: jobs.path)
    worker: job 124 failed (429): ...

Net effect: a transient rate limit silently lost the file until a new webhook.
"""
from __future__ import annotations

import importlib
import os
import sys
import time
from pathlib import Path

import requests

_HERE = Path(__file__).resolve().parent
_SRC = (_HERE.parent / "src").resolve()
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _isolated_worker(tmp: Path, name: str):
    """``jobstore`` + ``webhook_server`` bound to one throwaway DB.

    Both modules must be re-imported *while* ``NC_OCR_STATE_DIR`` points at the
    temp dir: the store resolves its path at import/init time, and
    ``webhook_server`` calls ``jobstore.init()`` at import.
    """
    db_dir = tmp / name
    db_dir.mkdir(parents=True, exist_ok=True)
    for mod_name in ("nc_ocr_flow.jobstore", "nc_ocr_flow.webhook_server"):
        sys.modules.pop(mod_name, None)
    prev = os.environ.get("NC_OCR_STATE_DIR")
    os.environ["NC_OCR_STATE_DIR"] = str(db_dir)
    try:
        store = importlib.import_module("nc_ocr_flow.jobstore")
        store._reset_for_tests()
        store.init()
        ws = importlib.import_module("nc_ocr_flow.webhook_server")
    finally:
        if prev is None:
            os.environ.pop("NC_OCR_STATE_DIR", None)
        else:
            os.environ["NC_OCR_STATE_DIR"] = prev
    return store, ws


def _job(i: int, path: str = "/likivik/files/doc.pdf") -> dict:
    return {
        "id": i, "path": path, "nc_path": path, "node_id": 1000 + i,
        "engine": "google", "force": False, "status": "queued",
        "created": time.time(), "started": None, "finished": None,
        "error": None, "reason": None, "result": None,
        "attempts": 0, "next_run_at": 0.0,
    }


def _http_error(status: int) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError(f"{status} Client Error", response=resp)


def _run_failing_job(store, ws, monkeypatch, job_id: int, exc: BaseException):
    store.record_enqueue(_job(job_id))
    job = store.claim_next()
    assert job is not None and job["status"] == "running"

    def _boom(*_args, **_kwargs):
        raise exc

    monkeypatch.setattr(ws, "_process_file", _boom)
    ws._run_job(job)
    return job


def test_429_schedules_a_retry_row(tmp_path, monkeypatch):
    """A rate-limited fetch must be retried, not buried as a permanent error."""
    store, ws = _isolated_worker(tmp_path, "retry429")
    _run_failing_job(store, ws, monkeypatch, 1, _http_error(429))

    failed = store.get(1)
    assert failed is not None and failed["status"] == "error"
    assert failed["attempts"] == 0, "the failed row must not carry attempts (B2)"

    queued = store.query(limit=50, status="queued")
    assert len(queued) == 1, (
        "a transient 429 must leave a queued retry behind; rows were "
        f"{[(r['id'], r['status'], r.get('attempts')) for r in store.query(limit=50)]}"
    )
    assert queued[0]["attempts"] == 1
    assert queued[0]["path"] == "/likivik/files/doc.pdf"
    assert queued[0]["next_run_at"] > time.time()


def test_transport_error_schedules_a_retry_row(tmp_path, monkeypatch):
    store, ws = _isolated_worker(tmp_path, "retryconn")
    _run_failing_job(store, ws, monkeypatch, 2,
                     requests.ConnectionError("connection reset by peer"))

    assert store.get(2)["status"] == "error"
    queued = store.query(limit=50, status="queued")
    assert len(queued) == 1, "transport failures are transient and must be retried"
    assert queued[0]["attempts"] == 1


def test_permanent_4xx_is_not_retried(tmp_path, monkeypatch):
    """The fix must not turn permanent failures into retry loops."""
    store, ws = _isolated_worker(tmp_path, "retry403")
    _run_failing_job(store, ws, monkeypatch, 3, _http_error(403))

    assert store.get(3)["status"] == "error"
    assert store.query(limit=50, status="queued") == []


def test_retries_stop_after_the_attempt_cap(tmp_path, monkeypatch):
    """The cap still bounds the chain, now that retries actually happen."""
    store, ws = _isolated_worker(tmp_path, "retrycap")
    cap = int(getattr(ws, "_MAX_RETRY_ATTEMPTS", 3))
    _run_failing_job(store, ws, monkeypatch, 4, _http_error(500))

    attempts_seen: list[int] = []
    for _ in range(cap + 2):
        queued = store.query(limit=50, status="queued")
        if not queued:
            break
        row = queued[0]
        attempts_seen.append(int(row["attempts"]))
        store.record_update({**row, "status": "running"})
        ws._run_job(store.get(row["id"]))

    assert store.query(limit=50, status="queued") == [], "the chain must end"
    assert len(attempts_seen) <= cap, f"exceeded the cap: {attempts_seen}"
    assert attempts_seen == list(range(1, len(attempts_seen) + 1))
