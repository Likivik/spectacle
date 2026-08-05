{ config, pkgs, lib }: {
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
        # OPENAI_API_KEY is required by graphiti_core's default OpenAIRerankerClient,
        # which constructs an AsyncOpenAI client at init time even though the
        # reranker is never used in our setup (we have bge-reranker on serenity).
        # The reranker would route via OPENAI_BASE_URL if invoked. We point at
        # the local litellm gateway so any accidental call lands on our proxy
        # instead of api.openai.com. The LLM and embedder still read api_key
        # from /var/lib/hermes/graphiti/mcp_server/config/config.yaml which is
        # seeded from /var/lib/litellm/master-key.txt at activation time.
        "OPENAI_API_KEY=sk-local-litellm-noop"
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

    ${pkgs.sudo}/bin/sudo -u hermes bash -c 'cd /var/lib/hermes/graphiti/mcp_server && UV_PYTHON=${pkgs.python312}/bin/python3 ${pkgs.uv}/bin/uv sync' || true

    ${pkgs.gnused}/bin/sed -i 's/pythonVersion = "3.10"/pythonVersion = "3.12"/' /var/lib/hermes/graphiti/mcp_server/pyproject.toml || true

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
