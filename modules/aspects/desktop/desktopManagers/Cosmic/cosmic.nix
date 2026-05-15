{ inputs, den, ... }:
{
  den.aspects.desktop.desktopManagers.cosmic = {
    nixos = { config, pkgs, ... }: {
      services.desktopManager.cosmic.enable = true;
      services.displayManager.cosmic-greeter.enable = true;
      services.displayManager.defaultSession = "cosmic";
      environment.cosmic.excludePackages = with pkgs; [
        # gcr_4
      ];
    };
  };
}