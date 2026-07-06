{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.vpn = {
    nixos =
      { config, pkgs, lib, ... }:
      let
        # Three-way source selector for amnezia-vpn:
        #   "unstable" → main nixpkgs input (nixos-unstable, no overlay applied). DEFAULT.
        #   "master"   → inputs.nixpkgs-master (latest in nixpkgs master branch).
        #   "local"    → locally pinned source (see amneziaSrc below).
        #
        # When a new upstream release appears before nixpkgs packages it:
        #   1. Switch to "local"
        #   2. Bump `tag` and recompute hash:
        #      nix run nixpkgs#nix-prefetch-github -- --fetch-submodules \
        #        --rev <new-tag> --nix amnezia-vpn amnezia-client
        #   3. Patch the SRI hash below, switch, test
        #   4. When upstream catches up, flip back to "unstable"
        vpnFallback = pkgs.callPackage ../../../../pkgs/vpn-fallback { };
        amneziaSource = "local";
        amneziaSrc = pkgs.fetchFromGitHub {
          owner = "amnezia-vpn";
          repo = "amnezia-client";
          tag = "4.8.19.0";
          hash = "sha256-kftLofCyLA6DDfEXRPyy6Zx0JiQUEzpdYpTlvPihPZg=";
          fetchSubmodules = true;
        };
      in
      {
        nixpkgs.overlays =
          lib.optional (amneziaSource == "master") (final: prev: {
            amnezia-vpn = inputs.nixpkgs-master.legacyPackages.${pkgs.system}.amnezia-vpn;
          })
           ++ lib.optional (amneziaSource == "local") (final: prev: {
            amnezia-vpn = prev.amnezia-vpn.overrideAttrs (old: {
              version = "4.8.19.0";
              src = amneziaSrc;
              # wrapGAppsHook4 removed — file-chooser portal routing handles it
            });
          });

        programs.amnezia-vpn.enable = true;

        services.mullvad-vpn.enable = true;
        services.mullvad-vpn.enableExcludeWrapper = true;
        services.mullvad-vpn.package = pkgs.mullvad-vpn;

        environment.systemPackages = with pkgs; [
          mullvad-compass

          ktailctl

          calyx-vpn
          riseup-vpn
          mozillavpn
          proton-vpn

          vpnFallback
          byedpi
          xray   # VLESS Reality engine (TUN-mode, managed via vpn-fallback v2ray)
        ];

         # v2raya replaced by xray-vless (TUN-mode VLESS Reality service below)
         # services.v2raya.enable = true;

         systemd.tmpfiles.rules = [
           "d /opt/vless 0700 root root - -"
         ];

         systemd.services.xray-vless = {
           description = "xray-core VLESS Reality tunnel (TUN mode)";
           after = [ "network-online.target" ];
           wants = [ "network-online.target" ];
           # NOT in wantedBy — manual start via vpn-fallback dispatcher
           serviceConfig = {
             Type = "simple";
             User = "root";
             ExecStartPre =
               "${pkgs.bash}/bin/bash -ec 'if [ ! -f /opt/vless/config.json ]; then echo \"no /opt/vless/config.json — create from secrets/vless/config.template.json\" >&2; exit 1; fi; if head -1 /opt/vless/config.json | grep -q \"^sops$\" && command -v sops >/dev/null 2>&1; then ${pkgs.sops}/bin/sops decrypt /opt/vless/config.json > /run/secrets/vless-config.json; else cp /opt/vless/config.json /run/secrets/vless-config.json; fi'";
             ExecStart = "${pkgs.xray}/bin/xray run -c /run/secrets/vless-config.json";
             Restart = "on-failure";
             RestartSec = "5s";
             LimitNOFILE = "infinity";
           };
         };

        services.zapret = {
          enable = true;
          configureFirewall = true;
          # set from blockcheck output (ran on traversal 2026-07-03)
          params = [
            "--dpi-desync=hostfakesplit"
            "--dpi-desync-ttl=7"
          ];
        };
        # Keep the unit and firewall rules available for vpn-fallback
        # but don't auto-start at boot — managed manually via `vpn-fallback zapret on/off`
        systemd.services.zapret.wantedBy = lib.mkForce [ ];

        # ── L2TP + AmneziaVPN coexistence ────────────────────────────────────
        # AmneziaVPN installs two routes that together cover ALL IPv4:
        #   0.0.0.0/1  dev amn0  metric 1    (covers 0.0.0.0 – 127.255.255.255)
        #   128.0.0.0/1 dev amn0  metric 1    (covers 128.0.0.0 – 255.255.255.255)
        # Everything — including the L2TP gateway (46.148.234.215) and our RDP
        # target (10.1.1.104) — gets stuffed into the Amnezia tunnel.
        #
        # We beat this with Linux's longest-prefix-match rule: a /32 or /24
        # route is *more specific* than a /1, so the kernel prefers it regardless
        # of metric. We just need to make sure those specific routes stay in the
        # table. The problem: Amnezia's client flushes routes when it starts or
        # reconnects, silently removing our entries.
        #
        # Solution: an NM dispatcher that re-asserts both routes on NM events
        # (up, vpn-up, vpn-down), replacing the old polling timer.
        #   ┌─ Route                                ─ Why we need it ────────
        #   │ 46.148.234.215/32 via WiFi gateway    L2TP/IPsec handshake must
        #   │                                       reach the server directly,
        #   │                                       not enter the Amnezia tunnel
        #   │ 10.1.1.0/24 dev ppp*                  RDP traffic must go through
        #   │                                       the L2TP tunnel's ppp interface
        networking.networkmanager.dispatcherScripts = lib.mkIf config.networking.networkmanager.enable [{
          source = pkgs.writeText "10-l2tp-bypass" ''
            #!/bin/sh
            case "$2" in
              up|vpn-up|vpn-down)
                GW_DEV=$(${pkgs.iproute2}/bin/ip route show default 0.0.0.0/0 | ${pkgs.gnugrep}/bin/grep -v -E 'dev (ppp|tun|tap|amn)' | ${pkgs.coreutils}/bin/head -1 | ${pkgs.gawk}/bin/awk '{print $3, $5}')
                set -- $GW_DEV
                GW=$1 DEV=$2
                if [ -n "$GW" ] && [ -n "$DEV" ]; then
                  ${pkgs.iproute2}/bin/ip route replace 46.148.234.215/32 via "$GW" dev "$DEV"
                fi

                for pppdev in $(${pkgs.iproute2}/bin/ip link show | ${pkgs.gnugrep}/bin/grep -oP 'ppp\d+'); do
                  ${pkgs.iproute2}/bin/ip route replace 10.1.1.0/24 dev "$pppdev"
                done
                ;;
            esac
          '';
          type = "basic";
        }];

         # boot.kernel.sysctl = {
        #   "net.ipv4.conf.all.forwarding" = true;
        #   "net.ipv6.conf.all.forwarding" = true;
        # };

        # # Exclude Tailscale traffic from Mullvad to prevent routing loops
        # systemd.services.mullvad-vpn.postStart = ''
        #   sleep 2
        #   ${pkgs.mullvad-vpn}/bin/mullvad exclude add 100.64.0.0/10
        #   ${pkgs.mullvad-vpn}/bin/mullvad exclude add 41641/udp
        # '';
      };
  };
}

/*
  ── Diagnostics: L2TP + AmneziaVPN ──────────────────────────────────────────

  The two routes this service maintains:

    ip route get 46.148.234.215    → should show "via 192.168.0.1 dev wlo1"
                                     (bypasses Amnezia, reaches L2TP server)
    ip route get 10.1.1.104        → should show "dev ppp0" or "dev ppp1"
                                     (goes through the L2TP tunnel to RDP target)

  Health checks:

    systemctl status ensure-l2tp-bypass.service   # active (exited)
    systemctl status ensure-l2tp-bypass.timer     # active (waiting)
    journalctl -u ensure-l2tp-bypass.service      # check logs on failure

  Rebuild:

    sudo nixos-rebuild switch

  If RDP stops working after Amnezia reconnects, wait ≤2 min for the timer
  to re-assert both routes. If it doesn't recover, trigger manually:

    sudo systemctl start ensure-l2tp-bypass.service
    ip route get 46.148.234.215
    ip route get 10.1.1.104

  See also: https://den.denful.com/
*/
