{ inputs, den, ... }:
{
  den.aspects.kde-darkly = {
    nixos = { config, pkgs, ... }: {
      environment.systemPackages = with pkgs; [
        darkly-qt5
        darkly
      ];
      qt.platformTheme = "qt6ct";
    };
  };
}