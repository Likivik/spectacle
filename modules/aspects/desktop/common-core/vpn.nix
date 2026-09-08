{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.vpn = {
    nixos =
      { config, pkgs, lib, ... }:
      {

        # ── Mullvad VPN: DISABLED (2026-09-09) ────────────────────────────
        #
        # Root cause, confirmed from the mullvad-daemon journal:
        #   Whenever the daemon cannot reach a relay — which is ALWAYS here,
        #   since RU blocks Mullvad's relays — it re-applies its kill-switch:
        #   policy-routing rules (fwmark 0x80000, priorities
        #   5210/5230/5250/5270) PLUS an nftables
        #   `table inet mullvad { chain output … policy drop }`.
        #
        #   That nft table survives `systemctl stop mullvad-daemon` and is
        #   invisible to `iptables -L` (it is nftables). It blackholes ALL
        #   traffic — curl, DNS, and even the local gateway. With no tunnel
        #   the box deadlocks: daemon can't connect → kill-switch drops
        #   everything → tailscale can't reach bootstrap DERP → host
        #   unreachable until hands delete the table.
        #
        #   The activation-script purge (removed below) only fired ONCE per
        #   boot; the daemon's ~5-minute retry loop re-created the table
        #   every time, so "boot with no internet" recurred on every reboot.
        #
        # Durable fix: disable the daemon outright. No daemon → no
        # kill-switch table → no self-bricking. For egress use a tailscale
        # exit node (ktailctl is installed).
        services.mullvad-vpn.enable = false;
        # services.mullvad-vpn.enableExcludeWrapper = true;
        # services.mullvad-vpn.gui.enable = true;

        environment.systemPackages = with pkgs; [
          # nft CLI stays on every desktop host: it is the only reliable way
          # to inspect / purge a stale Mullvad kill-switch table
          # (`nft delete table inet mullvad`) if one ever reappears.
          nftables

          ktailctl
        ];

        # v2raya replaced by xray-vless (TUN-mode VLESS Reality service below)
        services.v2raya.enable = true;

        boot.kernel.sysctl = {
          "net.ipv4.conf.all.forwarding" = true;
          "net.ipv6.conf.all.forwarding" = true;
        };

        # ── All Mullvad daemon wiring below is commented out together with
        #    the daemon itself (2026-09-09). Kept verbatim for reference if
        #    Mullvad is ever re-enabled with a relay that actually reaches.
        #
        # # Traffic exclusions (Mullvad split tunneling). Applied
        # # idempotently — `mullvad exclude add` is additive; prune+re-add
        # # keeps the list exact.
        # systemd.services.mullvad-vpn.postStart = ''
        #   sleep 2
        #   ${pkgs.mullvad}/bin/mullvad exclude add 100.64.0.0/10   # tailscale CGNAT range
        #   ${pkgs.mullvad}/bin/mullvad exclude add 41641/udp      # tailscale transport
        #   ${pkgs.mullvad}/bin/mullvad exclude add 192.168.0.0/16 # LAN + gateway
        #   ${pkgs.mullvad}/bin/mullvad exclude add 10.0.0.0/8     # private ranges
        #   ${pkgs.mullvad}/bin/mullvad exclude add 172.16.0.0/12  # private ranges
        #   ${pkgs.mullvad}/bin/mullvad exclude add 1.1.1.1/32     # bootstrap DNS (bootstrapDNS)
        #   ${pkgs.mullvad}/bin/mullvad exclude add 8.8.8.8/32     # fallback DNS
        #   ${pkgs.mullvad}/bin/mullvad exclude add 9.9.9.9/32     # fallback DNS
        # '';
        #
        # # Boot deadlock breaker: Mullvad 2025.6+ auto-enables lockdown-mode
        # # on upgrade / on missing settings, and the `mullvad-early-boot-
        # # blocking` / `mullvad-daemon` units apply the policy-drop nftables
        # # table during EARLY BOOT — before any postStart could delete it.
        # system.activationScripts.mullvadLockdownOff = {
        #   supportsDryActivation = true;
        #   text = ''
        #     if [ "''$NIXOS_ACTION" = 'dry-activate' ]; then
        #       echo "Dry run: mullvad lockdown-mode off"
        #     else
        #       ${pkgs.mullvad}/bin/mullvad lockdown-mode set off || true
        #       ${pkgs.nftables}/bin/nft delete table inet mullvad 2>/dev/null || true
        #     fi
        #   '';
        # };
        #
        # # Bounded window for the early-boot blocker so a router outage can
        # # never hold the box hostage until hands touch it.
        # systemd.services.mullvad-early-boot-blocking.serviceConfig = {
        #   TimeoutStartSec = lib.mkForce "90s";
        #   RemainAfterExit = lib.mkForce false;
        # };
        #
        # # Watchdog: bounce the daemon if disconnected AND no tunnel route.
        # systemd.services.mullvad-reconnect-guard = {
        #   description = "Kick mullvad-daemon if tunnel is down and LAN is unreachable";
        #   after = [ "mullvad-vpn.service" "network-online.target" ];
        #   wants = [ "network-online.target" ];
        #   serviceConfig = {
        #     Type = "oneshot";
        #     ExecStart = with pkgs; writeShellScript "mullvad-guard" ''
        #       set -eu
        #       if ${pkgs.iproute2}/bin/ip link show | ${pkgs.gnugrep}/bin/grep -qE "mullvad|wg-mullvad"; then
        #         exit 0
        #       fi
        #       if ${pkgs.iputils}/bin/ping -c 1 -W 3 1.1.1.1 >/dev/null 2>&1; then
        #         exit 0
        #       fi
        #       echo "mullvad guard: no tunnel, no internet — restarting mullvad-daemon"
        #       ${pkgs.systemd}/bin/systemctl restart mullvad-daemon.service
        #     '';
        #   };
        #   wantedBy = [ "timers.target" ];
        # };
        # systemd.timers.mullvad-reconnect-guard = {
        #   description = "Periodic mullvad health check";
        #   timerConfig = {
        #     OnBootSec = "3min";
        #     OnUnitActiveSec = "5min";
        #     AccuracySec = "30s";
        #   };
        #   wantedBy = [ "timers.target" ];
        # };
      };
  };
}
