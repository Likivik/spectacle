 
{ config, pkgs, ... }:
{

  nix.settings.experimental-features = [ "nix-command" "flakes" ]; # Flakes -> Enable

  nix.optimise.automatic = true;
  nix.optimise.dates = [ "03:45" ]; # Optional; allows customizing optimisation schedule


  # NH is a modern helper utility that aims to consolidate and reimplement
  # some of the commands from various tools within the NixOS ecosystem. 
  programs.nh = {
    enable = true;
    clean.enable = true;
    clean.extraArgs = "--keep-since 356d --keep 30";
    flake = "/Storage/Git/Nixos"; # sets NH_OS_FLAKE variable for you
  };

}
