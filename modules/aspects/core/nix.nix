{ inputs, den, ... }:
{
  den.aspects.nix = {
    nixos = { config, pkgs, ... }: {
      system.stateVersion = "25.11"; # set Nixpkgs version you start with, never change for proper backward compatability
      nixpkgs.config.allowUnfree = true; # allow unfree packages
      nix.settings.experimental-features = [ "nix-command" "flakes" ]; # enable flakes & new nix cli
      nix.optimise = {
        automatic = true;
        dates = [ "03:45" ];
      };

      programs.nh = {
        enable = true;
        clean = {
          enable = true;
          extraArgs = "--keep-since 356d --keep 30";
        };
        # flake = "/Storage/Git/Nixos";
      };
    };
  };
}