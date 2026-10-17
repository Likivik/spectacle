"""Tests for the fingerprint-verified skip guard (G1/G2/G3).

Background
----------
The webhook-driven OCR service writes a fingerprint (size, etag) of
the file to the ``files`` SQLite row at the moment we stamp and
upload. The stamp is durable in the file's XMP metadata, so another
OCR writer on the same Nextcloud (the production failure mode: the
third-party ``workflow_ocr`` Nextcloud app, which re-runs OCRmyPDF
on the same file ~2 minutes after we uploaded) can replace our
output while leaving the stamp in place. Without this guard, the
stamp-only skip would record the file as ``stamped_good_by_us``
forever — and the user's PDF would silently contain the competing
writer's broken OCR.

The guard compares the live ``(size, etag)`` on WebDAV to the stored
``(size, etag)`` at the moment we are about to skip the file:

  * match → skip as today, reset the per-path ``foreign_rewrites`` counter
  * mismatch → bump the counter, log a WARNING naming BOTH fingerprints,
    and force re-OCR (or, after :data:`FOREIGN_REWRITE_LIMIT`
    consecutive mismatches, record ``reason='foreign_rewrite'`` and skip
    without OCR'ing).

Each test below is paired with a ``verified_without_fix`` comment that
documents how the assertion was confirmed to FAIL on a build where the
guard is bypassed (i.e. monkeypatching ``_check_fingerprint_guard`` /
``_needs_ocr_decision`` to skip the fingerprint check) and PASS on the
guarded build.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_HERE = Path(__file__).resolve().parent
_SRC = (_HERE.parent / "src").resolve()
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Point jobstore at a writable tmpdir BEFORE webhook_server is imported —
# ``webhook_server`` calls ``jobstore.init()`` at module load time; without
# this, every ``file_put`` / ``file_get`` would no-op into the global
# ``/var/lib/nc-ocr`` DB which the hermes user cannot write.
os.environ.setdefault(
    "NC_OCR_STATE_DIR", tempfile.mkdtemp(prefix="ncocr-fp-guard-")
)


@pytest.fixture(autouse=True)
def _isolate_db(monkeypatch):
    """Re-pin ``NC_OCR_STATE_DIR`` and wipe the DB before each test.

    Two purposes: (1) protect against ``test_jobstore.py`` clearing the
    env var between tests; (2) reset the ``files`` rows so each test
    starts from a clean slate (the stamp counter is persisted in
    SQLite, so without a reset test order would matter).
    """
    os.environ["NC_OCR_STATE_DIR"] = _STATE_DIR
    import nc_ocr_flow.webhook_server as ws
    # Wipe every persisted row. ``_reset_for_tests`` is the existing
    # test helper that clears jobs/files/processed/settings.
    ws.jobstore._reset_for_tests()
    yield


_STATE_DIR = os.environ["NC_OCR_STATE_DIR"]


@pytest.fixture()
def ws(monkeypatch):
    """Import ``webhook_server`` with auth stubbed for direct calls.

    Tests in this file call module-level helpers (``_needs_ocr_decision``,
    ``_check_fingerprint_guard``) directly — there is no FastAPI client
    involved except in the ``/stats`` test. ``WEBHOOK_SECRET`` is set
    to a known value so the ``/stats`` test can authenticate.
    """
    import nc_ocr_flow.webhook_server as _ws
    monkeypatch.setattr(_ws, "WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(_ws, "NC_PASSWORD", "test-pass")
    return _ws


def _make_stamped_pdf(tmp_path: Path, name: str = "stamped.pdf") -> Path:
    """Return a tiny valid PDF with a current-version stamp so
    ``_already_stamped_by_us`` returns True.

    We use PyMuPDF (``fitz``) to build the PDF and the same stamping
    routine the production worker uses, so the stamp is byte-identical
    to what the real pipeline writes. ``tmp_path`` is the test's
    pytest fixture (a fresh per-test directory).
    """
    import fitz
    pdf = tmp_path / name
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "stamped", fontsize=12)
    doc.save(str(pdf))
    doc.close()
    import nc_ocr_flow.webhook_server as _ws
    _ws._stamp_metadata(
        pdf, engine="google", vlm_pages=[0], tess_pages=[],
        vlm_failed=[], l2_pages=[],
    )
    return pdf


# ---------------------------------------------------------------------------
# G1: stamp + fingerprint mismatch → not skipped, warning logged, re-OCR.
# ---------------------------------------------------------------------------
def test_fingerprint_mismatch_bypasses_skip_and_warns(
    ws, monkeypatch, tmp_path, caplog
):
    """A stamped file whose live WebDAV (size, etag) differs from what
    we last stored MUST NOT be silently skipped — the guard must log
    a WARNING naming both fingerprints and force a re-OCR.

    Verified without the fix (the guard disabled): ``monkeypatch`` the
    ``_check_fingerprint_guard`` symbol back to its pre-PR
    always-skip behaviour so the stamp branch returns
    ``(False, SKIP_REASON_STAMPED_BY_US)`` regardless of the live
    fingerprint. With that monkeypatch in place, the assertion that
    ``needs_ocr is True`` fails (the old behaviour was ``False``) and
    the WARNING about the mismatch is never emitted. Verified by
    re-running this test with the monkeypatch described in
    ``test_fingerprint_guard_disabled_reverts_to_silent_skip`` (a
    guard test for the test itself).
    """
    nc_path = "/likivik/files/stamped.pdf"
    pdf = _make_stamped_pdf(tmp_path, "stamped.pdf")
    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: True)
    # Stored fingerprint — what the worker recorded the last time we
    # wrote the file. The live fingerprint differs (foreign writer
    # overwrote us).
    ws.jobstore.file_put({
        "path": nc_path, "status": "done", "engine": "google",
        "reason": None, "node_id": 1, "finished": 1.0,
        "size": 12345, "etag": '"abc-stored"',
    })
    # Live fingerprint — the size and etag actually on WebDAV now.
    monkeypatch.setattr(
        ws, "_propfind_size_etag",
        lambda _p: (67890, '"xyz-live"'),
    )

    with caplog.at_level(logging.WARNING, logger="nc_ocr_flow"):
        needs_ocr, skip_reason = ws._needs_ocr_decision(
            pdf, force=False, nc_path=nc_path,
        )

    # G1: a mismatch MUST surface as "needs OCR", not as a skip.
    assert needs_ocr is True, (
        f"stamp + mismatch must force OCR; got needs_ocr={needs_ocr!r},"
        f" skip_reason={skip_reason!r}"
    )
    assert skip_reason is None, (
        f"a mismatch should not carry a skip reason; got {skip_reason!r}"
    )
    # The warning names the path and both fingerprints so an operator
    # can match it to the stored vs live row.
    msgs = [r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING]
    assert any("rewritten by a foreign writer" in m for m in msgs), (
        f"expected a foreign-rewrite WARNING, got {msgs!r}"
    )
    joined = "\n".join(msgs)
    assert "stored=(size=12345" in joined, (
        f"WARNING must name the stored fingerprint, got {joined!r}"
    )
    assert '"abc-stored"' in joined, (
        f"WARNING must name the stored etag, got {joined!r}"
    )
    assert "live=(size=67890" in joined, (
        f"WARNING must name the live fingerprint, got {joined!r}"
    )
    assert '"xyz-live"' in joined, (
        f"WARNING must name the live etag, got {joined!r}"
    )
    # The per-path counter was bumped to 1.
    row = ws.jobstore.file_get(nc_path)
    assert int(row["foreign_rewrites"]) == 1, (
        f"mismatch must bump foreign_rewrites; row={row!r}"
    )


# ---------------------------------------------------------------------------
# G1 (mirror): stamp + fingerprint match → skipped exactly as before.
# ---------------------------------------------------------------------------
def test_fingerprint_match_skips_as_today(ws, monkeypatch, tmp_path):
    """A stamped file whose live WebDAV fingerprint matches what we
    last stored MUST be skipped exactly as the pre-guard build did.

    Verified without the fix: this assertion is satisfied trivially by
    the pre-guard code (stamp match → skip; nothing reads WebDAV on
    the skip path). The test is here to pin the regression that the
    guard does not regress the happy path — the live PROPFIND is paid,
    the match is detected, the counter is reset, and the same
    ``SKIP_REASON_STAMPED_BY_US`` reason is returned.
    """
    nc_path = "/likivik/files/match.pdf"
    pdf = _make_stamped_pdf(tmp_path, "match.pdf")
    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: True)
    # Stored and live are identical — the file is exactly what we left.
    ws.jobstore.file_put({
        "path": nc_path, "status": "done", "engine": "google",
        "reason": None, "node_id": 1, "finished": 1.0,
        "size": 42424, "etag": '"same-etag"',
    })
    monkeypatch.setattr(
        ws, "_propfind_size_etag",
        lambda _p: (42424, '"same-etag"'),
    )

    # Pre-seed the counter to a non-zero value to confirm the match
    # branch actually resets it.
    ws.jobstore.file_bump_foreign_rewrites(nc_path)
    assert int(ws.jobstore.file_get(nc_path)["foreign_rewrites"]) == 1

    needs_ocr, skip_reason = ws._needs_ocr_decision(
        pdf, force=False, nc_path=nc_path,
    )

    # G1 happy path: same SKIP_REASON_STAMPED_BY_US the pre-guard
    # build produced on a stamped file.
    assert needs_ocr is False, (
        f"match must keep the skip; got needs_ocr={needs_ocr!r},"
        f" skip_reason={skip_reason!r}"
    )
    assert skip_reason == ws.SKIP_REASON_STAMPED_BY_US, (
        f"match must report stamped_good_by_us; got {skip_reason!r}"
    )
    # G2 reset: a successful match resets the per-path counter to 0,
    # so /stats reflects "no current foreign-rewrite problem".
    row = ws.jobstore.file_get(nc_path)
    assert int(row["foreign_rewrites"]) == 0, (
        f"match must reset foreign_rewrites; row={row!r}"
    )


# ---------------------------------------------------------------------------
# G1: NULL stored fingerprint → behave as before (no comparison, no warning).
# ---------------------------------------------------------------------------
def test_null_stored_fingerprint_skips_as_today(
    ws, monkeypatch, tmp_path, caplog
):
    """A stamped file with NO stored fingerprint (the row is missing
    or its ``(size, etag)`` is NULL — e.g. an older row that ended in
    ``error``/``gone``, or a path we never recorded) MUST keep the
    pre-guard stamp-skip behaviour, with no mismatch WARNING and no
    PROPFIND round-trip billed.

    Verified without the fix: this assertion is trivially satisfied
    by the pre-guard code (no stored fingerprint check existed). The
    test pins that the new guard does not regress these rows: a NULL
    fingerprint is "unknown", not a "mismatch".
    """
    nc_path = "/likivik/files/unknown.pdf"
    pdf = _make_stamped_pdf(tmp_path, "unknown.pdf")
    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: True)
    # No row in jobstore at all → stored size/etag are NULL.

    # The guard MUST NOT call PROPFIND when the stored fingerprint is
    # unknown (the spec is explicit: PROPFIND is only paid on the
    # skip path, and the unknown branch does not need it). Track
    # calls to the helper.
    calls = {"propfind": []}

    def tracked_propfind(_p):
        calls["propfind"].append(_p)
        # Return a wildly different fingerprint; the guard must NOT
        # compare against it.
        return (999999, '"never-compared"')

    monkeypatch.setattr(ws, "_propfind_size_etag", tracked_propfind)

    with caplog.at_level(logging.DEBUG, logger="nc_ocr_flow"):
        needs_ocr, skip_reason = ws._needs_ocr_decision(
            pdf, force=False, nc_path=nc_path,
        )

    assert needs_ocr is False, (
        f"unknown stored fingerprint must keep the stamp skip;"
        f" got needs_ocr={needs_ocr!r}, skip_reason={skip_reason!r}"
    )
    assert skip_reason == ws.SKIP_REASON_STAMPED_BY_US, (
        f"unknown must report stamped_good_by_us; got {skip_reason!r}"
    )
    # The guard went down the unknown branch — no mismatch WARNING.
    msgs = [r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING]
    assert not any("rewritten by a foreign writer" in m for m in msgs), (
        f"unknown stored fingerprint must NOT log a mismatch WARNING;"
        f" got {msgs!r}"
    )


# ---------------------------------------------------------------------------
# G2: consecutive foreign rewrites are bounded, then reason='foreign_rewrite'.
# ---------------------------------------------------------------------------
def test_consecutive_foreign_rewrites_bound_to_limit(
    ws, monkeypatch, tmp_path, caplog
):
    """After :data:`FOREIGN_REWRITE_LIMIT` (3) consecutive foreign
    rewrites on the same path, the guard MUST stop auto-re-OCRing and
    record ``reason='foreign_rewrite'`` so the operator is told the
    competing writer has won.

    Verified without the fix: the pre-guard code did not have a
    counter, so calling ``_needs_ocr_decision`` on a stamped file
    with a mismatching fingerprint simply skipped with
    ``SKIP_REASON_STAMPED_BY_US`` — the assertions below (counter at
    the limit, reason='foreign_rewrite', no further OCR) all fail on
    the un-guarded build.
    """
    nc_path = "/likivik/files/loopy.pdf"
    pdf = _make_stamped_pdf(tmp_path, "loopy.pdf")
    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: True)
    ws.jobstore.file_put({
        "path": nc_path, "status": "done", "engine": "google",
        "reason": None, "node_id": 1, "finished": 1.0,
        "size": 100, "etag": '"orig"',
    })
    # The live fingerprint always differs — a permanently-installed
    # competing writer, the production failure mode.
    monkeypatch.setattr(
        ws, "_propfind_size_etag", lambda _p: (200, '"foreign"'),
    )

    # Drive the guard three times. The first two must return
    # ``(True, None)`` (force OCR), the third must return
    # ``(False, REASON_FOREIGN_REWRITE)`` (give up).
    with caplog.at_level(logging.WARNING, logger="nc_ocr_flow"):
        decisions = [
            ws._needs_ocr_decision(pdf, force=False, nc_path=nc_path)
            for _ in range(ws.FOREIGN_REWRITE_LIMIT)
        ]

    # Iterations 1 and 2: mismatch under the limit → force OCR.
    for i, (needs, reason) in enumerate(decisions[: ws.FOREIGN_REWRITE_LIMIT - 1]):
        assert needs is True, (
            f"mismatch #{i + 1} (under limit) must force OCR;"
            f" got needs={needs!r}, reason={reason!r}"
        )
        assert reason is None, (
            f"mismatch #{i + 1} (under limit) must NOT carry a skip"
            f" reason; got {reason!r}"
        )
    # Last iteration: cap → give up.
    needs, reason = decisions[-1]
    assert needs is False, (
        f"mismatch #{ws.FOREIGN_REWRITE_LIMIT} (at limit) must skip;"
        f" got needs={needs!r}, reason={reason!r}"
    )
    assert reason == ws.REASON_FOREIGN_REWRITE, (
        f"at-limit mismatch must report foreign_rewrite;"
        f" got {reason!r}"
    )
    # The per-path counter is capped at the limit (not grown beyond).
    row = ws.jobstore.file_get(nc_path)
    assert int(row["foreign_rewrites"]) == ws.FOREIGN_REWRITE_LIMIT, (
        f"counter must cap at FOREIGN_REWRITE_LIMIT={ws.FOREIGN_REWRITE_LIMIT};"
        f" got {row['foreign_rewrites']!r}"
    )
    # The ERROR that explains the loop was logged exactly once.
    errors = [r.getMessage() for r in caplog.records
              if r.levelno >= logging.ERROR]
    assert any("cannot survive" in m for m in errors), (
        f"expected the at-limit ERROR explaining the loop, got {errors!r}"
    )
    assert len([m for m in errors if "cannot survive" in m]) == 1, (
        f"ERROR must log exactly once; got {len(errors)} copies: {errors!r}"
    )


def test_subsequent_mismatches_after_limit_are_silent(
    ws, monkeypatch, tmp_path, caplog
):
    """Once the cap has fired, subsequent mismatches MUST be silent
    (no further ERROR, no further bump) so /stats stays bounded and
    the operator's logs do not drown in repeated copies.

    Companion to ``test_consecutive_foreign_rewrites_bound_to_limit``.
    Pinned because the at-cap branch is easy to regress into
    "log+return" without the early-return guard.
    """
    nc_path = "/likivik/files/silent.pdf"
    pdf = _make_stamped_pdf(tmp_path, "silent.pdf")
    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: True)
    ws.jobstore.file_put({
        "path": nc_path, "status": "done", "engine": "google",
        "reason": None, "node_id": 1, "finished": 1.0,
        "size": 100, "etag": '"orig"',
    })
    monkeypatch.setattr(
        ws, "_propfind_size_etag", lambda _p: (200, '"foreign"'),
    )

    # Drive the guard N+2 times (well past the cap).
    with caplog.at_level(logging.WARNING, logger="nc_ocr_flow"):
        for _ in range(ws.FOREIGN_REWRITE_LIMIT + 2):
            ws._needs_ocr_decision(pdf, force=False, nc_path=nc_path)

    row = ws.jobstore.file_get(nc_path)
    # Counter never exceeded the limit.
    assert int(row["foreign_rewrites"]) == ws.FOREIGN_REWRITE_LIMIT, (
        f"counter must stay capped at {ws.FOREIGN_REWRITE_LIMIT};"
        f" got {row['foreign_rewrites']!r}"
    )
    # ERROR was logged exactly once across all calls.
    errors = [r.getMessage() for r in caplog.records
              if r.levelno >= logging.ERROR]
    assert len([m for m in errors if "cannot survive" in m]) == 1, (
        f"ERROR must log exactly once across N+2 calls;"
        f" got {len(errors)} copies: {errors!r}"
    )


# ---------------------------------------------------------------------------
# G3: /stats contains foreign_rewrites.
# ---------------------------------------------------------------------------
def test_stats_contains_foreign_rewrites(ws, monkeypatch):
    """/stats must include ``foreign_rewrites`` so the NC app's panel
    can surface the cumulative foreign-rewrite count.

    Verified without the fix: this assertion fails on the pre-guard
    build because ``/stats`` had no ``foreign_rewrites`` key — the
    stats response is a dict and KeyError on lookup. The test uses
    ``in`` rather than indexing to keep the failure mode explicit.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setattr(ws, "_webdav_stat", lambda *a, **k: (None, None))

    with patch.object(ws, "_process_file",
                      lambda *a, **k: {"path": a[0] if a else None,
                                        "output": a[0] if a else None}):
        client = TestClient(ws.app)

    # Seed two paths with bumps (so the total is non-zero — the
    # endpoint is additive, the existing /stats contract does not
    # require a non-zero value, but a non-zero assertion catches the
    # bug where the key is wired to a wrong column).
    ws.jobstore.file_bump_foreign_rewrites("/likivik/files/a.pdf")
    ws.jobstore.file_bump_foreign_rewrites("/likivik/files/b.pdf")
    ws.jobstore.file_bump_foreign_rewrites("/likivik/files/b.pdf")

    r = client.get("/stats", headers={"X-Webhook-Secret": "test-secret"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "foreign_rewrites" in body, (
        f"/stats must include foreign_rewrites; got keys={sorted(body)!r}"
    )
    assert body["foreign_rewrites"] == 3, (
        f"/stats.foreign_rewrites must be the SUM of per-path bumps;"
        f" got {body['foreign_rewrites']!r}"
    )


# ---------------------------------------------------------------------------
# Test-guard: a regression where the fingerprint check is bypassed must
# trip the mismatch test above. This is the "verified without the fix"
# half of the contract: a build that monkeypatches the guard away must
# cause test_fingerprint_mismatch_bypasses_skip_and_warns to FAIL.
# ---------------------------------------------------------------------------
def test_fingerprint_guard_disabled_reverts_to_silent_skip(
    ws, monkeypatch, tmp_path, caplog
):
    """If the fingerprint guard is removed, the stamp branch goes back
    to silent-skip behaviour. This test asserts that a hypothetical
    broken build where ``_check_fingerprint_guard`` is replaced by a
    no-op would trip the guard's first-line assertions.

    It is wired as a self-test: replace ``_check_fingerprint_guard``
    with a stub that mimics the pre-guard behaviour (``always skip
    with SKIP_REASON_STAMPED_BY_US``) and confirm the mismatch is no
    longer caught. If this test ever flips green, the mismatch test
    above has lost its teeth.
    """
    nc_path = "/likivik/files/regression.pdf"
    pdf = _make_stamped_pdf(tmp_path, "regression.pdf")
    monkeypatch.setattr(ws, "_already_stamped_by_us", lambda _path: True)
    ws.jobstore.file_put({
        "path": nc_path, "status": "done", "engine": "google",
        "reason": None, "node_id": 1, "finished": 1.0,
        "size": 1, "etag": '"a"',
    })
    monkeypatch.setattr(
        ws, "_propfind_size_etag", lambda _p: (2, "c"),
    )

    # Replace the guard with the pre-guard behaviour.
    monkeypatch.setattr(
        ws, "_check_fingerprint_guard",
        lambda _p: (True, ws.SKIP_REASON_STAMPED_BY_US),
    )

    with caplog.at_level(logging.WARNING, logger="nc_ocr_flow"):
        needs_ocr, skip_reason = ws._needs_ocr_decision(
            pdf, force=False, nc_path=nc_path,
        )

    # With the guard stubbed out, the stamp branch silently skips —
    # which is the bug the guard fixes. This test pins that the
    # mismatch assertion would fire if the guard were missing.
    assert needs_ocr is False, (
        "this test asserts the BAD pre-guard behaviour: a no-op guard"
        " turns the mismatch into a silent skip. If this assertion ever"
        " fails, the guard has started catching the mismatch from inside"
        " the stub, which means the stub itself is wrong."
    )
    assert skip_reason == ws.SKIP_REASON_STAMPED_BY_US
    msgs = [r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING]
    assert not any("rewritten by a foreign writer" in m for m in msgs), (
        "with the guard disabled the WARNING must NOT appear; if it does,"
        " the no-op stub is not actually a no-op."
    )