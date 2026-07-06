{ inputs, den, ... }:
{
  den.aspects.core.tailscale = {
    nixos = { config, pkgs, lib, ... }: {
      services.tailscale.enable = true;
      services.tailscale.useRoutingFeatures = "both";
      services.tailscale.extraUpFlags = [
        "--operator=likivik"
        "--accept-routes=true"
        "--fwmark=0x534e"
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
          GW_DEV=$(ip route show default | awk '{print $5}')
          GW_IP=$(ip route show default | awk '{print $3}')
          ip rule add fwmark 0x534e table ts-bypass 2>/dev/null || true
          ip route replace default via "$GW_IP" dev "$GW_DEV" table ts-bypass
        '';
      };

      networking.networkmanager.dispatcherScripts = lib.mkIf config.networking.networkmanager.enable [{
        source = pkgs.writeText "10-ts-fwmark" ''
          #!/bin/sh
          if [ "$2" = "up" ]; then
            GW_DEV=$(ip route show default | awk '{print $5}')
            GW_IP=$(ip route show default | awk '{print $3}')
            ip route replace default via "$GW_IP" dev "$GW_DEV" table ts-bypass
          fi
        '';
        type = "basic";
      }];
    };
  };
}
