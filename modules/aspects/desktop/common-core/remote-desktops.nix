{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.remote-desktops = {
    nixos =
      { config, pkgs, ... }:
      {
        environment.systemPackages = with pkgs; [
          kdePackages.krdc
          gnome-connections
        ];
      };
  };
}