{ inputs, den, ... }:
{
  den.aspects.packageSources = {
    nixos = { config, pkgs, ... }: {
      nixpkgs.config = { allowUnfree = true; };

      services.flatpak.enable = true;

      xdg.portal = {
        enable = true;
        config = {
          common = {
            default = [ "kde" ];
            "org.freedesktop.impl.portal.Settings" = [ "kde;gtk" ];
          };
        };
        xdgOpenUsePortal = true;
      };

      programs.appimage = {
        enable = true;
        binfmt = true;
      };
    };
  };
}