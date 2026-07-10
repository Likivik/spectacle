{ inputs, den, lib, ... }:
{
  den.aspects.server.hermes = {
    nixos = { config, pkgs, lib, ... }: let
      hermes-pkg = inputs.hermes-agent.packages.${pkgs.system}.messaging;
    in {
      users.groups.hermes = { };
      users.users.hermes = {
        isSystemUser = true;
        group = "hermes";
        home = "/var/lib/hermes";
        createHome = true;
        shell = pkgs.bash;
        subUidRanges = [{ startUid = 165536; count = 65536; }];
        subGidRanges = [{ startGid = 165536; count = 65536; }];
      };

      environment.systemPackages = [ hermes-pkg ];

      # FalkorDB via rootless Podman
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

      # Graphiti MCP server
      systemd.user.services.graphiti-mcp = {
        description = "Graphiti MCP Server";
        after = [ "falkordb.service" ];
        wants = [ "falkordb.service" ];
        wantedBy = [ "default.target" ];

        unitConfig.ConditionUser = "hermes";

        serviceConfig = {
          WorkingDirectory = "/var/lib/hermes/graphiti/mcp_server";
          ExecStart = "${pkgs.bash}/bin/bash -c 'export UV_PYTHON=${pkgs.python312}/bin/python3 && export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib && export OPENAI_API_KEY=$(${pkgs.gnugrep}/bin/grep \"^OPENROUTER_API_KEY=\" /run/secrets/hermes/env | ${pkgs.coreutils}/bin/cut -d= -f2-) && exec ${pkgs.uv}/bin/uv run main.py --transport http --host 127.0.0.1 --port 8000'";
          EnvironmentFile = [ "/run/secrets/hermes/env" ];
          Restart = "on-failure";
          RestartSec = 5;
        };
      };

      systemd.user.services.hermes-agent = {
        description = "Hermes Agent Gateway";
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        wantedBy = [ "default.target" ];

        unitConfig = {
          ConditionUser = "hermes";
        };

        serviceConfig = {
          WorkingDirectory = "/var/lib/hermes/workspace";
          ExecStart = "${hermes-pkg}/bin/hermes gateway";
          Restart = "always";
          RestartSec = 5;
          UMask = "0007";
          ProtectSystem = "full";
          ProtectHome = false;
          PrivateTmp = true;
          NoNewPrivileges = true;
          ReadWritePaths = [ "/var/lib/hermes" "/var/lib/hermes/workspace" ];
          Environment = [ "HERMES_HOME=/var/lib/hermes/.hermes" "HOME=/var/lib/hermes" ];
          EnvironmentFile = [ "/run/secrets/hermes/env" ];
        };
      };

      systemd.user.services.hermes-dashboard = {
        description = "Hermes Agent Dashboard";
        after = [ "hermes-agent.service" ];
        requires = [ "hermes-agent.service" ];
        wantedBy = [ "default.target" ];

        unitConfig = {
          ConditionUser = "hermes";
        };

        serviceConfig = {
          Restart = "always";
          RestartSec = 5;
          Environment = [ "HERMES_HOME=/var/lib/hermes/.hermes" "_HERMES_GATEWAY=0" ];
          ExecStart = "${hermes-pkg}/bin/hermes dashboard --host 0.0.0.0 --port 9119 --no-open";
          EnvironmentFile = [ "/run/secrets/hermes/env" ];
        };
      };

      system.activationScripts."hermes-seed" = lib.stringAfter (
        lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
      ) ''
        mkdir -p /var/lib/hermes/{.hermes,workspace}
        chown hermes:hermes /var/lib/hermes /var/lib/hermes/.hermes /var/lib/hermes/workspace
        chmod 2770 /var/lib/hermes /var/lib/hermes/.hermes /var/lib/hermes/workspace
        for _subdir in cron sessions logs memories plugins; do
          mkdir -p "/var/lib/hermes/.hermes/$_subdir"
          chown hermes:hermes "/var/lib/hermes/.hermes/$_subdir"
          chmod 2770 "/var/lib/hermes/.hermes/$_subdir"
        done
        mkdir -p /var/lib/hermes/.config/systemd/user
        ln -sf /etc/systemd/user/hermes-agent.service /var/lib/hermes/.config/systemd/user/
        ln -sf /etc/systemd/user/hermes-dashboard.service /var/lib/hermes/.config/systemd/user/
        chown -R hermes:hermes /var/lib/hermes/.config

        # Migrate podman storage for hermes user (fixes rootless GID extraction)
        sudo -u hermes XDG_RUNTIME_DIR=/run/user/$(id -u hermes) ${pkgs.podman}/bin/podman system migrate || true

        # FalkorDB data directory
        mkdir -p /var/lib/hermes/falkordb-data
        chown hermes:hermes /var/lib/hermes/falkordb-data

        # Graphiti — clone once, chown, uv sync
        if [ ! -d /var/lib/hermes/graphiti ]; then
          ${pkgs.git}/bin/git clone https://github.com/getzep/graphiti /var/lib/hermes/graphiti
        fi
        chown -R hermes:hermes /var/lib/hermes/graphiti
        sudo -u hermes bash -c 'cd /var/lib/hermes/graphiti/mcp_server && UV_PYTHON=${pkgs.python312}/bin/python3 ${pkgs.uv}/bin/uv sync' || true

        # Write Graphiti config with OpenRouter key from sops
        _openrouter_key="$(${pkgs.gnugrep}/bin/grep '^OPENROUTER_API_KEY=' /run/secrets/hermes/env | ${pkgs.coreutils}/bin/cut -d= -f2-)"
        mkdir -p /var/lib/hermes/graphiti/mcp_server/config
        cat > /var/lib/hermes/graphiti/mcp_server/config/config.yaml << CONFIGEOF
llm:
  provider: "openai"
  model: "deepseek/deepseek-v4-flash:free"
  providers:
    openai:
      api_url: "https://openrouter.ai/api/v1"
      api_key: "''${_openrouter_key}"

embedder:
  provider: "openai"
  model: "text-embedding-3-small"
  providers:
    openai:
      api_url: "https://openrouter.ai/api/v1"
      api_key: "''${_openrouter_key}"
CONFIGEOF
        chown -R hermes:hermes /var/lib/hermes/graphiti/mcp_server/config
      '';
    };
  };
}
