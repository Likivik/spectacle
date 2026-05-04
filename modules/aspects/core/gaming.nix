{ inputs, den, ... }:
{
  den.aspects.gaming = {
    nixos =
      { config, pkgs, ... }:
      {
        hardware.graphics.enable32Bit = true;

        environment.systemPackages = with pkgs; [
          bottles
        ];
      };
  };
}