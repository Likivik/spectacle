{ inputs, den, lib, ... }:
{
  flake-file.inputs = {
    hermes-agent = {
      url = "github:NousResearch/hermes-agent";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.server.hermes-agent = {
    nixos = { config, pkgs, lib, ... }: let
      hermes-pkg = inputs.hermes-agent.packages.${pkgs.system}.messaging;

      mitmproxyConfig = import ./_mitmproxy.nix { inherit config pkgs lib; };
      graphitiConfig = import ./_graphiti.nix { inherit config pkgs lib; };
    in lib.mkMerge [
      mitmproxyConfig
      graphitiConfig
      {
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

        systemd.user.services.hermes-agent = {
          description = "Hermes Agent Gateway";
          after = [ "network-online.target" ];
          wants = [ "network-online.target" ];
          wantedBy = [ "default.target" ];

          unitConfig.ConditionUser = "hermes";

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
            Environment = [
              "HERMES_HOME=/var/lib/hermes/.hermes"
              "HOME=/var/lib/hermes"
              "OPENROUTER_API_KEY=hermes-proxy://openrouter"
              "GITHUB_TOKEN=hermes-proxy://github"
              "OPENCODE_GO_API_KEY=hermes-proxy://opencode"
              "HTTPS_PROXY=http://127.0.0.1:7899"
              "SSL_CERT_FILE=/etc/ssl/certs/hermes-with-proxy-ca.crt"
              "NO_PROXY=127.0.0.1,localhost"
              "WHATSAPP_ENABLED=false"
              "WHATSAPP_MODE=self-chat"
            ];
            EnvironmentFile = [ "/run/secrets/hermes/env" ];
          };
        };

        systemd.user.services.hermes-dashboard = {
          description = "Hermes Agent Dashboard";
          after = [ "hermes-agent.service" ];
          requires = [ "hermes-agent.service" ];
          wantedBy = [ "default.target" ];

          unitConfig.ConditionUser = "hermes";

          serviceConfig = {
            Restart = "always";
            RestartSec = 5;
            Environment = [
              "HERMES_HOME=/var/lib/hermes/.hermes"
              "_HERMES_GATEWAY=0"
              "HTTPS_PROXY=http://127.0.0.1:7899"
              "NO_PROXY=127.0.0.1,localhost"
            ];
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

          sudo -u hermes XDG_RUNTIME_DIR=/run/user/$(id -u hermes) ${pkgs.podman}/bin/podman system migrate || true
        '';

        systemd.tmpfiles.rules = [
          "f /var/lib/systemd/linger/hermes 0644 root root - -"
        ];
      }
    ];
  };
}
