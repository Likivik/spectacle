"""Shared fixtures for the Hermes end-to-end test suite.

These tests live in pkgs/hermes-tests/ and assert on the *committed* Nix
source in the repo (config-contract tests) as well as runtime behaviour
(connectivity / graphiti extraction, gated behind @pytest.mark.live).
"""
from pathlib import Path

import pytest

# Locate the repo root robustly (works whether run from the source tree or
# from a sandboxed nix check): walk up until we find flake.nix / pkgs/.
def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "flake.nix").exists() and (p / "pkgs").is_dir():
            return p
    return start.parents[2]  # fallback: pkgs/hermes-tests/ -> repo

REPO_ROOT = _find_repo_root(Path(__file__).resolve())
HERMES_DIR = REPO_ROOT / "modules" / "aspects" / "server" / "hermes"

# Proxy/CA env vars that the mitmproxy credential proxy used to inject.
# After the removal these must never be set for the gateway.
STALE_PROXY_VARS = ["HTTPS_PROXY", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"]


def read_text(*parts: str) -> str:
    return (REPO_ROOT.joinpath(*parts)).read_text()


@pytest.fixture(scope="session")
def hermes_dir() -> Path:
    return HERMES_DIR


@pytest.fixture(scope="session")
def litellm_nix(hermes_dir: Path) -> str:
    return (hermes_dir / "_litellm.nix").read_text()


@pytest.fixture(scope="session")
def graphiti_nix(hermes_dir: Path) -> str:
    return (hermes_dir / "_graphiti.nix").read_text()


@pytest.fixture(scope="session")
def agent_nix(hermes_dir: Path) -> str:
    return (hermes_dir / "hermes-agent.nix").read_text()
