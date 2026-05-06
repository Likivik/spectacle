{ inputs, den, ... }:
{
  den.aspects.remoteDesktops = {
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