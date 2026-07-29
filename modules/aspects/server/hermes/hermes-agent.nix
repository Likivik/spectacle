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
      llamaConfig = import ./_llama.nix { inherit config pkgs lib; };
    in lib.mkMerge [
      mitmproxyConfig
      graphitiConfig
      llamaConfig
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

        systemd.user.services.hermes-dashboard = {
          description = "Hermes Agent Dashboard";
          after = [ "network-online.target" ];
          wants = [ "network-online.target" ];
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

        system.activationScripts."hermes-gateway-install" = lib.stringAfter (
          lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
        ) ''
          # Remove any dangling symlinks from previous deploys
          rm -f /var/lib/hermes/.config/systemd/user/hermes-gateway.service
          rm -f /var/lib/hermes/.config/systemd/user/hermes-dashboard.service

          # Remove .managed marker so hermes gateway install + config writes work
          rm -f /var/lib/hermes/.hermes/.managed

          # Install gateway unit file — hermes creates a real file, owns it, can update it
          ${pkgs.sudo}/bin/sudo -u hermes \
            XDG_RUNTIME_DIR=/run/user/$(id -u hermes) \
            DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u hermes)/bus \
            HERMES_HOME=/var/lib/hermes/.hermes \
            HOME=/var/lib/hermes \
            PATH=${hermes-pkg}/bin:${pkgs.systemd}/bin:/run/wrappers/bin:/nix/var/nix/profiles/default/bin \
            ${hermes-pkg}/bin/hermes gateway install --force --start-now || true

          # Drop-in override for env vars — NixOS-managed, hermes never touches this
          mkdir -p /var/lib/hermes/.config/systemd/user/hermes-gateway.service.d
          cat > /var/lib/hermes/.config/systemd/user/hermes-gateway.service.d/override.conf << 'DROPEOF'
[Service]
Environment=OPENROUTER_API_KEY=hermes-proxy://openrouter
Environment=GITHUB_TOKEN=hermes-proxy://github
Environment=OPENCODE_GO_API_KEY=hermes-proxy://opencode
Environment=HTTPS_PROXY=http://127.0.0.1:7899
Environment=SSL_CERT_FILE=/etc/ssl/certs/hermes-with-proxy-ca.crt
Environment=NO_PROXY=127.0.0.1,localhost
Environment=WHATSAPP_ENABLED=false
Environment=WHATSAPP_MODE=self-chat
EnvironmentFile=/run/secrets/hermes/env
DROPEOF
          chown -R hermes:hermes /var/lib/hermes/.config/systemd/user/hermes-gateway.service.d
          chmod 644 /var/lib/hermes/.config/systemd/user/hermes-gateway.service.d/override.conf

          # Reload, enable, and start
          ${pkgs.sudo}/bin/sudo -u hermes \
            XDG_RUNTIME_DIR=/run/user/$(id -u hermes) \
            ${pkgs.systemd}/bin/systemctl --user daemon-reload
          ${pkgs.sudo}/bin/sudo -u hermes \
            XDG_RUNTIME_DIR=/run/user/$(id -u hermes) \
            ${pkgs.systemd}/bin/systemctl --user enable hermes-gateway.service
        '';

        system.activationScripts."hermes-seed" = lib.stringAfter [ "hermes-gateway-install" ] ''
          mkdir -p /var/lib/hermes/{.hermes,workspace}
          chown hermes:hermes /var/lib/hermes /var/lib/hermes/.hermes /var/lib/hermes/workspace
          chmod 2770 /var/lib/hermes /var/lib/hermes/.hermes /var/lib/hermes/workspace
          for _subdir in cron sessions logs memories plugins; do
            mkdir -p "/var/lib/hermes/.hermes/$_subdir"
            chown hermes:hermes "/var/lib/hermes/.hermes/$_subdir"
            chmod 2770 "/var/lib/hermes/.hermes/$_subdir"
          done
          mkdir -p /var/lib/hermes/.config/git
          cat > /var/lib/hermes/.config/git/config << 'GITEOF'
[fetch]
  prune = true
GITEOF
          chown -R hermes:hermes /var/lib/hermes/.config

          ${pkgs.sudo}/bin/sudo -u hermes XDG_RUNTIME_DIR=/run/user/$(id -u hermes) ${pkgs.podman}/bin/podman system migrate || true
        '';

        systemd.tmpfiles.rules = [
          "f /var/lib/systemd/linger/hermes 0644 root root - -"
        ];
      }
    ];
  };
}
