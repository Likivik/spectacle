{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.remoteDesktops = {
    nixos =
      { config, pkgs, ... }:
      {
        environment.systemPackages = with pkgs; [
          anydesk
          remmina
        ];
      };
  };
}