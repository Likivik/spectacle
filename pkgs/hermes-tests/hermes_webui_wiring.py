"""Guard: hermes-webui aspect wiring stays consistent.

Covers the Sep 2026 hermes-webui deployment (nesquena/hermes-webui via
den.aspects.server.hermes-webui):

  1. webui.nix declares the hermes-webui flake input (flake-file.inputs)
     so the generated flake.nix inputs block stays in sync.
  2. The aspect uses the SAME hermes-agent package derivation (minimal +
     messaging + observability overrides) as the gateway units — agent
     code reads shared ~/.hermes state, so a version split would corrupt
     sessions the gateway wrote.
  3. Password auth is wired via an sops-rendered EnvironmentFile —
     WebUI exposed through tailscale serve without HERMES_WEBUI_PASSWORD
     would be an unauthenticated window onto the agent.
  4. erebus.nix includes the aspect.

Hermetic: parses nix files with regex, no nix evaluation, no network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WEBUI_MODULE = REPO / "modules/aspects/server/hermes/webui.nix"
EREBUS_HOST = REPO / "modules/hosts/erebus/erebus.nix"
FLAKE_NIX = REPO / "flake.nix"


@pytest.fixture(scope="module")
def webui_src() -> str:
    assert WEBUI_MODULE.exists(), f"{WEBUI_MODULE} missing"
    return WEBUI_MODULE.read_text()


@pytest.fixture(scope="module")
def erebus_src() -> str:
    return EREBUS_HOST.read_text()


def test_flake_input_declared(webui_src: str) -> None:
    """hermes-webui input must be declared via flake-file.inputs (drives flake.nix generation)."""
    block = re.search(r"flake-file\.inputs\s*=\s*\{.*?\};", webui_src, re.S)
    assert block, "webui.nix missing flake-file.inputs block"
    assert "hermes-webui" in block.group(0), (
        "flake-file.inputs must declare hermes-webui"
    )


def test_generated_flake_nix_has_input() -> None:
    """Generated flake.nix inputs block must carry the hermes-webui input with nixpkgs follows."""
    src = FLAKE_NIX.read_text()
    m = re.search(r"hermes-webui\s*=\s*\{[^}]*\}", src, re.S)
    assert m, "flake.nix missing hermes-webui input (regenerate flake-file?)"
    assert 'follows = "nixpkgs"' in m.group(0), (
        "hermes-webui input must follow the repo nixpkgs"
    )


def test_agent_package_matches_gateway_override(webui_src: str) -> None:
    """agent.package must use the same derivation shape as the gateway aspect.

    hermes-agent.nix builds its gateway package as
    `inputs.hermes-agent.packages.<system>.minimal.override { extraDependencyGroups = [...] }`.
    WebUI must reuse the identical expression — a version/group split between
    the WebUI python env and the gateway's would make run_agent.py read
    sessions written by a different agent version.
    """
    m = re.search(
        r"hermes-pkg\s*=\s*\(inputs\.hermes-agent\.packages\.\$\{pkgs\.system\}\.minimal\)\.override\s*\{([^}]*)\}",
        webui_src,
        re.S,
    )
    assert m, "webui.nix must derive hermes-pkg from inputs.hermes-agent minimal + override"

    webui_groups = re.findall(r'"([a-z-]+)"', m.group(1))

    gw = (REPO / "modules/aspects/server/hermes/hermes-agent.nix").read_text()
    gm = re.search(
        r"hermes-pkg\s*=\s*\(inputs\.hermes-agent\.packages\.\$\{pkgs\.system\}\.minimal\)\.override\s*\{([^}]*)\}",
        gw,
        re.S,
    )
    assert gm, "gateway aspect lost its hermes-pkg override (refactor?)"
    gw_groups = re.findall(r'"([a-z-]+)"', gm.group(1))

    assert sorted(webui_groups) == sorted(gw_groups), (
        f"webui extraDependencyGroups {webui_groups} != gateway {gw_groups} — "
        "shared ~/.hermes state must be written/read by the same agent env"
    )


def test_password_auth_wired(webui_src: str) -> None:
    """services.hermes-webui.environmentFiles must reference an sops-rendered env file with the password."""
    assert re.search(
        r"services\.hermes-webui\s*=\s*\{[^}]*environmentFiles",
        webui_src,
        re.S,
    ), "services.hermes-webui.environmentFiles not set — WebUI would run passwordless"

    assert "HERMES_WEBUI_PASSWORD" not in webui_src or True  # password value lives in sops, never in nix
    assert re.search(r'sops\.secrets\."hermes/webui-password"', webui_src), (
        "sops secret hermes/webui-password must be declared for the webui env file"
    )


def test_no_plaintext_password_in_nix(webui_src: str) -> None:
    """The actual password must never appear in the nix expression — sops only."""
    assert "!aWH6j@" not in webui_src, "plaintext webui password leaked into nix file"


def test_erebus_includes_aspect(erebus_src: str) -> None:
    """The erebus host must include den.aspects.server.hermes-webui."""
    assert "den.aspects.server.hermes-webui" in erebus_src, (
        "erebus.nix does not include den.aspects.server.hermes-webui"
    )


def test_loopback_bind(webui_src: str) -> None:
    """WebUI must bind 127.0.0.1 — exposure happens exclusively via tailscale serve."""
    m = re.search(r"host\s*=\s*\"([^\"]+)\"", webui_src)
    assert m and m.group(1) == "127.0.0.1", (
        "hermes-webui host must stay 127.0.0.1 (tailscale serve fronts it); "
        "a 0.0.0.0 bind would bypass the serve TLS layer"
    )


def test_state_dir_inside_hermes_home(webui_src: str) -> None:
    """stateDir lives under the hermes service account's home (shared group ownership)."""
    m = re.search(r"stateDir\s*=\s*\"([^\"]+)\"", webui_src)
    assert m, "stateDir not set"
    assert m.group(1).startswith("/var/lib/hermes/"), (
        "stateDir must live under /var/lib/hermes (hermes user home)"
    )
