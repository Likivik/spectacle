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
    };
  };
}
