"""Hermetic sops secret-presence guard.

A blanked/missing sops key silently yields an empty env var (the null-guarded
``cat ... || true`` pattern in hermes-agent.nix / _litellm.nix), which lets the
gateway boot with a broken secret. This asserts every ``/run/secrets/<path>``
the hermes + litellm nix reads resolves to a key in secrets/erebus/secrets.yaml
— catching drift before deploy.

Exclusions (documented, intentional):
  - hermes/salem-bot-token   — profile token deferred, not provisioned yet
  - hermes-litellm/master-key — has a local-generation fallback (no sops key)
"""

from __future__ import annotations

import re
from pathlib import Path

EXCLUDE_SUFFIXES = ["salem-bot-token", "hermes-litellm"]


def sops_keys(text: str) -> set[str]:
    """Flatten a sops secrets.yaml key structure (dots) from indentation."""
    keys: set[str] = set()
    stack: list[tuple[int, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        if content.startswith("sops:"):
            break
        if ":" not in content:
            continue
        key = content.split(":", 1)[0].strip()
        if not key or not re.match(r"^[A-Za-z0-9._/-]+$", key):
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([k for _, k in stack] + [key])
        keys.add(path)
        stack.append((indent, key))
    return keys


def test_every_run_secrets_path_present(hermes_dir: Path):
    src = ""
    for f in ["hermes-agent.nix", "_litellm.nix", "_graphiti.nix", "_hermes-graphiti.nix"]:
        p = hermes_dir / f
        if p.exists():
            src += p.read_text() + "\n"

    refs = set(re.findall(r"/run/secrets/([A-Za-z0-9/._-]+)", src))
    assert refs, "no /run/secrets refs found — extraction broken"

    secrets_file = hermes_dir.parents[3] / "secrets" / "erebus" / "secrets.yaml"
    assert secrets_file.exists(), f"missing {secrets_file}"
    keys = sops_keys(secrets_file.read_text())

    missing = []
    for ref in sorted(refs):
        if any(ex in ref for ex in EXCLUDE_SUFFIXES):
            continue
        dot = ref.replace("/", ".")
        if dot not in keys:
            missing.append(f"{ref} -> {dot}")

    assert not missing, (
        "secrets referenced in nix but absent from secrets.yaml: " + ", ".join(missing)
    )
