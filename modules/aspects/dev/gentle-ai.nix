{ inputs, den, ... }:
{
  den.aspects.gentle-ai = {
    nixos = { pkgs, ... }: {
      environment.systemPackages = [
        inputs.gentle-ai-nix.packages.${pkgs.system}.gentle-ai
        inputs.gentle-ai-nix.packages.${pkgs.system}.engram
      ];
    };
  };
}
