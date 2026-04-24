{ config, pkgs, lib, ... }:

{
  virtualisation.containers.enable = true;


  #virtualisation.docker.enable = true;
  
  virtualisation.podman = 
  {
    enable = true;
    # Create a `docker` alias for podman, to use it as a drop-in replacement
    dockerCompat = true;
    # Required for containers under podman-compose to be able to talk to each other.
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

#dj

}