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
        };
      };

      environment.sessionVariables = {
        MOZ_USE_XINPUT2 = "1";
      };
    };

    maid = { ... }: {
      file.home.".mozilla/firefox/profiles.ini".text = ''
        [General]
        StartWithLastProfile=1

        [Profile0]
        Name=defaultNix
        IsRelative=1
        Path=defaultNix
        Default=yes

        [Profile1]
        Name=gov-sign
        IsRelative=1
        Path=gov-sign
      '';

      file.home.".mozilla/firefox/defaultNix/chrome/userChrome.css".source = ./userChrome.css;
    };
  };

}
