{ inputs, den, ... }:
{
  den.aspects.shell-commands = {
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