{ inputs, den, ... }:
{
  den.aspects.docker = {
    nixos = { config, pkgs, lib, ... }: {
      virtualisation.containers.enable = true;

      virtualisation.podman = {
        enable = true;
        dockerCompat = true;
        defaultNetwork.settings.dns_enabled = true;
      };

      environment.systemPackages = [
        pkgs.distrobox
        pkgs.boxbuddy
        pkgs.podman-desktop
        pkgs.podman-compose
        pkgs.podman-tui
        pkgs.pods
        pkgs.buildah
      ];
    };
  };
}