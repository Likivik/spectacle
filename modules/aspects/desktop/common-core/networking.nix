{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.networking = {
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