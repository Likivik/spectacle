{ den, ... }:
{

  den.aspects.hyprland-bigscreen = {
    nixos = { ... }: {
      programs.hyprland.enable = true;
      hardware.graphics.enable = true;
    };

    homeManager = { pkgs, ... }: {
      wayland.windowManager.hyprland = {
        enable = true;
        settings = {
          # Optimized for TV/Large Screen
          monitor = ", preferred, auto, 1.5"; # Adjust scaling as needed for TV
          
          general = {
            gaps_in = 10;
            gaps_out = 20;
            border_size = 3;
          };

          # Add specific keybindings or auto-start apps (like a browser or media player) here
          exec-once = [ "firefox" ];
        };
      };
    };
  };
}