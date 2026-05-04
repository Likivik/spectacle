{ inputs, den, ... }:
{
  den.aspects.android = {
    nixos = { config, pkgs, ... }: {
      environment.systemPackages = [ pkgs.android-tools ];
    };
  };
}