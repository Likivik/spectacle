{
  den,
  inputs,
  lib,
  pkgs,
  ...
}:
{
  flake-file.inputs = {
    dms-plugin-registry = {
      url = "github:AvengeMedia/dms-plugin-registry";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.desktop.desktopManagers.dank-material-shell = {
    includes = [
      den.aspects.desktop.desktopManagers.niri
    ];

    nixos =
      { ... }:
      {
        imports = [ inputs.dms-plugin-registry.nixosModules.default ];

        services.displayManager.dms-greeter = {
          enable = true;
          compositor.name = "niri";
        };
        programs.dms-shell = {
          enable = true;

          systemd = {
            enable = true; # Systemd service for auto-start
            restartIfChanged = true; # Auto-restart dms.service when dms-shell changes
          };

          # Core features
          enableSystemMonitoring = true; # System monitoring widgets (dgop)
          enableVPN = true; # VPN management widget
          enableDynamicTheming = true; # Wallpaper-based theming (matugen)
          enableCalendarEvents = true; # Calendar integration (khal)
          enableClipboardPaste = true; # Pasting from the clipboard history (wtype)
        };
      };

    maid =
      { user, ... }:
      {
        file.xdg_config."DankMaterialShell".source = ./../../../../../users/likivik/dotfiles/dms;
      };
  };
}
