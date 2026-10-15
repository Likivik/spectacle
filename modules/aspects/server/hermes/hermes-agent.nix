{ inputs, den, lib, ... }:
{
  den.aspects.server.hermes-agent = {
    nixos = { config, pkgs, lib, ... }: let
      # Upstream v0.21.1: otel 1.39.1 suffices (mcp 2.0.0 requires >=1.28; no
      # code uses TraceFlags.RANDOM_TRACE_ID). Langfuse ships as bundled opt-in
      # plugin; SDK lazy-installs into HERMES_LAZY_INSTALL_TARGET (~/.hermes/
      # lazy-packages) on first enable. No `observability` extra upstream.
      # version: v0.21.7 moved to stamp-based versioning — pyproject.toml now
      # carries the `0.0.0` placeholder and the CLI reads baseVersion from
      # install-stamp.json. Nix sources keep no .git, so nothing can infer the
      # tag; upstream's flake leaves `version ? "0.0.0"` and stamps 0.0.0
      # (upstream #130070, open). Pass it explicitly.
      # ⚠ keep in sync with the hermes-agent input tag in flake.nix /
      #   modules/defaults/inputs.nix.
      hermes-pkg = (inputs.hermes-agent.packages.${pkgs.system}.minimal).override {
        extraDependencyGroups = [ "messaging" "anthropic" ];
        version = "0.21.7";
      };

      # Extra (non-default) Hermes profiles. `default` stays hardcoded below for
      # zero churn; these get parameterized gateway units + graphiti wiring.
      # apiPort: per-profile gateway API listener (each profile owns its own
      # port; default = 8642, first extra = 8643, ...).apiKeySecret: sops path
      # for that profile's API_SERVER_KEY.
      extraHermesProfiles = [
        {
          name = "salem";
          home = "/var/lib/hermes/.hermes/profiles/salem";
          botTokenSecret = "hermes/salem-bot-token";
          apiPort = 8643;
          apiKeySecret = "hermes/salem-api-server-key";
        }
      ];

      graphitiConfig = import ./_graphiti.nix { inherit config pkgs lib; };
      # The agent's own bge-m3 embedder (:8081, used by graphiti's vector
      # search). Skipped on serenity — see the gate in the mkMerge below.
      llamaConfigRaw = import ./_llama.nix { inherit config pkgs lib; };
      graphitiMemoryConfig = import ./_hermes-graphiti.nix { inherit config pkgs lib; extraProfiles = extraHermesProfiles; };
      playwrightConfig = import ./_playwright.nix { inherit config pkgs lib; };
      litellmConfig = import ./_litellm.nix { inherit config pkgs lib; };

      # ── Secrets → env, done by sops-nix instead of by us ──────────────
      #
      # sops-nix renders these templates inside the SAME `sops-install-secrets`
      # manifest pass that installs the secrets, and places the result with
      # os.Rename — so the file is atomic, ordered after the secrets it reads,
      # and a placeholder with no matching secret is a hard ERROR instead of a
      # blank. That is the entire reason this replaced the hand-rolled
      # activation script that used to `cat` each secret file: that script wrote
      # `KEY=` whenever a secret was unreadable, and because this file is the
      # LAST EnvironmentFile a unit loads, systemd let the blank silently win
      # over the real value. On 2026-10-14 that cost Telegram ~11h.
      #
      # Values never reach the Nix store: `sops.placeholder.<name>` evaluates to
      # "<SOPS:<sha256 of the NAME>:PLACEHOLDER>" and the installer substitutes
      # the real value at activation. So template content may ONLY contain
      # placeholders — a literal secret here would land in the world-readable
      # store. Enforced by the assertion below (the key *shapes* are covered
      # separately by pkgs/hermes-tests).
      #
      # One list per profile drives the template, and the coverage test reads
      # these rows. The smoke gate's dummy secret set instead follows the host's
      # sops.secrets declarations — which a row requires anyway, since
      # `sops.placeholder.<name>` only exists for a declared secret, so an
      # undeclared one is an eval error rather than a missing env var. Add a row
      # AND declare the secret, and all three follow.
      commonSecretEnv = [
        { env = "EXA_API_KEY"; secret = "hermes/exa-api-key"; }
        { env = "MINIMAX_API_KEY"; secret = "hermes/minimax-api-key"; }
        { env = "SYNTHETIC_API_KEY"; secret = "hermes/synthetic-api-key"; }
        { env = "HERMES_LANGFUSE_PUBLIC_KEY"; secret = "langfuse/hermes-erebus/public-key"; }
        { env = "HERMES_LANGFUSE_SECRET_KEY"; secret = "langfuse/hermes-erebus/secret-key"; }
        { env = "OPENROUTER_API_KEY"; secret = "hermes-mitmproxy/llm-providers/openrouter/api-key"; }
        { env = "GITHUB_TOKEN"; secret = "hermes-mitmproxy/github/pat-hermes-full"; }
      ];

      # The default profile additionally carries dashboard password auth.
      defaultSecretEnv = commonSecretEnv ++ [
        { env = "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH"; secret = "hermes/dashboard-basic-auth-hash"; }
        { env = "HERMES_DASHBOARD_BASIC_AUTH_SECRET"; secret = "hermes/dashboard-basic-auth-secret"; }
      ];

      # Non-secret settings that every consumer of the env file expects. They
      # live here (not only in serviceConfig.Environment) because the webui
      # loads the same file as a different service.
      commonLiteralEnv = apiPort: [
        "API_SERVER_ENABLED=true"
        "API_SERVER_HOST=0.0.0.0"
        "API_SERVER_PORT=${toString apiPort}"
        "HERMES_LANGFUSE_BASE_URL=https://cloud.langfuse.com"
      ];

      # The exact non-placeholder lines a template is permitted to contain.
      # Deliberately NOT derived from commonLiteralEnv: an allow-list built from
      # the same binding it validates would approve anything added there —
      # including a secret, which is the one thing this guard exists to stop.
      # Adding a legitimate new literal therefore means two edits, and that
      # duplication is the point: it is an independent statement of intent.
      permittedLiteralLines = [
        "API_SERVER_ENABLED=true"
        "API_SERVER_HOST=0.0.0.0"
        "API_SERVER_PORT=8642"
        "API_SERVER_PORT=8643"
        "HERMES_LANGFUSE_BASE_URL=https://cloud.langfuse.com"
        "HERMES_DASHBOARD_BASIC_AUTH_USERNAME=likivik"
      ];

      mkSopsTemplate = { botTokenSecret, apiKeySecret, apiPort, secretEnv, extraLiterals ? [ ] }: {
        content = lib.concatStringsSep "\n" (
          [ "TELEGRAM_BOT_TOKEN=${config.sops.placeholder.${botTokenSecret}}" ]
          ++ map (r: "${r.env}=${config.sops.placeholder.${r.secret}}") secretEnv
          ++ [ "API_SERVER_KEY=${config.sops.placeholder.${apiKeySecret}}" ]
          ++ commonLiteralEnv apiPort
          ++ extraLiterals
        ) + "\n";
        owner = "hermes";
        mode = "0600";
      };

      # Template name -> rendered path. `/run/secrets/rendered/<name>`, inside
      # /run/secrets/ so the smoke gate's path discovery picks it up like any
      # other secret (sops-install-secrets MkdirAll's the parent).
      sopsTemplates = {
        "hermes/sops-env" = mkSopsTemplate {
          botTokenSecret = "hermes/telegram-bot-token";
          apiKeySecret = "hermes/api-server-key";
          apiPort = 8642;
          secretEnv = defaultSecretEnv;
          extraLiterals = [ "HERMES_DASHBOARD_BASIC_AUTH_USERNAME=likivik" ];
        };
      } // lib.listToAttrs (map (p:
        lib.nameValuePair "hermes/${p.name}-sops-env" (mkSopsTemplate {
          inherit (p) botTokenSecret apiKeySecret apiPort;
          secretEnv = commonSecretEnv;
        })
      ) extraHermesProfiles);

      envFileFor = name: config.sops.templates.${name}.path;

      # Opt each extra profile out of the host multiplexer so its own unit can
      # serve it. Gated by a grep so the CLI call only happens when the key is
      # missing — same idiom as _hermes-graphiti.nix.
      mkStandalone = { home, ... }: ''
        if ! ${pkgs.gnugrep}/bin/grep -q "standalone: true" "${home}/config.yaml" 2>/dev/null; then
          ${pkgs.sudo}/bin/sudo -u hermes ${pkgs.bash}/bin/bash -c '
            export HOME=/var/lib/hermes
            export HERMES_HOME=${home}
            export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
            export PATH=/run/current-system/sw/bin:/etc/profiles/per-user/hermes/bin
            /run/current-system/sw/bin/hermes config set gateway.standalone true
          '
        fi
      '';

      # Per-profile gateways: 0.21.5 multiplexes ONE gateway per host, so a
      # profile's own unit only starts if that profile opts out of the host
      # multiplexer. The opt-out lives in the profile's own (Hermes-owned)
      # config.yaml as `gateway.standalone: true` — set below through the
      # supported CLI, never by hand-editing that file.
      # See hermes_cli/profiles.py:profile_is_standalone + profiles_to_serve.

      # `hermes-gateway-<name>` is a per-profile gateway that uses the
      # rendered env from the corresponding sops template (placed on disk by
      # sops-install-secrets.service). Both ordering lines below are mandatory:
      #   * sops-install-secrets.service — the rendered EnvironmentFile this
      #     unit reads does not exist before that service completes. Without
      #     this, the unit starts in parallel and exits on a missing env file
      #     (2026-10-15 14:02:41 incident). Restart=always masked it; the
      #     ordering stops the mask instead.
      #   * hermes-gateway.service — the default-profile gateway. Salem runs
      #     with `gateway.standalone: true` and refuses to start while
      #     another gateway owns the host socket but has not yet published
      #     its served-set (CLI exit 75/TEMPFAIL). Waiting for the default
      #     gateway removes the race, so the retry chain (typically 3-4
      #     cycles at RestartSec=5) collapses to one start.
      extraGatewayUnits = lib.listToAttrs (map (p:
        lib.nameValuePair "hermes-gateway-${p.name}" {
          description = "Hermes Agent Gateway (${p.name})";
          after = [
            "network-online.target"
            "sops-install-secrets.service"
            "hermes-gateway.service"
          ];
          wants = [
            "network-online.target"
            "sops-install-secrets.service"
            "hermes-gateway.service"
          ];
          wantedBy = [ "default.target" ];
          unitConfig.ConditionUser = "hermes";
          serviceConfig = {
            Restart = "always";
            RestartSec = 5;
            Environment = [
              "HERMES_HOME=${p.home}"
              "HERMES_PROFILE=${p.name}"
              "NO_PROXY=127.0.0.1,localhost"
              "WHATSAPP_ENABLED=false"
              "WHATSAPP_MODE=self-chat"
              "HERMES_BUNDLED_SKILLS=${hermes-pkg}/share/hermes-agent/skills"
              "HERMES_BUNDLED_PLUGINS=${hermes-pkg}/share/hermes-agent/plugins"
              "HERMES_BUNDLED_LOCALES=${hermes-pkg}/share/hermes-agent/locales"
              "HERMES_OPTIONAL_MCPS=${hermes-pkg}/share/hermes-agent/optional-mcps"
              "HERMES_LAZY_INSTALL_TARGET=${p.home}/lazy-packages"
            ];
            ExecStart = "${hermes-pkg}/bin/hermes gateway run";
            EnvironmentFile = [
              "/run/secrets/hermes/env"
              (envFileFor "hermes/${p.name}-sops-env")
            ];
          };
        }
      ) extraHermesProfiles);
    in lib.mkMerge [
      graphitiConfig
      # Gate by host, the same idiom nc-rag uses for its host-specific units:
      # serenity already runs an identical bge-m3 embedder for nc-rag (same
      # model, same port, CUDA), so the agent's copy is skipped there instead
      # of colliding on :8081 and pulling a second copy of the weights.
      (lib.mkIf (config.networking.hostName != "serenity") llamaConfigRaw)
      graphitiMemoryConfig
      playwrightConfig
      litellmConfig
      (lib.mkIf (extraHermesProfiles != []) {
        systemd.user.services = extraGatewayUnits;
        system.activationScripts."hermes-standalone-profiles" =
          lib.stringAfter [ "hermes-seed" ] (lib.concatMapStringsSep "\n" mkStandalone extraHermesProfiles);
      })
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
          # nix-maid declares maid-activation.service host-wide, so *every* user gets
          # the unit, while system.build.all-maid only links a bundle for users whose
          # `maid` is non-null (nix-maid: maidUsers = filterAttrs (... maid != null)).
          # The unit hardcodes $all-maid/nix-maid-$USER/bin/activate, so for a user
          # with no maid config it execs a path that was never built -> exit 127.
          # An empty config is all it takes: the bundle exists, and the unit becomes
          # a no-op. (Not a class question - hermes isn't a den user.)
          maid = { };
        };

        environment.systemPackages = [ hermes-pkg ];

        # Secrets reach every unit as a rendered env file, never as a
        # hand-written one. See the sopsTemplates block above for why.
        sops.templates = sopsTemplates;

        # A literal secret typed into a template would land in the
        # world-readable Nix store, because template content is written there as
        # a plain file (only the placeholders are inert). Only placeholders and
        # the explicitly allow-listed non-secret settings may appear; anything
        # else fails the build rather than leaking.
        assertions = [
          {
            assertion = lib.all
              (t:
                lib.all
                  (l:
                    lib.hasInfix "PLACEHOLDER>" l
                    || lib.elem l permittedLiteralLines)
                  (lib.filter (l: l != "") (lib.splitString "\n" t.content)))
              (lib.attrValues sopsTemplates);
            message = ''
              A sops.templates entry in the hermes-agent aspect has a line that
              is neither a sops placeholder nor an allow-listed setting.
              Template content is written to the world-readable Nix store, so a
              literal secret there is a leak. Add a
              `{ env = "..."; secret = "..."; }` row to commonSecretEnv (or
              defaultSecretEnv) instead of typing the value.
            '';
          }
        ];

        systemd.user.services.hermes-dashboard = {
          description = "Hermes Agent Dashboard";
          # Order against sops-install-secrets.service so the rendered
          # EnvironmentFile is present when this unit starts. The sops-env
          # template is rendered inside sops-install-secrets.service, so before
          # this ordering (commit "fix(hermes): render the env file with
          # sops.templates, not a script") the unit started in parallel with
          # that service, opened an empty EnvironmentFile, and systemd logged
          # "Failed to load environment files" → first-start exit code.
          # Restart=always then hid it. Keep the ordering in lockstep with the
          # sops.templates list above so a future env-file addition does not
          # silently regress the same race.
          after = [
            "network-online.target"
            "sops-install-secrets.service"
          ];
          wants = [
            "network-online.target"
            "sops-install-secrets.service"
          ];
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
            EnvironmentFile = [
              "/run/secrets/hermes/env"
              (envFileFor "hermes/sops-env")
            ];
          };
        };

        # Gateway as a real NixOS-managed user unit — same pattern as
        # hermes-dashboard above. Replaces the old imperative
        # `hermes gateway install` dance, which silently broke on every boot:
        # boot-time activation runs before PAM/sudo-as-user works, so the
        # sudo -u hermes calls failed, but the preceding rm -f still deleted
        # the only copy of the unit file → not-found after every reboot.
        systemd.user.services.hermes-gateway = {
          description = "Hermes Agent Gateway - Messaging Platform Integration";
          # Order against sops-install-secrets.service: this unit's
          # EnvironmentFile is a sops.templates render, populated by
          # sops-install-secrets.service. Without this directive, the user
          # unit starts in parallel with that service and exits on
          # "Failed to load environment files" (cf. 2026-10-15 14:02:41
          # incident). Restart=always masked the race; the ordering stops the
          # mask instead.
          after = [
            "network-online.target"
            "sops-install-secrets.service"
          ];
          wants = [
            "network-online.target"
            "sops-install-secrets.service"
          ];
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
              # Default profile's gateway API listener — own port (8642),
              # key comes from the rendered env file (API_SERVER_KEY). Extra
              # profiles get their own ports the same way (8643, ...).
              "API_SERVER_ENABLED=true"
              "API_SERVER_HOST=0.0.0.0"
              "API_SERVER_PORT=8642"
              "HERMES_BUNDLED_SKILLS=${hermes-pkg}/share/hermes-agent/skills"
              "HERMES_BUNDLED_PLUGINS=${hermes-pkg}/share/hermes-agent/plugins"
              "HERMES_BUNDLED_LOCALES=${hermes-pkg}/share/hermes-agent/locales"
              "HERMES_OPTIONAL_MCPS=${hermes-pkg}/share/hermes-agent/optional-mcps"
              "HERMES_LAZY_INSTALL_TARGET=/var/lib/hermes/.hermes/lazy-packages"
            ];
            ExecStart = "${hermes-pkg}/bin/hermes gateway run";
            EnvironmentFile = [
              "/run/secrets/hermes/env"
              (envFileFor "hermes/sops-env")
            ];
          };
        };

        # Boot-safe one-time migration cleanup: purge remnants of the
        # hermes-CLI-managed gateway unit so they can't shadow or dangle
        # alongside the NixOS-managed one above. Pure filesystem ops (root),
        # no sudo/PAM — safe during boot-time activation.
        # No ordering against secret provisioning: this only removes stale unit
        # files and never reads a secret. It used to depend on `setupSecrets`
        # conditionally, which went dead the moment serenity moved to
        # sops.useSystemdActivation = true — that activation script no longer
        # exists, so the dep silently evaluated to []. Removed rather than left
        # as a line that looks like it orders against secrets but cannot.
        system.activationScripts."hermes-unit-cleanup" = ''
          rm -f /var/lib/hermes/.config/systemd/user/default.target.wants/hermes-gateway.service
          rm -f /var/lib/hermes/.config/systemd/user/hermes-agent.service
          rm -f /var/lib/hermes/.config/systemd/user/hermes-dashboard.service
          rm -rf /var/lib/hermes/.config/systemd/user/hermes-gateway.service.d
          rm -f /var/lib/hermes/.config/systemd/user/hermes-gateway.service
          rm -f /var/lib/hermes/.hermes/.managed
          # The env file is rendered by sops-nix into /run/secrets/rendered/ now.
          # The old hand-written copies are unmanaged leftovers: plaintext
          # secrets in the agent's home that nothing regenerates. Drop them.
          rm -f /var/lib/hermes/.hermes/sops-env
          rm -f /var/lib/hermes/.hermes/profiles/*/sops-env
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

        system.activationScripts."hermes-langfuse-alert" = lib.stringAfter [ "hermes-seed" ] ''
          mkdir -p /var/lib/hermes/.hermes/scripts
          cp ${./scripts/langfuse-error-alert.py} /var/lib/hermes/.hermes/scripts/langfuse-error-alert.py
          chmod 0700 /var/lib/hermes/.hermes/scripts/langfuse-error-alert.py
          chown hermes:hermes /var/lib/hermes/.hermes/scripts/langfuse-error-alert.py
        '';

        systemd.tmpfiles.rules = [
          "f /var/lib/systemd/linger/hermes 0644 root root - -"
        ];
      }
    ];
  };
}
