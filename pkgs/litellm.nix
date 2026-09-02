# litellm 1.97.0 pinned + proxy deps restored. nixpkgs rev 56c02bc bumped litellm
# 1.89->1.97 but its packaging dropped the `[proxy]` extras, so `litellm.service`
# crashed at import (`No module named 'expression'`, then `'jwt'`, `'fastapi'`, …)
# and graphiti extraction silently lost episodes. litellm 1.97.0's own
# `[project.optional-dependencies].proxy` = gunicorn, uvicorn, fastapi, pyyaml,
# orjson, fastapi-sso, PyJWT, python-multipart, litellm-proxy-extras. We add the
# subset actually imported by the proxy source (grep `^(import|from) X` over
# litellm/): fastapi 196, orjson 12, yaml 9, jwt 9, fastapi_sso 5, uvicorn 10
# (runtime), plus `expression` (new dep of _experimental outbound_credentials).
# gunicorn + litellm-proxy-extras are NOT imported by litellm source — skipped.
{ lib, python3Packages, python3 }:

let
  expression = python3Packages.callPackage ./expression.nix { };
in
python3Packages.litellm.overridePythonAttrs (old: {
  postPatch =
    (old.postPatch or "")
    + ''
      # litellm 1.97.0's custom_logger_registry imports ~50 optional observability
      # SDKs UNCONDITIONALLY (boto3, agentops, braintrust, datadog, galileo, opik,
      # posthog, vantage, ...) — many absent from nixpkgs. Wrap each in try/except
      # so missing SDKs degrade instead of crashing proxy import. Mirror litellm's
      # own enterprise-logger handling.
      ${python3.interpreter} ${./litellm/make_lazy.py} litellm/litellm_core_utils/custom_logger_registry.py
    '';

  propagatedBuildInputs = (old.propagatedBuildInputs or [ ]) ++ [
    expression
    python3Packages.fastapi
    python3Packages.uvicorn
    python3Packages.pyyaml
    python3Packages.pyjwt
    python3Packages.orjson
    python3Packages.fastapi-sso
    python3Packages.python-multipart
    python3Packages.backoff
    python3Packages.apscheduler
    python3Packages.redis
    python3Packages.cryptography
    python3Packages.rich
    python3Packages.sse-starlette
    python3Packages.requests
    python3Packages.packaging
    # litellm hard-codes event loop "uvloop" on Linux (proxy_cli _get_loop_type),
    # which uvicorn dynamically imports at RUNTIME — invisible to import checks.
    python3Packages.uvloop
    # The proxy's DB exception handler (`is_database_infrastructure_error`) does a
    # lazy `import prisma` when handling auth errors (/health returns 500 without
    # it). The stack runs DB-less (no DATABASE_URL), so prisma is import-only here.
    python3Packages.prisma
    # langfuse_otel callback (litellm_settings.callbacks = ["langfuse_otel"])
    # needs the OTLP HTTP exporter at runtime — the load-bearing observability
    # path. opentelemetry deps are NOT in nixpkgs' litellm closure.
    python3Packages.opentelemetry-api
    python3Packages.opentelemetry-sdk
    python3Packages.opentelemetry-exporter-otlp-proto-http
    python3Packages.opentelemetry-semantic-conventions
  ];

  # The import chain that crashed (from the traceback):
  #   key_management_endpoints.py:46 -> outbound_credentials/__init__.py:15
  #   -> resolver.py -> client_credentials.py -> types.py:33
  #   -> `from expression import case, tag, tagged_union`.
  # Importing the outbound_credentials package re-runs that exact chain at
  # build time, so a missing `expression` (or any dep in it) fails the build.
  pythonImportsCheck = (old.pythonImportsCheck or [ ]) ++ [
    "litellm.proxy._experimental.mcp_server.outbound_credentials"
    "litellm.proxy.proxy_server"
  ];
})
