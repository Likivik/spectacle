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
      { pkgs, ... }:
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

          plugins = {
            bongoCat.enable = true;
            caffeine.enable = true;
            clipboardPlus.enable = true;
            commandRunner.enable = true;
            dankActions.enable = true;
            dankBatteryAlerts.enable = true;
            dankBitwarden.enable = true;
            dankCalendar.enable = true;
            dankDiskUsage.enable = true;
            dankHooks.enable = true;
            dankKDEConnect.enable = true;
            dankLauncherKeys.enable = true;
            displayManager.enable = true;
            emojiLauncher.enable = true;
            folderView.enable = true;
            githubInbox.enable = true;
            keybindingCheatSheet.enable = true;
            niriDS.enable = true;
            nixMonitor.enable = true;
            nixPackageRunner.enable = true;
            ocrScanner.enable = true;
            qcalCalendar.enable = true;
            quickTote.enable = true;
            tailscale.enable = true;
            unifiedTaskbar.enable = true;
            vscodeLauncher.enable = true;
            wallpaperDiscovery.enable = true;
          };
        };

        environment.systemPackages = with pkgs; [
          bibata-cursors
          capitaine-cursors
          catppuccin-cursors
          i2c-tools
        ];

        services.upower.enable = true;
      };

    maid =
      { user, ... }:
      {
        file.xdg_config."DankMaterialShell".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/dms";
      };
  };
}
