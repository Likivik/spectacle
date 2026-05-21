{ den, inputs, pkgs, ... }:

{
  flake-file.inputs = {
    noctalia = {
      url = "github:noctalia-dev/noctalia-shell/v5";
    };
  };

  den.aspects.desktop.desktopManagers.noctalia = {
    nixos = { config, pkgs, ... }: {
      nix.settings = {
        extra-substituters = [ "https://noctalia.cachix.org" ];
        extra-trusted-public-keys = [
          "noctalia.cachix.org-1:pCOR47nnMEo5thcxNDtzWpOxNFQsBRglJzxWPp3dkU4="
        ];


        # Noctalia asks to make sure these are enabled
        networking.networkmanager.enable = true;
        hardware.bluetooth.enable = true;
        services.tuned.enable = true;
        services.upower.enable = true;
      };

      environment.systemPackages = [
        inputs.noctalia.packages.${pkgs.stdenv.hostPlatform.system}.default
      ];

      /* --------------------------- Screensharing -------------------------- */
      xdg.portal = {
        enable = true;
        extraPortals = with pkgs; [ xdg-desktop-portal-wlr xdg-desktop-portal-termfilechooser ];
      };
    };

    maid = { user, ... }: {
      file.xdg_config."noctalia".source =
        "{{home}}/nixos-config/modules/users/likivik/dotfiles/noctalia";
      file.xdg_config."niri".source =
        "{{home}}/nixos-config/modules/users/likivik/dotfiles/niri";
    };
  };
}
