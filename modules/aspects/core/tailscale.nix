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

      networking.iproute2.rttablesExtraConfig = ''
        534 ts-bypass
      '';

      systemd.services.ensure-ts-fwmark-bypass = {
        description = "Ensure Tailscale fwmark bypass rule and route for Amnezia coexistence";
        before = [ "tailscaled.service" ];
        wantedBy = [ "multi-user.target" ];
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        serviceConfig.Type = "oneshot";
        script = ''
          ${pkgs.iproute2}/bin/ip rule add fwmark 0x534e table 534 2>/dev/null || true
          GW_DEV=$(${pkgs.iproute2}/bin/ip route show default | ${pkgs.gawk}/bin/awk '{print $5}')
          GW_IP=$(${pkgs.iproute2}/bin/ip route show default | ${pkgs.gawk}/bin/awk '{print $3}')
          if [ -n "$GW_DEV" ]; then
            ${pkgs.iproute2}/bin/ip route replace default via "$GW_IP" dev "$GW_DEV" table 534
          fi
        '';
      };

      networking.networkmanager.dispatcherScripts = lib.mkIf config.networking.networkmanager.enable [{
        source = pkgs.writeText "10-ts-fwmark" ''
          #!/bin/sh
          if [ "$2" = "up" ]; then
            GW_DEV=$(${pkgs.iproute2}/bin/ip route show default | ${pkgs.gawk}/bin/awk '{print $5}')
            GW_IP=$(${pkgs.iproute2}/bin/ip route show default | ${pkgs.gawk}/bin/awk '{print $3}')
            ${pkgs.iproute2}/bin/ip route replace default via "$GW_IP" dev "$GW_DEV" table 534
          fi
        '';
        type = "basic";
      }];
    };
  };
}
