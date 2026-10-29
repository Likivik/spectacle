{ inputs, den, ... }:
{
  den.aspects.core.tailscale = {
    nixos = { config, pkgs, lib, ... }: {
      services.tailscale.enable = true;
      services.tailscale.useRoutingFeatures = "both";
      services.tailscale.extraUpFlags = [
        "--operator=likivik"
        "--accept-routes=true"
      ];

      # `tailscale serve` and `tailscale set` exit 1 while the backend is still
      # NoState/Starting, and oneshots that call them have nothing to retry
      # them. Measured 2026-10-29 on poweredge: at boot the backend sat in
      # NoState for over a minute, tailscale-serve failed, and the tailnet HTTPS
      # endpoints stayed dead until the unit was restarted by hand. Anything
      # tailscale-dependent must wait for a Running backend first:
      #
      #   systemd.services.<name>.serviceConfig.ExecStartPre =
      #     "${config.systemd.package}/bin/systemctl is-active --quiet tailscaled";
      #   systemd.services.<name>.script = "tailscale-wait-running\n" + ...;
      #
      # Fleet-wide because every host includes this aspect (via core,
      # desktop.common-core or server.core).
      environment.systemPackages = [
        (pkgs.writeShellScriptBin "tailscale-wait-running" ''
          # No tailscaled (CI eval, VM tests, units copied to a guest): skip
          # cleanly. Exiting non-zero here would turn every such host into a
          # restart loop for a unit that is simply not applicable.
          if ! ${config.systemd.package}/bin/systemctl is-active --quiet tailscaled; then
            echo "tailscale-wait-running: tailscaled is not active, skipping" >&2
            exit 0
          fi
          tries="''${TAILSCALE_WAIT_TRIES:-15}"
          i=0
          while [ "$i" -lt "$tries" ]; do
            state=$(${lib.getExe pkgs.tailscale} status --json 2>/dev/null \
              | ${pkgs.gnused}/bin/sed -n 's/.*"BackendState": *"\([A-Za-z]*\)".*/\1/p')
            if [ "$state" = "Running" ]; then exit 0; fi
            ${pkgs.coreutils}/bin/sleep 2
            i=$((i + 1))
          done
          # Bounded on purpose: this runs inside a unit that the boot target
          # waits for, so an unbounded wait turns "tailnet is down" into "boot
          # never completes" — measured 2026-10-29 in the poweredge VM smoke,
          # where a guest with a dummy auth key sat in NeedsLogin forever and the
          # gate reported `boot: system state is 'starting'`.
          echo "tailscale-wait-running: backend not Running after $((tries * 2))s — skipping" >&2
          exit 0
        '')
      ];
    };
  };
}
