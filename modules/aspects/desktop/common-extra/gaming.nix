{ inputs, den, ... }:
{
  den.aspects.desktop.common-extra.gaming = {
    nixos =
      { config, pkgs, ... }:
      {
        # hardware.graphics.enable32Bit = true;

        environment.systemPackages = with pkgs; [
          bottles
        ];
      };
  };
}