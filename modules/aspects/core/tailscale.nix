{ inputs, den, ... }:
{
  den.aspects.core.tailscale = {
    nixos = { ... }: {
      services.tailscale.enable = true;
      services.tailscale.useRoutingFeatures = "both";
      services.tailscale.extraUpFlags = [
        "--operator=$USER"
        "--accept-routes=true"
      ];
    };
  };
}
