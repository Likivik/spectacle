"""Guard: .env must not shadow the NixOS-managed rendered env file.

Regression for the Aug-Sep 2026 gateway auth split-brain: a hand-edited
API_SERVER_KEY in ~/.hermes/.env silently overrode the sops value that the
hermes-gateway systemd unit loads via EnvironmentFile= (hermes' dotenv loader
runs at startup with override=True and wins).

The env file is rendered by sops-nix (`sops.templates`) in the same
sops-install-secrets pass that installs the secrets, so it is regenerated on
every switch. ~/.hermes/.env is NOT NixOS-managed and never regenerated. Any
secret key present in BOTH must have identical values — otherwise the
deployment's idea of the secret diverges from the running gateway's.

What is worth testing here, and what is not: the comparison itself is a
comprehension over two dicts, so a test that feeds it a crafted mismatch only
tests Python — it would pass forever regardless of this repo. There is no such
test. What IS tested is (a) the live host, where the comparison gets real
inputs, and (b) that the key sets it depends on are complete, which is where
drift would silently disable the guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HERMES_MODULE = REPO / "modules/aspects/server/hermes/hermes-agent.nix"

# Keys that are deployment secrets: presence in .env is only legitimate when it
# matches the rendered env file exactly. Behavioral keys (ENABLED/HOST/PORT) are
# NOT secrets — .env may legitimately diverge there (different profile config).
#
# Hand-maintained, which is a drift risk: add a secret to the template and this
# list does not grow by itself, silently narrowing the guard. Hence
# test_every_secret_backed_key_is_listed, which asserts the converse direction.
SECRET_KEYS = [
    "API_SERVER_KEY",
    "TELEGRAM_BOT_TOKEN",
    "EXA_API_KEY",
    "MINIMAX_API_KEY",
    "SYNTHETIC_API_KEY",
    "HERMES_LANGFUSE_PUBLIC_KEY",
    "HERMES_LANGFUSE_SECRET_KEY",
    "OPENROUTER_API_KEY",
    "GITHUB_TOKEN",
    # Found by test_every_secret_backed_key_is_listed: both are credentials the
    # template renders from sops, and both were uncovered here — a .env copy of
    # the dashboard password hash or session secret would have shadowed the
    # managed value with nothing checking it.
    "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH",
    "HERMES_DASHBOARD_BASIC_AUTH_SECRET",
]

_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_env(path: Path) -> dict[str, str]:
    """Minimal dotenv parser: KEY=VALUE lines, strips quotes, ignores
    comments/blank lines. Values are opaque (no $ expansion) — matches
    hermes_cli/env_loader behavior for these keys."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def _module_text() -> str:
    if not HERMES_MODULE.exists():  # pragma: no cover
        pytest.skip("hermes-agent.nix not found")
    return HERMES_MODULE.read_text()


def _row_keys(text: str) -> set[str]:
    """`{ env = "KEY"; secret = "..."; }` — a secret-backed template row."""
    return set(re.findall(r'\{ env = "([A-Z][A-Z0-9_]*)";', text))


def _placeholder_keys(text: str) -> set[str]:
    """`"KEY=${config.sops.placeholder.…}"` — the literal `=` form."""
    return set(re.findall(r'"([A-Z][A-Z0-9_]*)=\$\{config\.sops\.placeholder', text))


def _literal_keys(text: str) -> set[str]:
    """`"KEY=<literal>"` — a non-secret setting. Also matches the units'
    `Environment = [ "KEY=value" ]` entries, which is harmless: see
    test_sops_env_keys_are_all_in_the_template."""
    return set(re.findall(r'"([A-Z][A-Z0-9_]*)=[^"$]', text))


def test_sops_env_keys_are_all_in_the_template():
    """Every key this file treats as a secret must still be produced by the
    module — catches a key quietly dropped by a refactor.

    The scan is deliberately broad, so it also sees unit-level keys
    (HERMES_HOME, NO_PROXY, …). That does not weaken it: those are not in
    SECRET_KEYS, and a secret key appears in the template and nowhere else.
    """
    text = _module_text()
    keys = _row_keys(text) | _placeholder_keys(text) | _literal_keys(text)
    missing = [k for k in SECRET_KEYS if k not in keys]
    assert not missing, f"template no longer defines: {missing}"


def test_every_secret_backed_key_is_listed():
    """The converse of the check above, and the one that closes a silent hole.

    A secret-backed key is one whose value comes from a sops placeholder, either
    as a row or inline. Every such key must appear in SECRET_KEYS — otherwise a
    newly added secret is simply not covered by the shadowing comparison, and
    the guard fails OPEN without ever saying so.
    """
    text = _module_text()
    secret_backed = _row_keys(text) | _placeholder_keys(text)
    assert secret_backed, "no secret-backed keys found — extraction broken"
    unlisted = sorted(secret_backed - set(SECRET_KEYS))
    assert not unlisted, (
        f"secret-backed keys missing from SECRET_KEYS: {unlisted}. "
        "Add them, or the .env-shadowing guard silently stops covering them."
    )


def test_no_hand_rolled_env_generator():
    """A speed bump, not a behavioural test — deliberately, and worth saying so.

    The 2026-10-14 outage came from a `cat`-based activation script that wrote
    `KEY=` when a secret was unreadable. sops-nix renders atomically and refuses
    to render at all when a placeholder has no secret, so that failure mode left
    with the script. This only asserts the script has not been reintroduced by
    name; it cannot prove the env file still comes from sops-nix.
    """
    text = _module_text()
    assert "sops.templates" in text, "env file is no longer rendered by sops-nix"
    assert not re.search(r"hermes-secrets-env", text), (
        "a hand-rolled secrets-env activation script is back; "
        "the env file must come from sops.templates"
    )


def test_live_host_no_shadowing():
    """The only test here with real inputs: compares the LIVE rendered env file
    against ~/.hermes/.env. Skipped where that layout does not exist (hermetic CI
    runs with HOME=$(mktemp -d))."""
    rendered_path = Path("/run/secrets/rendered/hermes/sops-env")
    if not rendered_path.exists():
        pytest.skip("no live rendered env file")
    rendered = parse_env(rendered_path)
    dotenv = parse_env(Path("/var/lib/hermes/.hermes/.env"))
    conflicts = [
        k
        for k in SECRET_KEYS
        if k in rendered and k in dotenv and rendered[k] != dotenv[k]
    ]
    assert not conflicts, (
        f"~/.hermes/.env shadows the NixOS-managed env file for {conflicts}. "
        "The .env copy wins at gateway runtime (dotenv override=True) and "
        "will not survive regeneration. Delete the stale .env lines."
    )
