{ den, inputs, lib, pkgs, ... }: {
  flake-file.inputs = {
    nirimod = {
      url = "github:srinivasr/nirimod";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.desktop.desktopManagers.niri = {
    nixos = { config, pkgs, ... }: {
      programs.niri.enable = true;

      xdg.portal = {
        enable = true;
        extraPortals = with pkgs; [ xdg-desktop-portal-gtk xdg-desktop-portal-gnome xdg-desktop-portal-wlr xdg-desktop-portal-termfilechooser ];
      };

      environment.systemPackages = [
        inputs.nirimod.packages.${pkgs.stdenv.hostPlatform.system}.default
      ];
    };

    maid = { user, ... }: {
      file.xdg_config."niri".source = ./../../../../../modules/users/likivik/dotfiles/niri;
    };
  };
}
