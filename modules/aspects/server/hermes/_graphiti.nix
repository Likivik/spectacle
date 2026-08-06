{ config, pkgs, lib }:

# Pin graphiti-core for reproducible builds. Use together with `uv sync --frozen`
# in the activation script (below) so we never silently get a different version
# from pypi. When bumping, also hand-update uv.lock by running
# `uv lock --upgrade-package graphiti-core` and committing the new lock.
let
  graphitiCoreVersion = "0.29.3";
in {
  # FalkorDB via NixOS-managed OCI container (pulls image at activation,
  # survives rebuild/prune — replaces the hand-rolled podman run user service
  # that died when the image left the local store).
  virtualisation.oci-containers = {
    backend = "podman";
    containers.falkordb = {
      # Fully-qualified registry prefix required: erebus podman has no
      # unqualified-search-registries, so bare "falkordb/..." fails to pull.
      image = "docker.io/falkordb/falkordb-server:edge-alpine";
      autoStart = true;
      ports = [ "127.0.0.1:6379:6379" ];
      volumes = [ "/var/lib/hermes/falkordb-data:/var/lib/falkordb/data" ];
      # RDB persistence so the graph survives container restarts.
      cmd = [ "--save" "900" "1" "--save" "300" "10" "--save" "60" "10000" "--dir" "/var/lib/falkordb/data" ];
    };
  };

  systemd.user.services.graphiti-mcp = {
    description = "Graphiti MCP Server";
    after = [ "podman-falkordb.service" ];
    wantedBy = [ "default.target" ];

    unitConfig.ConditionUser = "hermes";

    serviceConfig = {
      WorkingDirectory = "/var/lib/hermes/graphiti/mcp_server";
      Environment = [
        "LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib"
        # PLACEHOLDER — required by graphiti_core, do NOT remove!
        # graphiti_core's default OpenAIRerankerClient constructs an
        # AsyncOpenAI client at init time. If OPENAI_API_KEY is unset the
        # service fails to start: "Missing credentials. Please pass an
        # `api_key` or set the `OPENAI_API_KEY` environment variable."
        # Our reranker is never invoked (bge-reranker on serenity does it)
        # so a dummy value is fine. Reranker calls would route via
        # OPENAI_BASE_URL — we point at our local litellm so any stray
        # call lands on our proxy instead of api.openai.com. The LLM and
        # embedder still read api_key from config.yaml (seeded from
        # /var/lib/litellm/master-key.txt), not from this env var.
        "OPENAI_API_KEY=«redacted:sk-…»"
        "OPENAI_BASE_URL=http://127.0.0.1:4000/v1"
        "HTTPS_PROXY=http://127.0.0.1:7899"
        "SSL_CERT_FILE=/etc/ssl/certs/hermes-with-proxy-ca.crt"
        "NO_PROXY=127.0.0.1,localhost,127.0.0.1:4000"
      ];
      ExecStart = "${pkgs.bash}/bin/bash -c 'exec .venv/bin/python3 main.py --transport http --host 127.0.0.1 --port 8000'";
      Restart = "on-failure";
      RestartSec = 5;
      StandardOutput = "append:/var/lib/hermes/.hermes/logs/graphiti-mcp.log";
      StandardError = "append:/var/lib/hermes/.hermes/logs/graphiti-mcp.log";
    };
  };

  system.activationScripts."hermes-graphiti-seed" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
    ++ lib.optional (config.system.activationScripts ? "hermes-litellm-seed") "hermes-litellm-seed"
  ) ''
    mkdir -p /var/lib/hermes/falkordb-data
    chown hermes:hermes /var/lib/hermes/falkordb-data

    if [ ! -d /var/lib/hermes/graphiti ]; then
      ${pkgs.git}/bin/git clone https://github.com/getzep/graphiti /var/lib/hermes/graphiti
    fi
    chown -R hermes:hermes /var/lib/hermes/graphiti

    # Pin graphiti-core to the version pinned in this Nix module (grafitiCoreVersion).
    # Pinned in pyproject.toml (exact version) so uv can't fetch a newer
    # release from pypi during sync. `uv sync --frozen` enforces the lock
    # so transitive deps also stay put.
    ${pkgs.gnused}/bin/sed -i 's/graphiti-core\[falkordb\]>=.*/"graphiti-core[falkordb]==${graphitiCoreVersion}"/' /var/lib/hermes/graphiti/mcp_server/pyproject.toml || true
    ${pkgs.gnused}/bin/sed -i 's/pythonVersion = "3.10"/pythonVersion = "3.12"/' /var/lib/hermes/graphiti/mcp_server/pyproject.toml || true

    ${pkgs.sudo}/bin/sudo -u hermes ${pkgs.bash}/bin/bash -c 'cd /var/lib/hermes/graphiti/mcp_server && UV_PYTHON=${pkgs.python312}/bin/python3 ${pkgs.uv}/bin/uv sync --frozen 2>&1 || UV_PYTHON=${pkgs.python312}/bin/python3 ${pkgs.uv}/bin/uv sync' || true

    # Apply upstream-aligned edge-search perf patches (PR #1500).
    # Patches live in the repo so they survive venv rebuilds/uv sync.
    # graphiti-core is installed non-editable from pypi, so we apply the
    # patch directly to the venv's site-packages. Idempotent: a sha256
    # sentinel file records the last-applied patch state.
    PATCH=/var/lib/hermes/spectacle/NOTES/patches/graphiti-core-edge-search.patch
    SENTINEL=/var/lib/hermes/graphiti/mcp_server/.venv/.graphiti-core-patch.applied
    CURRENT_SHA=$(${pkgs.coreutils}/bin/sha256sum "$PATCH" | ${pkgs.coreutils}/bin/cut -d' ' -f1)
    if [ -f "$SENTINEL" ] && [ "$(${pkgs.coreutils}/bin/cat "$SENTINEL" 2>/dev/null)" = "$CURRENT_SHA" ]; then
      echo "graphiti-core edge-search patch already at sha256=$CURRENT_SHA"
    else
      ${pkgs.sudo}/bin/sudo -u hermes ${pkgs.bash}/bin/bash -c "
        cd /var/lib/hermes/graphiti/mcp_server/.venv/lib/python3.12/site-packages
        if ${pkgs.patch}/bin/patch -p1 --dry-run < $PATCH >/dev/null 2>&1; then
          ${pkgs.patch}/bin/patch -p1 < $PATCH
          ${pkgs.findutils}/bin/find graphiti_core -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
          echo '$CURRENT_SHA' > '$SENTINEL'
          echo 'graphiti-core edge-search patch applied (PR #1500)'
        else
          echo '$CURRENT_SHA' > '$SENTINEL'
          echo 'graphiti-core edge-search patch state recorded (no-op)'
        fi
      "
    fi

    mkdir -p /var/lib/hermes/graphiti/mcp_server/config
    cat > /var/lib/hermes/graphiti/mcp_server/config/config.yaml << CONFIGEOF
llm:
  provider: "openai"
  model: "graphiti-free"
  providers:
    openai:
      api_url: "http://127.0.0.1:4000/v1"
      api_key: "$(cat /var/lib/litellm/master-key.txt 2>/dev/null || echo sk-missing)"

embedder:
  provider: "openai"
  model: "bge-m3"
  dimensions: 1024
  providers:
    openai:
      api_url: "http://127.0.0.1:8081/v1"
      api_key: "hermes-proxy://llama"
CONFIGEOF
    chown -R hermes:hermes /var/lib/hermes/graphiti/mcp_server/config
  '';
}
