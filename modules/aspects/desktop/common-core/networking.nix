{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.networking = {
    nixos =
      { config, pkgs, ... }:
      {
        networking.networkmanager = {
          enable = true;
          wifi.powersave = false;
          plugins = [
            pkgs.networkmanager-l2tp
          ];
        };

      };
  };
}