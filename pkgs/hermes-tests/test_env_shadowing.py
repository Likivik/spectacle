"""Guard: .env must not shadow NixOS-managed sops secrets.

Regression for the Aug-Sep 2026 gateway auth split-brain: a hand-edited
API_SERVER_KEY in ~/.hermes/.env silently overrode the sops value that the
hermes-gateway systemd unit loads via EnvironmentFile= (hermes' dotenv loader
runs at startup with override=True and wins).

The env file is now rendered by sops-nix (`sops.templates`), in the same
sops-install-secrets pass that installs the secrets, so it is regenerated on
every switch. ~/.hermes/.env is NOT NixOS-managed and never regenerated. Any
secret key present in BOTH files must have identical values — otherwise the
deployment's idea of the secret diverges from the running gateway's.

Strategy (hermetic, no live gateway):
  1. Parse both env files (constructed in a temp HOME).
  2. For every key defined in both, assert byte-equal values.
  3. Any mismatch = the .env copy will shadow the managed one at runtime.

Also asserts the sops-managed key list is extractable from the template in
modules/aspects/server/hermes/hermes-agent.nix — catches drift when someone
adds a key to the template and the extraction here stops seeing it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HERMES_MODULE = REPO / "modules/aspects/server/hermes/hermes-agent.nix"

# Keys that are deployment secrets: presence in .env is only legitimate when
# it matches the rendered env file exactly. Behavioral keys
# (ENABLED/HOST/PORT) are NOT secrets — .env may legitimately diverge there
# (different profile config).
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


def _template_keys() -> set[str]:
    """Keys the sops template writes into the rendered env file.

    Three shapes, all of which must be understood — a scan that only knows one
    of them silently stops covering the others:
      * `{ env = "KEY"; secret = "..."; }`   — a secret-backed row
      * `"KEY=${config.sops.placeholder.…}"` — the literal `=` form
      * `"KEY=<literal>"`                    — a non-secret setting
    """
    keys: set[str] = set()
    if not HERMES_MODULE.exists():  # pragma: no cover
        pytest.skip("hermes-agent.nix not found")
    text = HERMES_MODULE.read_text()
    keys |= set(re.findall(r'\{ env = "([A-Z][A-Z0-9_]*)";', text))
    keys |= set(re.findall(r'"([A-Z][A-Z0-9_]*)=\$\{config\.sops\.placeholder', text))
    keys |= set(re.findall(r'"([A-Z][A-Z0-9_]*)=[^"$]', text))
    return keys


def test_sops_env_keys_are_all_in_the_template():
    """Every key the rendered env file carries must be declared by the sops
    template — no orphan writes, and no key quietly dropped by a refactor."""
    keys = _template_keys()
    assert "API_SERVER_KEY" in keys, (
        "the sops template must define API_SERVER_KEY (the gateway auth secret)"
    )
    assert "TELEGRAM_BOT_TOKEN" in keys, (
        "the sops template must define TELEGRAM_BOT_TOKEN"
    )
    # Every key this file treats as a secret must still be produced somewhere.
    missing = [k for k in SECRET_KEYS if k not in keys]
    assert not missing, f"template no longer defines: {missing}"


def test_no_hand_rolled_env_generator():
    """The env file must be produced by sops-nix, not by a `cat`-based
    activation script.

    The 2026-10-14 outage was a generator that wrote `KEY=` when a secret was
    unreadable; sops-nix renders atomically and refuses to render at all when a
    placeholder has no secret. Reintroducing a hand-rolled writer would restore
    the failure mode, so it is asserted against directly.
    """
    text = HERMES_MODULE.read_text()
    assert "sops.templates" in text, "env file is no longer rendered by sops-nix"
    assert not re.search(r"hermes-secrets-env", text), (
        "a hand-rolled secrets-env activation script is back; "
        "the env file must come from sops.templates"
    )


def test_dotenv_shadowing_detected(tmp_path: Path):
    """The core regression: same key, different values in .env vs the rendered
    env file must be flagged. Mirrors the production layout under tmp_path."""
    rendered_env = tmp_path / "sops-env"
    dot_env = tmp_path / ".env"
    rendered_env.write_text("API_SERVER_KEY=aaaa1111aaaa1111aaaa1111aaaa1111\n")
    dot_env.write_text("API_SERVER_KEY=bbbb2222bbbb2222bbbb2222bbbb2222\n")

    rendered, dotenv = parse_env(rendered_env), parse_env(dot_env)
    conflicts = [
        k
        for k in SECRET_KEYS
        if k in rendered and k in dotenv and rendered[k] != dotenv[k]
    ]
    assert conflicts == ["API_SERVER_KEY"], (
        f".env shadows the NixOS-managed env file for: {conflicts}"
    )


def test_dotenv_matching_values_pass(tmp_path: Path):
    rendered_env = tmp_path / "sops-env"
    dot_env = tmp_path / ".env"
    val = "cccc3333cccc3333cccc3333cccc3333"
    rendered_env.write_text(f"API_SERVER_KEY={val}\n")
    dot_env.write_text(f"API_SERVER_KEY={val}\n")
    rendered, dotenv = parse_env(rendered_env), parse_env(dot_env)
    conflicts = [
        k
        for k in SECRET_KEYS
        if k in rendered and k in dotenv and rendered[k] != dotenv[k]
    ]
    assert conflicts == []


def test_live_host_no_shadowing():
    """Runs only where the real /var/lib/hermes layout exists. Skipped in
    hermetic CI (checks.nix runs with HOME=$(mktemp -d))."""
    base = Path("/run/secrets/rendered/hermes/sops-env")
    if not base.exists():
        pytest.skip("no live rendered env file")
    rendered = parse_env(base)
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
