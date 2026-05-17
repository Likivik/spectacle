{ inputs, den, ... }:
{
  den.aspects.kde-extras = {
    nixos = { config, pkgs, ... }: {
      environment.systemPackages = [
        #### Kwin Effects
        # inputs.kwin-effects-forceblur.packages.${pkgs.system}.default
        # kwin-effects-glass https://github.com/4v3ngR/kwin-effects-glass

        ##### Widgets
        pkgs.plasma-panel-colorizer
      ];
    };
  };
}