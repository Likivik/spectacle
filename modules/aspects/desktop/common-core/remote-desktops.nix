{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.remote-desktops = {
    nixos =
      { config, pkgs, ... }:
      {
        environment.systemPackages = with pkgs; [
          anydesk
          kdePackages.krdc
          gnome-connections
        ];
      };
  };
}