{ inputs, den, ... }:
{
  den.aspects.nix = {
    nixos = { config, pkgs, ... }: {
      nix.settings.experimental-features = [ "nix-command" "flakes" ];

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
        flake = "/Storage/Git/Nixos";
      };
    };
  };
}