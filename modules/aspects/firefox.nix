{ den, ... }:
{
  den.aspects.firefox = {

    homeManager = { pkgs, ... }:{
      programs.firefox = {
        enable = true;
        package = pkgs.firefox;
        languagePacks = [
          "ru_RU"
          "en-US"
        ];
        nativeMessagingHosts = [
          pkgs.firefoxpwa
          pkgs.kdePackages.plasma-browser-integration
        ];
        # pkcs11Modules = [  ];
        policies = {
          # Updates & Background Services
          AppAutoUpdate = false;
          BackgroundAppUpdate = false;

          # Feature Disabling
          DisableProfileImport = true;
          DisablePocket = true;
          NoDefaultBookmarks = true;
          OfferToSaveLoginsDefault = false;

          # # UI and Behavior
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

        # profiles.likivik = {
        #   id = 0;
        #   isDefault = true;
        #   name = "likivik";
        #   userChrome = ./userChrome.css;
          # extensions = {
          #   settings = {
          #     sidebery.settings = {
          #       sidebarCSS = "#root.root {--frame-fg: #813d9cff;}";
          #     };
          #   };
          # };
        };

      };
    };

}