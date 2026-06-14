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
      let
        arcAurora = pkgs.stdenv.mkDerivation {
          name = "arc-aurora-cursors";
          src = pkgs.fetchFromGitHub {
            owner = "yeyushengfan258";
            repo = "ArcAurora-Cursors";
            rev = "9689e49487818bface315f8cf1d2c4f860f050a7";
            hash = "sha256-u/x8aEeOskv6R8uCB4ojn9tXxTxflejWACxgp03o9PI=";
          };
          installPhase = ''
            mkdir -p $out/share/icons
            cp -r dist/* $out/share/icons/
          '';
        };

        afterglow = pkgs.stdenv.mkDerivation {
          name = "afterglow-cursors";
          src = pkgs.fetchFromGitHub {
            owner = "yeyushengfan258";
            repo = "Afterglow-Cursors";
            rev = "424a3326827f3bc56856fc5a3a1cce8da1ea3ecd";
            hash = "sha256-Kv4/MyuZXicM0rT89lZZd7AUwxb55bq0lYEetSybFTk=";
          };
          installPhase = ''
            mkdir -p $out/share/icons
            cp -r dist/* $out/share/icons/
          '';
        };

        aosp = pkgs.stdenv.mkDerivation {
          name = "aosp-cursors";
          src = pkgs.fetchzip {
            url = "https://github.com/Tech-Tac/aosp-cursors/releases/download/1.1.0/aosp-cursors-linux-1.1.0.tar.xz";
            hash = "sha256-zLUd7ZZHIE1AiFw9GaeU2E6mjd6okKrxEG8Jt5z6ltA=";
          };
          installPhase = ''
            mkdir -p $out/share/icons
            cp -r * $out/share/icons/
          '';
        };

        pixelfun2 = pkgs.stdenv.mkDerivation {
          name = "pixelfun2-cursors";
          src = pkgs.fetchurl {
            url = "https://aur.archlinux.org/cgit/aur.git/plain/xcur-pixelfun-all-merge.tar.zst?h=xcursor-pixelfun-all";
            hash = "sha256-BRz1Osw2a5D937icfPeGd4NP5kD4J08Ch0qhMigflrc=";
          };
          nativeBuildInputs = [ pkgs.zstd ];
          unpackPhase = ''
            zstd -d < $src | tar xf -
          '';
          installPhase = ''
            mkdir -p $out/share/icons
            cp -r ./* $out/share/icons/
          '';
        };
      in
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
          pcmanfm
        ] ++ [
          arcAurora
          afterglow
          aosp
          pixelfun2
        ];

        services.gnome.gnome-keyring.enable = true;
        services.upower.enable = true;
      };

    maid =
      { user, ... }:
      {
        file.xdg_config."DankMaterialShell".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/DankMaterialShell";
      };
  };
}
