{ inputs, den, ... }:
{
  den.aspects.flatpak-build = {
    nixos = { config, pkgs, lib, ... }: {
      environment.systemPackages = [ pkgs.flatpak-builder ];
    };
  };
}