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
            mkdir -p $out/share/icons/ArcAurora
            cp -r dist/* $out/share/icons/ArcAurora/
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
            mkdir -p $out/share/icons/Afterglow
            cp -r dist/* $out/share/icons/Afterglow/
          '';
        };

        aosp = pkgs.stdenv.mkDerivation {
          name = "aosp-cursors";
          src = pkgs.fetchzip {
            url = "https://github.com/Tech-Tac/aosp-cursors/releases/download/1.1.0/aosp-cursors-linux-1.1.0.tar.xz";
            hash = "sha256-zLUd7ZZHIE1AiFw9GaeU2E6mjd6okKrxEG8Jt5z6ltA=";
          };
          installPhase = ''
            mkdir -p $out/share/icons/AOSP-Cursors
            cp -r * $out/share/icons/AOSP-Cursors/
          '';
        };

        catppuccin-latte-mauve-src = pkgs.fetchzip {
          url = "https://github.com/catppuccin/cursors/releases/download/v2.0.0/catppuccin-latte-mauve-cursors.zip";
          hash = "sha256-fQrLyF9fnkbahrC/7UFWhS8hh/8PVvuDp33eKItM9Io=";
        };
        catppuccin-frappe-mauve-src = pkgs.fetchzip {
          url = "https://github.com/catppuccin/cursors/releases/download/v2.0.0/catppuccin-frappe-mauve-cursors.zip";
          hash = "sha256-02m1wBAF82DeehYScBzf2ARQjX0oZbRfq0wiIizlh74=";
        };
        catppuccin-macchiato-mauve-src = pkgs.fetchzip {
          url = "https://github.com/catppuccin/cursors/releases/download/v2.0.0/catppuccin-macchiato-mauve-cursors.zip";
          hash = "sha256-LtEMo9jK6zbvgI2p+iXUfmuRreBbR79gdRP+C/Vg5eU=";
        };
        catppuccin-mocha-mauve-src = pkgs.fetchzip {
          url = "https://github.com/catppuccin/cursors/releases/download/v2.0.0/catppuccin-mocha-mauve-cursors.zip";
          hash = "sha256-F6kKWVLO+xxSnJp/cdIUZuplb2NZJTZJSjJ6IWyYRV4=";
        };
        catppuccin-mauve = pkgs.stdenv.mkDerivation {
          name = "catppuccin-mauve-cursors";
          phases = [ "installPhase" ];
          installPhase = ''
            mkdir -p $out/share/icons
            cp -r ${catppuccin-latte-mauve-src} $out/share/icons/Catppuccin-Latte-Mauve
            cp -r ${catppuccin-frappe-mauve-src} $out/share/icons/Catppuccin-Frappe-Mauve
            cp -r ${catppuccin-macchiato-mauve-src} $out/share/icons/Catppuccin-Macchiato-Mauve
            cp -r ${catppuccin-mocha-mauve-src} $out/share/icons/Catppuccin-Mocha-Mauve
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
          capitaine-cursors
          i2c-tools
          pcmanfm
        ] ++ [
          arcAurora
          afterglow
          aosp
          catppuccin-mauve
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
