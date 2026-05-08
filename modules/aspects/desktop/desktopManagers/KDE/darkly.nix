{ inputs, den, ... }:
{
  den.aspects.kdeDarkly = {
    nixos = { config, pkgs, ... }: {
      environment.systemPackages = with pkgs; [
        darkly-qt5
        darkly
      ];
      qt.platformTheme = "qt6ct";
    };
  };
}