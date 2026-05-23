{ den, inputs, lib, pkgs, ... }:

{
  flake-file.inputs = {
    noctalia = {
      url = "github:noctalia-dev/noctalia-shell/v5";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.desktop.desktopManagers.noctalia = {
    nixos = { config, pkgs, ... }: {
      nix.settings = {
        extra-substituters = [ "https://noctalia.cachix.org" ];
        extra-trusted-public-keys = [
          "noctalia.cachix.org-1:pCOR47nnMEo5thcxNDtzWpOxNFQsBRglJzxWPp3dkU4="
        ];
      };
      environment.systemPackages = [
        inputs.noctalia.packages.${pkgs.stdenv.hostPlatform.system}.default
      ];
      
      programs.niri.enable = true;

      /* --------------------------- Screensharing -------------------------- */
      xdg.portal = {
        enable = true;
        extraPortals = with pkgs; [ xdg-desktop-portal-gtk xdg-desktop-portal-gnome xdg-desktop-portal-wlr xdg-desktop-portal-termfilechooser ];
      };
      
      # Noctalia asks to make sure these are enabled
      networking.networkmanager.enable = lib.mkDefault true;
      hardware.bluetooth.enable = lib.mkDefault true;
      services.tuned.enable = lib.mkDefault true;
      services.upower.enable = lib.mkDefault true;

      services.displayManager.gdm = {
        enable = true;
      };
      services.displayManager.defaultSession = "niri";

      services.gnome.gnome-keyring.enable = true;

      # Enable polkit for password/privilege elevation
      security.polkit.enable = true;
    };

    maid = { user, ... }: {
      file.xdg_config."noctalia".source =
        "{{home}}/nixos-config/modules/users/likivik/dotfiles/noctalia";
      file.xdg_config."niri".source =
        "{{home}}/nixos-config/modules/users/likivik/dotfiles/niri";
    };
  };
}
