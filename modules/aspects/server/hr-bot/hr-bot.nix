{ den, pkgs, lib, ... }:

# HR hiring funnel bot (aiogram) — the "Менеджер проекта «Счётчики тепла»"
# onboarding bot. Reads the 3-question funnel (pay → exp → contact), logs
# candidates to /var/lib/hr-bot/candidates.jsonl.
#
# Previously a hand-rolled systemd-run transient unit on a /tmp venv — the
# venv got wiped by tmpfiles and the stale process crashed on every update
# with `No module named 'concurrent.futures.thread'` (Python 3.13 removed it;
# aiogram's asyncio to_thread still references it). This module makes it
# decla>rative and durable:
#   - venv on python3.12 (3.13+ is broken for aiogram here), built in
#     StateDirectory on first start, idempotent marker file
#   - token via EnvironmentFile → the existing hiring sops-env (0600 hermes)
#   - service survives reboot and tmpfs cleanup (no /tmp dependency)
{
  den.aspects.server.hr-bot = {
    nixos = { config, lib, pkgs, ... }:

    let
      botSrc = ../../../../pkgs/hr-bot/hr_bot.py;
      engSrc = ../../../../pkgs/hr-bot/engine.py;
      botVenv = "/var/lib/hr-bot/venv";
      # hr_bot.py `import engine` — both must sit in ONE dir on sys.path.
      # Copy them into the store at build time so the running cwd (/) and the
      # venv interpreter both resolve it; botDir contains engine.py alongside.
      botDir = pkgs.runCommand "hr-bot-src" { } ''
        mkdir -p $out
        cp ${botSrc} $out/hr_bot.py
        cp ${engSrc} $out/engine.py
        chmod +x $out/hr_bot.py
      '';

      # Build the aiogram venv idempotently (recreate when src or marker moves).
      startScript = pkgs.writeShellScript "hr-bot-start" ''
        set -eu
        if [ ! -x "${botVenv}/bin/python" ] || [ "${botVenv}/.installed" -ot "${botDir}/hr_bot.py" ]; then
          echo "Creating hr-bot venv (python3.12)..."
          ${pkgs.python312}/bin/python3.12 -m venv ${botVenv}
          ${botVenv}/bin/pip install --quiet --upgrade pip
          ${botVenv}/bin/pip install --quiet "aiogram>=3,<4"
          touch ${botVenv}/.installed
        fi
        exec ${botVenv}/bin/python ${botDir}/hr_bot.py
      '';
    in {
      # /var/lib/hr-bot must be hermes-owned end-to-end. The dir from
      # StateDirectory is created 0755 hermes, but files migrated from the
      # old root-owned transient unit (candidates.jsonl, state/*.json) come
      # in as root:root 644 — the bot (User=hermes) then fails the append
      # with PermissionError, silently dropping the candidate card (the
      # notify() after the write never runs). Fix both ways:
      #   - `Z` tmpfile recurses and re-owns existing files on boot;
      #   - preStart re-owns right before first exec (covers in-place restarts).
      systemd.tmpfiles.rules = [
        "d /var/lib/hr-bot 0700 hermes hermes -"
        "Z /var/lib/hr-bot 0700 hermes hermes -"
      ];

      systemd.services.hr-bot = {
        description = "HR hiring funnel bot (aiogram)";
        after = [ "network.target" ];
        wantedBy = [ "multi-user.target" ];

        preStart = ''
          chown -R hermes:hermes /var/lib/hr-bot || true
        '';

        environment = {
          HOME = "/var/lib/hr-bot";
        };

        serviceConfig = {
          Type = "simple";
          Restart = "on-failure";
          RestartSec = "10s";
          # Bound a crash/bad-token loop so systemd surfaces `failed` instead
          # of burning CPU; and a sane stop deadline so deploy switches fast.
          StartLimitIntervalSec = "60s";
          StartLimitBurst = 10;
          TimeoutStopSec = "30s";
          KillMode = "mixed";
          OOMPolicy = "stop";
          StateDirectory = "hr-bot";
          StateDirectoryMode = "0700";
          User = "hermes";
          Group = "hermes";
          # Best-effort hardening for a network-facing python interpreter.
          NoNewPrivileges = true;
          ProtectSystem = "strict";
          ProtectHome = "tmpfs";
          PrivateTmp = true;
          RestrictAddressFamilies = [ "AF_INET" "AF_INET6" "AF_UNIX" ];
          ReadWritePaths = [ "/var/lib/hr-bot" ];
          ExecStart = startScript;
          # Bot token from sops (declared in the host module).
          EnvironmentFile = config.sops.secrets."hermes/hr-bot-token".path;
        };
      };
    };
  };
}
