{ inputs, den, ... }:
{
  den.aspects.shellCommands = {
    nixos = { config, pkgs, ... }: {
      environment.systemPackages = with pkgs; [
        killall
        # unzip
        # unrar
        # unar
        # yazi
        # bat
        # eza
      ];
    };
  };
}