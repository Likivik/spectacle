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
      anthropic-py = pkgs.python312.withPackages (ps: [ ps.pip ]);
      # Extra Python packages for Hermes plugins (langfuse SDK for observability).
      hermes-plugin-py = pkgs.python312.withPackages (ps: [ ps.langfuse ]);

      graphitiConfig = import ./_graphiti.nix { inherit config pkgs lib; };
      llamaConfig = import ./_llama.nix { inherit config pkgs lib; };
      graphitiMemoryConfig = import ./_hermes-graphiti.nix { inherit config pkgs lib; };
      searxngConfig = import ./_searxng.nix { inherit config pkgs lib; };
      playwrightConfig = import ./_playwright.nix { inherit config pkgs lib; };
      litellmConfig = import ./_litellm.nix { inherit config pkgs lib; };
    in lib.mkMerge [
      graphitiConfig
      llamaConfig
      graphitiMemoryConfig
      searxngConfig
      playwrightConfig
      litellmConfig
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
              "NO_PROXY=127.0.0.1,localhost"
            ];
            ExecStart = "${hermes-pkg}/bin/hermes dashboard --host 0.0.0.0 --port 9119 --no-open";
            EnvironmentFile = [ "/run/secrets/hermes/env" ];
          };
        };

        system.activationScripts."hermes-secrets-env" = lib.stringAfter (
          lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
        ) ''
          # Generate env file from individual sops secrets — same pattern as LiteLLM.
          # This file is NixOS-managed; hermes never touches it.
          SEED_DIR=/var/lib/hermes/.hermes
          ENV_FILE="$SEED_DIR/sops-env"
          {
            TG=$(cat /run/secrets/hermes/telegram-bot-token 2>/dev/null || true)
            EXA=$(cat /run/secrets/hermes/exa-api-key 2>/dev/null || true)
            OBS=$(cat /run/secrets/hermes/mcp-obsidian-api-key 2>/dev/null || true)
            MM=$(cat /run/secrets/hermes/minimax-api-key 2>/dev/null || true)
            SYN=$(cat /run/secrets/hermes/synthetic-api-key 2>/dev/null || true)
            APIK=$(cat /run/secrets/hermes/api-server-key 2>/dev/null || true)
            LFPK=$(cat /run/secrets/hermes/langfuse-public-key 2>/dev/null || true)
            LFSK=$(cat /run/secrets/hermes/langfuse-secret-key 2>/dev/null || true)
            ORK=$(cat /run/secrets/hermes-mitmproxy/llm-providers/openrouter/api-key 2>/dev/null || true)
            GH=$(cat /run/secrets/hermes-mitmproxy/github/pat-hermes-full 2>/dev/null || true)
            echo "TELEGRAM_BOT_TOKEN=$TG"
            echo "EXA_API_KEY=$EXA"
            echo "MCP_OBSIDIAN_API_KEY=$OBS"
            echo "MINIMAX_API_KEY=$MM"
            echo "SYNTHETIC_API_KEY=$SYN"
            echo "API_SERVER_KEY=$APIK"
            echo "HERMES_LANGFUSE_PUBLIC_KEY=$LFPK"
            echo "HERMES_LANGFUSE_SECRET_KEY=$LFSK"
            echo "HERMES_LANGFUSE_BASE_URL=https://cloud.langfuse.com"
            echo "OPENROUTER_API_KEY=$ORK"
            echo "GITHUB_TOKEN=$GH"
          } > "$ENV_FILE"
          chown hermes:hermes "$ENV_FILE"
          chmod 0600 "$ENV_FILE"
        '';

        # Gateway as a real NixOS-managed user unit — same pattern as
        # hermes-dashboard above. Replaces the old imperative
        # `hermes gateway install` dance, which silently broke on every boot:
        # boot-time activation runs before PAM/sudo-as-user works, so the
        # sudo -u hermes calls failed, but the preceding rm -f still deleted
        # the only copy of the unit file → not-found after every reboot.
        systemd.user.services.hermes-gateway = {
          description = "Hermes Agent Gateway - Messaging Platform Integration";
          after = [ "network-online.target" ];
          wants = [ "network-online.target" ];
          wantedBy = [ "default.target" ];

          unitConfig.ConditionUser = "hermes";

          serviceConfig = {
            Restart = "always";
            RestartSec = 5;
            Environment = [
              "HERMES_HOME=/var/lib/hermes/.hermes"
              "NO_PROXY=127.0.0.1,localhost"
              "WHATSAPP_ENABLED=false"
              "WHATSAPP_MODE=self-chat"
              "PYTHONPATH=${anthropic-py}/${anthropic-py.sitePackages}:${hermes-plugin-py}/${hermes-plugin-py.sitePackages}"
              "HERMES_BUNDLED_SKILLS=${hermes-pkg}/share/hermes-agent/skills"
              "HERMES_BUNDLED_PLUGINS=${hermes-pkg}/share/hermes-agent/plugins"
              "HERMES_BUNDLED_LOCALES=${hermes-pkg}/share/hermes-agent/locales"
              "HERMES_OPTIONAL_MCPS=${hermes-pkg}/share/hermes-agent/optional-mcps"
              "HERMES_LAZY_INSTALL_TARGET=/var/lib/hermes/.hermes/lazy-packages"
            ];
            ExecStart = "${hermes-pkg}/bin/hermes gateway run";
            EnvironmentFile = [
              "/run/secrets/hermes/env"
              "/var/lib/hermes/.hermes/sops-env"
            ];
          };
        };

        # Boot-safe one-time migration cleanup: purge remnants of the
        # hermes-CLI-managed gateway unit so they can't shadow or dangle
        # alongside the NixOS-managed one above. Pure filesystem ops (root),
        # no sudo/PAM — safe during boot-time activation.
        system.activationScripts."hermes-unit-cleanup" = lib.stringAfter (
          lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
        ) ''
          rm -f /var/lib/hermes/.config/systemd/user/default.target.wants/hermes-gateway.service
          rm -f /var/lib/hermes/.config/systemd/user/hermes-agent.service
          rm -f /var/lib/hermes/.config/systemd/user/hermes-dashboard.service
          rm -rf /var/lib/hermes/.config/systemd/user/hermes-gateway.service.d
          rm -f /var/lib/hermes/.config/systemd/user/hermes-gateway.service
          rm -f /var/lib/hermes/.hermes/.managed
          chown -R hermes:hermes /var/lib/hermes/.config/systemd
        '';

        system.activationScripts."hermes-seed" = lib.stringAfter [ "hermes-unit-cleanup" ] ''
          mkdir -p /var/lib/hermes/{.hermes,workspace}
          chown hermes:hermes /var/lib/hermes /var/lib/hermes/.hermes /var/lib/hermes/workspace
          chmod 2770 /var/lib/hermes /var/lib/hermes/.hermes /var/lib/hermes/workspace
          for _subdir in cron sessions logs memories plugins lazy-packages; do
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

        system.activationScripts."hermes-profile-env" = lib.stringAfter [ "hermes-seed" ] ''
          PROFILE="/var/lib/hermes/.profile"
          touch "$PROFILE"
          chown hermes:hermes "$PROFILE"
          chmod 0600 "$PROFILE"
          if ${pkgs.gnugrep}/bin/grep -q "hermes-mitmproxy" "$PROFILE"; then
            # Strip the (now-removed) mitmproxy proxy exports from a previous deploy
            ${pkgs.gnused}/bin/sed -i '/hermes-mitmproxy/d; /HTTPS_PROXY/d; /SSL_CERT_FILE/d; /REQUESTS_CA_BUNDLE/d' "$PROFILE"
            chown hermes:hermes "$PROFILE"
          fi
        '';

        systemd.tmpfiles.rules = [
          "f /var/lib/systemd/linger/hermes 0644 root root - -"
        ];
      }
    ];
  };
}
