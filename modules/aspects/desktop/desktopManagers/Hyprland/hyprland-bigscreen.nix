{ den, inputs, ... }:
{

  den.default.desktop.desktopManagers.includes = [ den._.inputs' ];

  flake-file.inputs = {
    hyprland.url = "github:hyprwm/Hyprland/v0.52.0";
    hyprland-plugins.url = "github:hyprwm/hyprland-plugins/v0.52.0";
    hy3.url = "github:outfoxxed/hy3/hl0.52.0";
    hypr-dynamic-cursors.url = "github:VirtCode/hypr-dynamic-cursors/8c1679b87c54e97145cae83e622956d720e88bef";
  };

  den.aspects.hyprland-bigscreen = {
    nixos = { pkgs, ... }:
    {

      nix.settings = { # TODO: ???
        substituters = ["https://hyprland.cachix.org"];
        trusted-substituters = ["https://hyprland.cachix.org"];
        trusted-public-keys = ["hyprland.cachix.org-1:a7pgxzMz7+chwVL3/pzj6jIBMioiJM7ypFP8PwtkuGc="];
      };

      programs.hyprland = {
        enable = true;

        /* -------------------------------------------------------
          Wrapes Wayland compositors for integration with systemd.
          Starts appropriate targets like graphical-session.target,
          uses dbus-broker
          -------------------------------------------------------- */
        withUWSM = true;

        xwayland.enable = true; # TODO: ???
        package = pkgs.hyprland;  # TODO: ???
        portalPackage = pkgs.xdg-desktop-portal-hyprland; # TODO: ???
      };

      hardware.graphics.enable = true; # TODO: ???

      /* --------------------------- Screensharing -------------------------- */
      xdg.portal = {
        enable = true;
        extraPortals = with pkgs; [ xdg-desktop-portal-hyprland ];
      };

    };

    homeManager = { pkgs, ... }: {
      wayland.windowManager.hyprland = {
        enable = true;
        systemd.enable = false; # has to be off for UWSM to work
        settings = {
          # Optimized for TV/Large Screen
          monitor = ", preferred, auto, 1.5"; # Adjust scaling as needed for TV

          general = {
            gaps_in = 10;
            gaps_out = 20;
            border_size = 3;
          };

          # Add specific keybindings or auto-start apps (like a browser or media player) here
          exec-once = [ "firefox" ];
        };
      };
    };
  };
}