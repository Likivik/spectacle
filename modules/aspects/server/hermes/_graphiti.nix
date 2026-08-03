{ config, pkgs, lib }: {
  systemd.user.services.falkordb = {
    description = "FalkorDB Graph Database";
    after = [ "network.target" ];
    wantedBy = [ "default.target" ];

    unitConfig.ConditionUser = "hermes";

    serviceConfig = {
      # Use - prefix to ignore non-zero exit (systemd doesn't run shell; || true is a shell construct)
      ExecStartPre = "-${pkgs.podman}/bin/podman rm -f falkordb";
      # Volume mount: container data dir is /var/lib/falkordb/data (not /data)
      # Pass --save args to enable RDB persistence (survives container restarts)
      # Pass --dir to write dump.rdb to the bind-mounted volume
      ExecStart = "${pkgs.podman}/bin/podman run --rm --name falkordb -p 127.0.0.1:6379:6379 -v /var/lib/hermes/falkordb-data:/var/lib/falkordb/data falkordb/falkordb-server:edge-alpine --save 900 1 --save 300 10 --save 60 10000 --dir /var/lib/falkordb/data";
      ExecStop = "${pkgs.podman}/bin/podman stop falkordb";
      Restart = "on-failure";
      RestartSec = 5;
    };
  };

  systemd.user.services.graphiti-mcp = {
    description = "Graphiti MCP Server";
    after = [ "falkordb.service" ];
    wantedBy = [ "default.target" ];

    unitConfig.ConditionUser = "hermes";

    serviceConfig = {
      WorkingDirectory = "/var/lib/hermes/graphiti/mcp_server";
      Environment = [
        "LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib"
        "OPENAI_API_KEY=«redacted:sk-…»"
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
