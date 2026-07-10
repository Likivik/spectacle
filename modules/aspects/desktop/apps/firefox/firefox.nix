{ den, lib, ... }:
{

  den.aspects.firefox = {

    nixos = { pkgs, ... }: {
      programs.firefox = {
        enable = true;
        package = pkgs.firefox;
        languagePacks = [
          "ru"
          "en-US"
        ];
        nativeMessagingHosts.packages = [
          pkgs.firefoxpwa-unwrapped
          pkgs.kdePackages.plasma-browser-integration
        ];
        policies = {
          AppAutoUpdate = false;
          BackgroundAppUpdate = false;
          DisableProfileImport = true;
          DisablePocket = true;
          NoDefaultBookmarks = true;
          OfferToSaveLoginsDefault = false;
          DontCheckDefaultBrowser = true;
          HardwareAcceleration = true;
          OfferToSaveLogins = false;
          SecurityDevices = true;

          ShowHomeButton = false;
          FirefoxHome = {
            Search = true;
            TopSites = false;
            SponsoredTopSites = false;
            Highlights = false;
            Pocket = false;
            Stories = false;
            SponsoredPocket = false;
            SponsoredStories = false;
            Snippets = false;
            Locked = false;
          };

          Preferences = {
            "extensions.autoDisableScopes" = {
              Value = 0;
              Status = "user";
            };
            "browser.theme.content-theme" = {
              Value = 2;
              Status = "user";
            };
            "browser.theme.toolbar-theme" = {
              Value = 3;
              Status = "user";
            };
            "browser.shell.checkDefaultBrowser" = {
              Value = false;
              Status = "user";
            };
          };
        };
      };

      environment.sessionVariables = {
        MOZ_USE_XINPUT2 = "1";
      };
    };

    maid = { pkgs, ... }: let
      profilesIni = pkgs.writeText "firefox-profiles.ini" ''
        [General]
        StartWithLastProfile=1
        Version=2

        [Profile0]
        Name=likivik
        IsRelative=1
        Path=likivik
        Default=1

        [Profile1]
        Name=gov-sign
        IsRelative=1
        Path=gov-sign
      '';
    in {
      systemd.tmpfiles.dynamicRules = [
        "d {{xdg_config_home}}/mozilla/firefox 0755 - - -"
        "d {{xdg_config_home}}/mozilla/firefox/gov-sign 0755 - - -"
        "d {{xdg_config_home}}/mozilla/firefox/likivik 0755 - - -"
        "C+ {{xdg_config_home}}/mozilla/firefox/profiles.ini 0644 - - - ${profilesIni}"
      ];

      file.xdg_config."mozilla/firefox/likivik/chrome/userChrome.css".source = ./userChrome.css;
    };
  };

}
