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
        # Background (2026-09-07 serenity outage): Mullvad's kill-switch is a
        # policy-routing ladder (ip rules 5210/5230/5250/5270, fwmark 0x80000,
        # empty table 52) that blackholes ALL traffic while the tunnel is
        # down. That is correct behavior — but with no exemptions beyond the
        # tunnel itself, a no-internet boot deadlocks: daemon can't connect
        # (no internet) → kill-switch blocks everything → tailscale can't
        # even reach its bootstrap DERP servers → box unreachable. The
        # exemptions below (LAN, gateway, bootstrap DNS, tailscale, NTP)
        # keep recovery paths alive without un-VPNing user traffic.
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

        # Boot deadlock breaker: mullvad-early-boot-blocking holds ALL traffic
        # hostage until the tunnel is up. If the daemon can't connect (e.g.
        # router down at 03:00), the box stays bricked until hands touch it.
        # Allow a bounded window instead: daemon gets 90s to establish the
        # tunnel; if it fails, the blocker relents and the box boots with a
        # plain connection (Mullvad's own reconnect logic takes over later).
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
