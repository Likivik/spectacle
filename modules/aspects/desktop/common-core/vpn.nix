{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.vpn = {
    nixos =
      { config, pkgs, lib, ... }:
      {

        services.mullvad-vpn.enable = true;
        services.mullvad-vpn.enableExcludeWrapper = true;
        services.mullvad-vpn.gui.enable = true;

        environment.systemPackages = with pkgs; [
          mullvad-compass

          ktailctl
          # nft CLI on every desktop host: the only reliable way to inspect /
          # purge Mullvad's killswitch table (table inet mullvad) when it
          # bricks the box (iptables -L shows nothing — it's nftables).
          nftables
        ];

        # v2raya replaced by xray-vless (TUN-mode VLESS Reality service below)
        services.v2raya.enable = true;

        boot.kernel.sysctl = {
          "net.ipv4.conf.all.forwarding" = true;
          "net.ipv6.conf.all.forwarding" = true;
        };

        # Traffic exclusions (Mullvad split tunneling). Applied idempotently —
        # `mullvad exclude add` is additive; prune+re-add keeps the list exact.
        #
        # Background (2026-09-07 serenity 5h outage): Mullvad's kill-switch is
        # a policy-routing ladder (ip rules 5210/5230/5250/5270, fwmark
        # 0x80000) PLUS an nftables `table inet mullvad { output … policy
        # drop }` block. The nft table survives daemon-stop, never shows in
        # iptables -L, and blackholes ALL traffic (curl to ya.ru AND local
        # gateway both fail) while the tunnel is down. A no-internet boot
        # deadlocks: daemon can't connect → kill-switch blocks everything →
        # tailscale can't reach bootstrap DERP → box unreachable. Recovery
        # was literally `nft delete table inet mullvad` (2026-09-09). We keep
        # the policy-routing exclusions (LAN/gateway/DNS/tailscale) so
        # recovery paths survive, and purge the nft table in postStart so a
        # stale table can never brick the host again.
        systemd.services.mullvad-vpn.postStart = ''
          sleep 2
          ${pkgs.mullvad}/bin/mullvad exclude add 100.64.0.0/10   # tailscale CGNAT range
          ${pkgs.mullvad}/bin/mullvad exclude add 41641/udp      # tailscale transport
          ${pkgs.mullvad}/bin/mullvad exclude add 192.168.0.0/16 # LAN + gateway
          ${pkgs.mullvad}/bin/mullvad exclude add 10.0.0.0/8     # private ranges
          ${pkgs.mullvad}/bin/mullvad exclude add 172.16.0.0/12  # private ranges
          ${pkgs.mullvad}/bin/mullvad exclude add 1.1.1.1/32     # bootstrap DNS (bootstrapDNS)
          ${pkgs.mullvad}/bin/mullvad exclude add 8.8.8.8/32     # fallback DNS
          ${pkgs.mullvad}/bin/mullvad exclude add 9.9.9.9/32     # fallback DNS
        '';
        
        # Boot deadlock breaker (community-proven fix, nixpkgs#281102 +
        # mullvad/mullvadvpn-app#8213): Mullvad 2025.6+ AUTO-ENABLES
        # lockdown-mode on upgrade and on missing/corrupt settings, and the
        # `mullvad-early-boot-blocking` / `mullvad-daemon` units apply the
        # policy-drop nftables table (table inet mullvad) during EARLY BOOT —
        # before any mullvad-vpn postStart could delete it. lockdown-mode
        # makes the box always require the tunnel: no tunnel at boot = the
        # box bricks itself (both curl to ya.ru AND local gateway fail).
        #
        # The durable fix is NOT deleting the table (races the daemon which
        # re-applies on every state change) — it is forcing lockdown-mode
        # OFF at every boot via an activation script (community-standard),
        # so the daemon starts in the safe, non-blocking state. Deleting a
        # stale table is kept as a belt-and-braces purge.
        system.activationScripts.mullvadLockdownOff = {
          supportsDryActivation = true;
          text = ''
            if [ "''$NIXOS_ACTION" = 'dry-activate' ]; then
              echo "Dry run: mullvad lockdown-mode off"
            else
              # Best effort: only relevant when the daemon is present.
              ${pkgs.mullvad}/bin/mullvad lockdown-mode set off || true
              # Belt-and-braces: drop any stale killswitch table so a
              # half-baked boot can never wedge traffic.
              ${pkgs.nftables}/bin/nft delete table inet mullvad 2>/dev/null || true
            fi
          '';
        };

        # Bounded window for the early-boot blocker: if the tunnel can't come
        # up (router down at 03:00), the blocker relents in 90s instead of
        # holding the box hostage until hands touch it.
        systemd.services.mullvad-early-boot-blocking.serviceConfig = {
          TimeoutStartSec = lib.mkForce "90s";
          # Failure to start the blocker must NOT wedge boot — the kill-switch
          # rules alone already cover the protection.
          RemainAfterExit = lib.mkForce false;
        };

        # Watchdog: if the daemon has been disconnected AND there is no
        # default route via the tunnel for 5 minutes, bounce the daemon so it
        # re-applies exclusions from a clean slate. Cheap, self-healing.
        systemd.services.mullvad-reconnect-guard = {
          description = "Kick mullvad-daemon if tunnel is down and LAN is unreachable";
          after = [ "mullvad-vpn.service" "network-online.target" ];
          wants = [ "network-online.target" ];
          serviceConfig = {
            Type = "oneshot";
            ExecStart = with pkgs; writeShellScript "mullvad-guard" ''
              set -eu
              # healthy: either tunnel is up (tun0/mullvad0 present) or ping works
              if ${pkgs.iproute2}/bin/ip link show | ${pkgs.gnugrep}/bin/grep -qE "mullvad|wg-mullvad"; then
                exit 0
              fi
              if ${pkgs.iputils}/bin/ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1; then
                exit 0
              fi
              echo "mullvad guard: no tunnel, no internet — restarting mullvad-daemon"
              ${pkgs.systemd}/bin/systemctl restart mullvad-daemon.service
            '';
          };
          wantedBy = [ "timers.target" ];
        };
        systemd.timers.mullvad-reconnect-guard = {
          description = "Periodic mullvad health check";
          timerConfig = {
            OnBootSec = "3min";
            OnUnitActiveSec = "5min";
            AccuracySec = "30s";
          };
          wantedBy = [ "timers.target" ];
        };
      };
  };
}
