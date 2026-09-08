"""No-VM import-contract smoke test for the hermes-agent venv.

Runs against the *sealed* hermes venv (hermes-pkg.hermesVenv) — the exact
closure the gateway loads. Catches, in seconds, the dependency-class
regressions that each cost us a prod outage during the Aug 15-24 graphiti
work:

1. mcp 1.x -> 2.0.0 rename  (`streamablehttp_client` -> `streamable_http_client`)

Post fork-drop (Sep 2026):
- langfuse SDK is NO LONGER in the sealed venv: upstream ships it as a
  bundled opt-in plugin (plugins/observability/langfuse) that lazy-installs
  into HERMES_LAZY_INSTALL_TARGET on first use.
- otel is NO LONGER in the sealed venv either: it belongs to litellm's own
  closure now (proxy-runtime extra), not hermes'. The otel asserts moved to
  the `litellm-proxy-imports` flake check.
- mistralai assert kept: upstream marks it `false`; we route mistral via
  litellm. Presence in the venv means a stray extra regressed back in.

Each assert maps to a real, observed failure mode. If a future dependency
bump re-breaks any of these, this check fails `nix flake check` before deploy.
"""

import sys


def main() -> int:
    # --- mcp 2.0.0 client (the 1.x -> 2.0 rename that broke the plugin) ---
    from mcp import ClientSession  # noqa: F401
    from mcp.client.streamable_http import streamable_http_client  # noqa: F401

    # mistralai must be ABSENT (upstream marks mistralai = false; we route
    # mistral via litellm). Presence means a stray extra regressed back in.
    try:
        import mistralai  # noqa: F401
    except ImportError:
        pass
    else:
        print("FAIL: mistralai present in venv — re-pins semantic-conventions<0.61")
        return 1

    print("ALL VENV IMPORTS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
