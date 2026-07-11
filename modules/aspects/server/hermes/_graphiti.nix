{ config, pkgs, lib }: let
  openrouterKeyPath = lib.attrByPath [ "sops" "secrets" "hermes-mitmproxy/llm-providers/openrouter/api-key" "path" ] null config;
in {
  systemd.user.services.falkordb = {
    description = "FalkorDB Graph Database";
    after = [ "network.target" ];
    wantedBy = [ "default.target" ];

    unitConfig.ConditionUser = "hermes";

    serviceConfig = {
      ExecStartPre = "${pkgs.podman}/bin/podman rm -f falkordb || true";
      ExecStart = "${pkgs.podman}/bin/podman run --rm --name falkordb -p 127.0.0.1:6379:6379 -v /var/lib/hermes/falkordb-data:/data falkordb/falkordb-server:edge-alpine";
      ExecStop = "${pkgs.podman}/bin/podman stop falkordb";
      Restart = "on-failure";
      RestartSec = 5;
    };
  };

  systemd.user.services.graphiti-mcp = {
    description = "Graphiti MCP Server";
    after = [ "falkordb.service" ];
    wants = [ "falkordb.service" ];
    wantedBy = [ "default.target" ];

    unitConfig.ConditionUser = "hermes";

    serviceConfig = {
      WorkingDirectory = "/var/lib/hermes/graphiti/mcp_server";
      Environment = [
        "LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib"
        "HTTPS_PROXY=http://127.0.0.1:7899"
        "SSL_CERT_FILE=/etc/ssl/certs/hermes-with-proxy-ca.crt"
        "NO_PROXY=127.0.0.1,localhost"
      ];
      ExecStart = "${pkgs.bash}/bin/bash -c 'UV_PYTHON=${pkgs.python312}/bin/python3 && exec ${pkgs.uv}/bin/uv run main.py --transport http --host 127.0.0.1 --port 8000'";
      Restart = "on-failure";
      RestartSec = 5;
    };
  };

  system.activationScripts."hermes-graphiti-seed" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    mkdir -p /var/lib/hermes/falkordb-data
    chown hermes:hermes /var/lib/hermes/falkordb-data

    if [ ! -d /var/lib/hermes/graphiti ]; then
      ${pkgs.git}/bin/git clone https://github.com/getzep/graphiti /var/lib/hermes/graphiti
    fi
    chown -R hermes:hermes /var/lib/hermes/graphiti

    ${lib.optionalString (openrouterKeyPath != null) ''
      sudo -u hermes bash -c 'cd /var/lib/hermes/graphiti/mcp_server && UV_PYTHON=${pkgs.python312}/bin/python3 ${pkgs.uv}/bin/uv sync' || true

      _openrouter_key="$(cat "${openrouterKeyPath}")"
      mkdir -p /var/lib/hermes/graphiti/mcp_server/config
      cat > /var/lib/hermes/graphiti/mcp_server/config/config.yaml << CONFIGEOF
  llm:
    provider: "openai"
    model: "deepseek/deepseek-v4-flash:free"
    providers:
      openai:
        api_url: "https://openrouter.ai/api/v1"
        api_key: "$_openrouter_key"

  embedder:
    provider: "openai"
    model: "text-embedding-3-small"
    providers:
      openai:
        api_url: "https://openrouter.ai/api/v1"
        api_key: "$_openrouter_key"
  CONFIGEOF
      chown -R hermes:hermes /var/lib/hermes/graphiti/mcp_server/config
    ''}
  '';
}
