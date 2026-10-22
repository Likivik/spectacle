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

          # enableSystemMonitoring, enableVPN, enableClipboardPaste,
          # enableDynamicTheming and enableCalendarEvents were all removed
          # upstream. DMS detects networking at runtime and ships these
          # features built in, so the options no longer exist and merely
          # setting them fails the assertions — which breaks `nix build` for
          # every host that includes this aspect (traversal among them).

          # `src` for every entry below is filled in by
          # inputs.dms-plugin-registry.nixosModules.default (imported above),
          # which only knows plugins listed in the official registry. Six names
          # that used to be here are NOT in that registry and therefore had no
          # src, which made the whole host fail to evaluate:
          #   caffeine            - repo deleted upstream; DMS has a built-in
          #                         idle inhibitor, so it is not needed
          #   dankBatteryAlerts   - first-party only (AvengeMedia/dms-plugins);
          #                         re-add with an explicit src if wanted
          #   folderView          - repo archived, not in the registry
          #   keybindingCheatSheet- not in the registry, duplicates
          #                         dankLauncherKeys
          #   qcalCalendar        - not in the registry (unofficial repo);
          #                         khalCalendar / dankCalendarAgenda are the
          #                         registry equivalents
          #   tailscale           - registered as `tailscaleDashboard`
          plugins = {
            bongoCat.enable = true;
            clipboardPlus.enable = true;
            commandRunner.enable = true;
            dankActions.enable = true;
            dankBitwarden.enable = true;
            dankCalendar.enable = true;
            dankDiskUsage.enable = true;
            dankHooks.enable = true;
            dankKDEConnect.enable = true;
            dankLauncherKeys.enable = true;
            displayManager.enable = true;
            emojiLauncher.enable = true;
            githubInbox.enable = true;
            niriDS.enable = true;
            nixMonitor.enable = true;
            nixPackageRunner.enable = true;
            ocrScanner.enable = true;
            quickTote.enable = true;
            tailscaleDashboard.enable = true;
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
          libnotify
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
          ghostty
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
      { user, host, ... }:
      let
        gitRoot = import ../../../../../lib/git-root.nix host;
      in
      {
        file.xdg_config."DankMaterialShell".source = "${gitRoot}/spectacle/modules/users/likivik/dotfiles/DankMaterialShell";
        file.xdg_config."qt6ct/qt6ct.conf".text = ''
          [Appearance]
          icon_theme=Tela
          standard_dialogs=filechooser
        '';
        file.xdg_config."ghostty/config".source = "${gitRoot}/spectacle/modules/users/likivik/dotfiles/ghostty/config";
        file.xdg_config."kitty/kitty.conf".source = "${gitRoot}/spectacle/modules/users/likivik/dotfiles/kitty/kitty.conf";
        file.xdg_config."wezterm/wezterm.lua".source = "${gitRoot}/spectacle/modules/users/likivik/dotfiles/wezterm/wezterm.lua";
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
