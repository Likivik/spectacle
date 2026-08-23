"""No-VM import-contract smoke test for the hermes-agent venv.

Runs against the *sealed* hermes venv (hermes-pkg.hermesVenv) — the exact
closure the gateway loads. Catches, in seconds, the three dependency-class
regressions that each cost us a prod outage during the Aug 15-24 graphiti
work:

1. mcp 1.x -> 2.0.0 rename  (`streamablehttp_client` -> `streamable_http_client`)
2. opentelemetry-api too old (TraceFlags.RANDOM_TRACE_ID added in 1.42)
3. langfuse SDK missing from the venv (PYTHONPATH-layering anti-pattern)

Each assert maps to a real, observed failure mode. If a future dependency
bump re-breaks any of these, this check fails `nix flake check` before deploy.
"""

import sys


def main() -> int:
    # --- langfuse observability SDK must be in the sealed venv (no PYTHONPATH) ---
    import langfuse  # noqa: F401
    from langfuse import Langfuse, propagate_attributes  # noqa: F401

    # --- mcp 2.0.0 client (the 1.x -> 2.0 rename that broke the plugin) ---
    from mcp import ClientSession  # noqa: F401
    from mcp.client.streamable_http import streamable_http_client  # noqa: F401

    # --- opentelemetry >= 1.42 (TraceFlags.RANDOM_TRACE_ID) ---
    from opentelemetry.trace import TraceFlags

    assert hasattr(TraceFlags, "RANDOM_TRACE_ID"), (
        "opentelemetry-api too old: TraceFlags.RANDOM_TRACE_ID missing "
        "(mcp 2.0.0 requires otel >= 1.42)"
    )

    # otel SDK + OTLP HTTP exporter must resolve too (langfuse spans depend on them)
    import opentelemetry.sdk.trace  # noqa: F401
    import opentelemetry.sdk.resources  # noqa: F401
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: F401
        OTLPSpanExporter,
    )

    # mistralai must be ABSENT (its semconv<0.61 pin forces otel<=1.39, which is
    # exactly the broken state). Its presence means the fork extraction regressed.
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
