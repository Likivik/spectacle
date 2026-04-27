{den, ... }:
{
  den.aspects.gnome-desktop = {

    nixos = 
    { pkgs, ... }:{

      services.displayManager.gdm.enable = true;
      services.desktopManager.gnome.enable = true;
      services.displayManager.autoLogin.enable  = true;
      services.displayManager.autoLogin.user = "watcher";

      # To disable installing GNOME's suite of applications
      # and only be left with GNOME shell.
      services.gnome.core-apps.enable = true;
      services.gnome.core-developer-tools.enable = false;
      services.gnome.games.enable = false;
      environment.gnome.excludePackages = with pkgs; [ gnome-tour gnome-user-docs ];



      services.sysprof.enable = true;
    };

    homeManager = 
    { pkgs, ... }:{

      home.packages = 
      ( with pkgs; 
        [
          ocs-url
        ]
      ) 
      ++
      ( with pkgs.gnomeExtensions; [
        appindicator
        clipboard-history
        gsconnect
        impatience
        keep-awake
        open-bar
        blur-my-shell
        status-area-horizontal-spacing
        tailscale-status
        tiling-assistant
        transcodeappsearch
        vertical-workspaces
        window-gestures
        fly-pie
        kando-integration
        just-perfection
        arc-menu
      ]);

      # home.file.".local/share/gnome-shell/extensions/order-extensions@wa4557.github.com".source = builtins.fetchGit {
      #   url = "https://github.com/andia89/order-icons.git";
      # };
      # home.file.".local/share/gnome-shell/extensions/inputmethod-shortcuts@osamu.debian.org".source = builtins.fetchGit {
      #   url = "https://github.com/osamuaoki/inputmethod-shortcuts.git";
      # };

      dconf =
      {
        enable = true;
        settings = 
        {
          # Mutter Settings
          "org/gnome/mutter" = 
          {
            experimental-features =
            [
              "scale-monitor-framebuffer" # Enables fractional scaling (125% 150% 175%)
              "variable-refresh-rate" # Enables Variable Refresh Rate (VRR) on compatible displays
              "xwayland-native-scaling" # Scales Xwayland applications to look crisp on HiDPI screens
              "autoclose-xwayland" # automatically terminates Xwayland if all relevant X11 clients are gone
            ];
          };

          # Extensions Part
          "org/gnome/shell" = 
          {
            disable-user-extensions = false; # enables user extensions
            disabled-extensions = [];
          };

          #"org/gnome/shell".enabled-extensions = map (extension: extension.extensionUuid) home.packages;

          # Configure individual extensions

          # Configure GSConnect
          "org/gnome/shell/extensions/gsconnect".show-indicators = true;


        };
      };

      programs.firefox.enableGnomeExtensions = true;


    };

  };

}