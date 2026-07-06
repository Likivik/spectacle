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

        programs.kdeconnect = {
          enable = true;
          package = pkgs.valent;
        };

        environment.systemPackages = with pkgs; [
          capitaine-cursors
          i2c-tools
          libinput # bongoCat plugin
          pcmanfm
          papirus-icon-theme
          tela-icon-theme
          tesseract
          kdePackages.breeze-icons
          kdePackages.qt6ct
          kdePackages.okular
          kdePackages.ark
          kitty
          ghostty
          wezterm
          adw-gtk3
          seahorse
        ] ++ [
          afterglow
          aosp
          pkgs.catppuccin-cursors.latteDark
          pkgs.catppuccin-cursors.latteLight
          pkgs.phinger-cursors
          pkgs.oreo-cursors-plus
          pkgs.simp1e-cursors
          pkgs.graphite-cursors
          pkgs.nordzy-cursor-theme
          pkgs.posy-cursors
        ];

        # GTK_USE_PORTAL set in niri.nix — routes GTK file dialogs
        # through xdg-desktop-portal-kde.

        services.gnome.gnome-keyring.enable = true;
        security.pam.services.dms-greeter.enableGnomeKeyring = true;
        services.upower = {
          enable = true;
          percentageLow = 10;
          percentageCritical = 7;
          percentageAction = 5;
          criticalPowerAction = "PowerOff";
        };
      };

    maid =
      { user, ... }:
      {
        file.xdg_config."DankMaterialShell".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/DankMaterialShell";
        file.xdg_config."qt6ct/qt6ct.conf".text = ''
          [Appearance]
          icon_theme=Tela
          standard_dialogs=filechooser
        '';
        file.xdg_config."ghostty/config".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/ghostty/config";
        file.xdg_config."kitty/kitty.conf".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/kitty/kitty.conf";
        file.xdg_config."wezterm/wezterm.lua".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/wezterm/wezterm.lua";
        file.xdg_config."mimeapps.list".text = ''
          [Default Applications]
          inode/directory=org.kde.dolphin.desktop
          image/*=qimgv.desktop
          image/svg+xml=qimgv.desktop
          image/vnd.adobe.photoshop=org.kde.krita.desktop
          image/vnd.krita=org.kde.krita.desktop
          video/*=org.kde.haruna.desktop
          application/pdf=org.kde.okular.desktop
          text/*=codium.desktop
          application/msword=writer.desktop
          application/vnd.openxmlformats-officedocument.wordprocessingml.document=writer.desktop
          application/vnd.ms-excel=calc.desktop
          application/vnd.openxmlformats-officedocument.spreadsheetml.sheet=calc.desktop
          application/vnd.ms-powerpoint=impress.desktop
          application/vnd.openxmlformats-officedocument.presentationml.presentation=impress.desktop
          application/vnd.oasis.opendocument.text=writer.desktop
          application/vnd.oasis.opendocument.spreadsheet=calc.desktop
          application/vnd.oasis.opendocument.presentation=impress.desktop
          application/zip=org.kde.ark.desktop
          application/x-tar=org.kde.ark.desktop
          application/gzip=org.kde.ark.desktop
          application/x-7z-compressed=org.kde.ark.desktop
          application/x-rar=org.kde.ark.desktop
          x-scheme-handler/http=firefox.desktop
          x-scheme-handler/https=firefox.desktop
          x-scheme-handler/about=firefox.desktop
        '';
      };
  };
}
