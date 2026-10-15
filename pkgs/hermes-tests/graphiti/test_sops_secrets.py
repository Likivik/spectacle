"""Hermetic sops secret-presence guard.

A blanked/missing sops key used to silently yield an empty env var (the
null-guarded ``cat ... || true`` pattern), which let the gateway boot with a
broken secret. The env file is now rendered by ``sops.templates`` — which fails
hard on a placeholder with no secret — but the failure this file guards is one
step earlier: a secret path referenced by the aspects that no host declares, or
that is absent from the encrypted file. Both otherwise show up only at runtime.

Exclusions (documented, intentional):
  - hermes/salem-bot-token   — profile token deferred, not provisioned yet
  - hermes-litellm/master-key — has a local-generation fallback (no sops key)
"""

from __future__ import annotations

import re
from pathlib import Path

EXCLUDE_SUFFIXES = ["salem-bot-token", "hermes-litellm"]

# Files that reference secrets, relative to the hermes aspect directory.
REFERRING_FILES = [
    "hermes-agent.nix",
    "_litellm.nix",
    "_graphiti.nix",
    "_hermes-graphiti.nix",
    "webui.nix",
]


def strip_comments(src: str) -> str:
    """Drop full-line comments: prose mentions a path without referencing it."""
    return "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )


def secret_refs(src: str) -> set[str]:
    """Every sops secret path the hermes aspects reference.

    Four shapes, all of which must be understood — a scan that knows only some
    of them silently drops coverage for the rest:
      * ``{ env = "KEY"; secret = "path"; }``  — a sops.templates row
      * ``sops.placeholder."path"``            — a literal placeholder
      * ``botTokenSecret = "path";``           — profile-parameterised
      * ``"/run/secrets/<path>"``              — EnvironmentFile / cat
    """
    src = strip_comments(src)
    refs: set[str] = set()
    refs |= set(re.findall(r'\{ env = "[A-Z][A-Z0-9_]*"; secret = "([^"]+)";', src))
    refs |= set(re.findall(r'sops\.placeholder\."([^"]+)"', src))
    refs |= set(re.findall(r'(?:botTokenSecret|apiKeySecret) = "([^"]+)";', src))
    refs |= {
        r[len("/run/secrets/") :].rstrip(".")
        for r in re.findall(r'"(/run/secrets/[^"]+)"', src)
    }
    # Unresolved Nix interpolations (${...}) cannot be checked here; their
    # concrete values appear literally in the profile definitions above, which
    # ARE checked, so nothing is lost.
    return {r for r in refs if "$" not in r and "/" in r}


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


def _referring_src(hermes_dir: Path) -> str:
    src = ""
    for f in REFERRING_FILES:
        p = hermes_dir / f
        if p.exists():
            src += p.read_text() + "\n"
    return src


def test_every_run_secrets_path_present(hermes_dir: Path):
    refs = secret_refs(_referring_src(hermes_dir))
    assert refs, "no secret refs found — extraction broken"

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


def _modules_root(hermes_dir: Path) -> Path:
    # modules/aspects/server/hermes -> repo root
    return hermes_dir.parents[3]


def test_every_referenced_secret_is_declared_somewhere(hermes_dir: Path):
    """Every secret path the hermes aspects reference must have a matching
    ``sops.secrets."<path>"`` declaration.

    The aspects are shared and the declarations are per host, so this is the
    union across all modules: it catches a secret added to a template (or an
    EnvironmentFile) that no host ever declares. That matters more now, not
    less — sops.templates makes an undeclared secret an EVAL error, because
    ``config.sops.placeholder."<path>"`` only exists for declared secrets.
    """
    refs = secret_refs(_referring_src(hermes_dir))
    assert refs, "no secret refs found — extraction broken"

    # Declarations come in two shapes: `sops.secrets."<path>" = {` and quoted
    # keys inside a `sops.secrets = { ... }` block. Only keys containing a "/"
    # are secret paths.
    declared: set[str] = set()
    for nix_file in sorted((_modules_root(hermes_dir) / "modules").rglob("*.nix")):
        text = strip_comments(nix_file.read_text())
        if "sops.secrets" not in text:
            continue
        declared.update(re.findall(r'sops\.secrets\."([^"]+)"', text))
        declared.update(re.findall(r'"([^"]*/[^"]*)"\s*=\s*\{', text))

    assert declared, "no sops.secrets declarations found — extraction broken"

    missing = sorted(
        ref
        for ref in refs
        if ref not in declared and not any(ex in ref for ex in EXCLUDE_SUFFIXES)
    )
    assert not missing, (
        "secrets referenced by the hermes aspects but declared by no "
        'sops.secrets."..." block: ' + ", ".join(missing)
    )
