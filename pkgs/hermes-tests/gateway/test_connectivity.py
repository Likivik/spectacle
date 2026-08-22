"""LIVE gateway connectivity tests — the mitmproxy-removal regression.

These assert that Hermes can actually reach Telegram over TLS *without* the
now-removed mitmproxy CA, and that the bot token is valid. They need real
network access (and the real bot token) so they are gated behind
`@pytest.mark.live` and skipped in hermetic CI.

Run them on the host with:
    .venv/bin/python -m pytest gateway/test_connectivity.py -m live
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.request

import pytest

pytestmark = pytest.mark.live

TOKEN_PATHS = [
    "/run/secrets/hermes/telegram-bot-token",
    "/var/lib/hermes/.secrets/telegram-bot-token",
]

TELEGRAM_API = "https://api.telegram.org"


def _bot_token() -> str:
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if tok:
        return tok
    for p in TOKEN_PATHS:
        if os.path.exists(p):
            tok = open(p, encoding="utf-8").read().strip()
            if tok:
                return tok
    pytest.skip("no bot token available (TELEGRAM_BOT_TOKEN or secret file)")


def _get(url: str, timeout: int = 15) -> tuple[int, bytes]:
    # Default SSL context = system CA bundle. If a stale mitmproxy CA were
    # still required, this would raise ssl.SSLCertVerificationError.
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-test"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.status, r.read()


def test_tls_to_telegram_without_mitmproxy_ca():
    # Plain GET to api.telegram.org — proves TLS + DNS + routing work with no
    # stale HTTPS_PROXY / SSL_CERT_FILE pointing at the removed proxy.
    status, body = _get(f"{TELEGRAM_API}/")
    assert status in (200, 404), f"unexpected status {status}"
    # Any well-formed response (the 404 JSON for "/") means TLS succeeded.


def test_bot_token_valid():
    token = _bot_token()
    status, body = _get(f"{TELEGRAM_API}/bot{token}/getMe")
    assert status == 200, f"getMe HTTP {status}: {body[:200]!r}"
    data = json.loads(body)
    assert data.get("ok") is True, f"getMe not ok: {data!r}"
    assert data["result"]["is_bot"] is True
    assert data["result"].get("username"), "bot has no username"
