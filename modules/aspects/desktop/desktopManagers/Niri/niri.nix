{ den, inputs, lib, pkgs, ... }: {
  flake-file.inputs = {
    nirimod = {
      url = "github:srinivasr/nirimod";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    niri-float-sticky = {
      url = "github:probeldev/niri-float-sticky";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.desktop.desktopManagers.niri = {
    nixos = { config, pkgs, ... }: {
      programs.niri.enable = true;

      services.keyd.enable = true;
      environment.etc."keyd/default.conf".source =
        ../../../../../modules/users/likivik/dotfiles/keyd/default.conf;

xdg.portal = {
         enable = true;
         config.common."org.freedesktop.impl.portal.FileChooser" = [ "kde" ];
         extraPortals = with pkgs; [ xdg-desktop-portal-wlr ];
         configPackages = [ pkgs.kdePackages.xdg-desktop-portal-kde ];
       };

      environment.sessionVariables = {
        QT_QPA_PLATFORMTHEME = "qt6ct";
        QT_QPA_PLATFORMTHEME_QT6 = "qt6ct";
        GTK_USE_PORTAL = "1";
      };

      environment.systemPackages = [
        inputs.nirimod.packages.${pkgs.stdenv.hostPlatform.system}.default
        inputs.niri-float-sticky.packages.${pkgs.stdenv.hostPlatform.system}.default
      ];
    };

    maid = { user, ... }: {
      file.xdg_config."niri".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/niri";
    };
  };
}
