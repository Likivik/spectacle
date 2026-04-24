{ pkgs, lib, ... }:

{

  # SDDM ----------------------------------------------------------------------
  services.displayManager.sddm = {
    enable = lib.mkDefault true; # enable KDE's default Login Manager
    wayland.enable = true; # why not wayland all the way
    wayland.compositor = "kwin"; # default is weston, but since I'm using KDE anyway...
    # theme = "where_is_my_sddm_theme";
    theme = "catppuccin-mocha-mauve";
    # extraPackages = with pkgs; [ qt6.qt5compat ]; # needed this for where-is-my-sddm-theme to work
  };

  # Themes for SDDM
  environment.systemPackages = with pkgs; [
    # where-is-my-sddm-theme
    # sddm-astronaut
    # sddm-sugar-dark
    # sddm-chili-theme
    # elegant-sddm

    (catppuccin-sddm.override {
      flavor = "mocha";
      accent = "mauve";
      font = "Noto Sans";
      fontSize = "14";
      # background = "${./wallpaper.png}";
      loginBackground = false;
      clockEnabled = false;
    })

  ];

}
