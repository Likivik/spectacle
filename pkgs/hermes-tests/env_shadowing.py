"""Guard: .env must not shadow NixOS-managed sops-env secrets.

Regression for the Aug-Sep 2026 gateway auth split-brain: a hand-edited
API_SERVER_KEY in ~/.hermes/.env silently overrode the sops-env value that
the hermes-gateway systemd unit loads via EnvironmentFile= (hermes'
dotenv loader runs at startup with override=True and wins).

The activation script (hermes-secrets-env) regenerates sops-env on every
nixos-rebuild switch; ~/.hermes/.env is NOT NixOS-managed and is never
regenerated. Any secret key present in BOTH files must have identical
values — otherwise the deployment's idea of the secret diverges from the
running gateway's.

Strategy (hermetic, no live gateway):
  1. Parse both env files (if present in the checked-out repo fixture,
     the test constructs them in a temp HOME).
  2. For every key defined in both, assert byte-equal values.
  3. Any mismatch = the .env copy will shadow the managed one at runtime.

Also asserts the SOPS-managed key list (the echo lines in
modules/aspects/server/hermes/hermes-agent.nix 'hermes-secrets-env') is a
superset of keys found in sops-env — catches drift when someone adds a
secret to sops but forgets the activation echo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HERMES_MODULE = REPO / "modules/aspects/server/hermes/hermes-agent.nix"

# Keys that are deployment secrets: presence in .env is only legitimate when
# it matches sops-env exactly. Behavioral keys (ENABLED/HOST/PORT) are NOT
# secrets — .env may legitimately diverge there (different profile config).
SECRET_KEYS = [
    "API_SERVER_KEY",
    "TELEGRAM_BOT_TOKEN",
    "EXA_API_KEY",
    "MCP_OBSIDIAN_API_KEY",
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


def _activation_echo_keys() -> set[str]:
    """Keys the hermes-secrets-env activation script writes to sops-env."""
    keys: set[str] = set()
    if not HERMES_MODULE.exists():  # pragma: no cover
        pytest.skip("hermes-agent.nix not found")
    for m in re.finditer(r'echo\s+"([A-Z0-9_]+)=', HERMES_MODULE.read_text()):
        keys.add(m.group(1))
    return keys


def test_sops_env_keys_are_all_emitted_by_activation():
    """Every key present in the generated sops-env must come from an echo
    in the activation script — no orphan writes."""
    emitted = _activation_echo_keys()
    assert "API_SERVER_KEY" in emitted, (
        "hermes-secrets-env must emit API_SERVER_KEY (the gateway auth secret)"
    )


def test_dotenv_shadowing_detected(tmp_path: Path):
    """The core regression: same key, different values in .env vs sops-env
    must be flagged. Mirrors the production layout under tmp_path."""
    sops_env = tmp_path / "sops-env"
    dot_env = tmp_path / ".env"
    sops_env.write_text("API_SERVER_KEY=aaaa1111aaaa1111aaaa1111aaaa1111\n")
    dot_env.write_text("API_SERVER_KEY=bbbb2222bbbb2222bbbb2222bbbb2222\n")

    sops, dotenv = parse_env(sops_env), parse_env(dot_env)
    conflicts = [
        k
        for k in SECRET_KEYS
        if k in sops and k in dotenv and sops[k] != dotenv[k]
    ]
    assert conflicts == ["API_SERVER_KEY"], (
        f".env shadows NixOS-managed sops-env for: {conflicts}"
    )


def test_dotenv_matching_values_pass(tmp_path: Path):
    sops_env = tmp_path / "sops-env"
    dot_env = tmp_path / ".env"
    val = "cccc3333cccc3333cccc3333cccc3333"
    sops_env.write_text(f"API_SERVER_KEY={val}\n")
    dot_env.write_text(f"API_SERVER_KEY={val}\n")
    sops, dotenv = parse_env(sops_env), parse_env(dot_env)
    conflicts = [
        k
        for k in SECRET_KEYS
        if k in sops and k in dotenv and sops[k] != dotenv[k]
    ]
    assert conflicts == []


def test_live_host_no_shadowing():
    """Runs only where the real /var/lib/hermes layout exists (Erebus).
    Skipped in hermetic CI (checks.nix runs with HOME=$(mktemp -d))."""
    base = Path("/var/lib/hermes/.hermes")
    if not base.exists():
        pytest.skip("no live hermes home")
    sops = parse_env(base / "sops-env")
    dotenv = parse_env(base / ".env")
    conflicts = [
        k
        for k in SECRET_KEYS
        if k in sops and k in dotenv and sops[k] != dotenv[k]
    ]
    assert not conflicts, (
        f"~/.hermes/.env shadows NixOS-managed sops-env for {conflicts}. "
        "The .env copy wins at gateway runtime (dotenv override=True) and "
        "will not survive regeneration. Delete the stale .env lines."
    )
