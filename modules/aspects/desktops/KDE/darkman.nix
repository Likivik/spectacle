{ den, ... }:
{
  den.aspects.kde-darkman = {

    homeManager =
    { pkgs, ... }:
    {

      ###############################################
      # services.darkman = {
      #   enable = true;

      #   darkModeScripts = {
      #     kde-dark = ''
      #       lookandfeeltool -platform offscreen --apply org.kde.breezedark.desktop
      #       dbus-send --session --dest=org.kde.GtkConfig --type=method_call /GtkConfig org.kde.GtkConfig.setGtkTheme "string:Breeze"
      #       notify-send --app-name="darkman" --urgency=low --icon=weather-clear-night "switching to dark mode"
      #     '';
      #   };

      #   lightModeScripts = {
      #     kde-light = ''
      #       lookandfeeltool -platform offscreen --apply org.kde.breezetwilight.desktop
      #       dbus-send --session --dest=org.kde.GtkConfig --type=method_call /GtkConfig org.kde.GtkConfig.setGtkTheme "string:Breeze"
      #       notify-send --app-name="darkman" --urgency=low --icon=weather-clear-night "switching to light mode"
      #     '';
      #   };
      #   settings = {

      #     lat = 59.9;
      #     lng = 30.3;
      #   };
      # };

    };

  };
}