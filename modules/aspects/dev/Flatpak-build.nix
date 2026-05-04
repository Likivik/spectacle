{ inputs, den, ... }:
{
  den.aspects.flatpakBuild = {
    nixos = { config, pkgs, lib, ... }: {
      environment.systemPackages = [ pkgs.flatpak-builder ];
    };
  };
}