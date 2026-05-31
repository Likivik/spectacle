{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.package-sources = {
    nixos =
      { config, pkgs, ... }:
      {
        nixpkgs.config = {
          allowUnfree = true;
        };

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
          extraPortals = with pkgs; [
            kdePackages.xdg-desktop-portal-kde
          ];
        };

        programs.appimage = {
          enable = true;
          binfmt = true;
        };
      };
  };
}
