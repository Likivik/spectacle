{ inputs, den, ... }:
{
  den.aspects.networking = {
    nixos =
      { config, pkgs, ... }:
      {
        networking.networkmanager = {
          enable = true;
          plugins = [
            pkgs.networkmanager-l2tp
          ];
        };

      };
  };
}