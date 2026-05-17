{ den, config, ... }:
{

  den.aspects.firefox = {

    homeManager =
      { pkgs, config, user, ... }:
      {

        programs.firefox = {
          enable = true;
          package = pkgs.firefox;
          configPath = "${config.xdg.configHome}/mozilla/firefox";
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

          # profiles.default = {
          #   id = 0;
          #   isDefault = true;
          #   name = "defaultNix";
          #   userChrome = ./userChrome.css;
          # extensions = {
          #   settings = {
          #     sidebery.settings = {
          #       sidebarCSS = "#root.root {--frame-fg: #813d9cff;}";
          #     };
          #   };
          # };
        };

        home.sessionVariables = {
          MOZ_USE_XINPUT2 = "1";
        };
      };

  };

}
