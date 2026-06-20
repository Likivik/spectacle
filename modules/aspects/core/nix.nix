{ inputs, den, lib, ... }:
{
  den.aspects.core.nix = {
    nixos = { config, pkgs, ... }: {
      system.stateVersion = "25.11"; # set Nixpkgs version you start with, never change for proper backward compatability
      nixpkgs.config.allowUnfree = true; # allow unfree packages
      nix.settings.experimental-features = [ "nix-command" "flakes" ]; # enable flakes & new nix cli
      nix.settings.extra-substituters = [
        "https://nix-community.cachix.org"
        "https://mirror.sjtu.edu.cn/nix-channels/store"
        "https://mirrors.ustc.edu.cn/nix-channels/store"
        "https://mirrors.tuna.tsinghua.edu.cn/nix-channels/store"
      ];
      nix.settings.trusted-public-keys = [
        "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
      ];
      nix.optimise = {
        automatic = true;
        dates = [ "03:45" ];
      };
      nix.settings.max-substitution-jobs = 64;
      nix.settings.http-connections = 64;

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