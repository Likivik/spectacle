{ inputs, den, ... }:
{
  den.aspects.kdeSddm = {
    nixos = { config, pkgs, lib, ... }: {
      # SDDM
      services.displayManager.sddm = {
        enable = lib.mkDefault true;
        wayland.enable = true;
        wayland.compositor = "kwin";
        theme = "catppuccin-mocha-mauve";
      };

      # Themes for SDDM
      environment.systemPackages = [
        (pkgs.catppuccin-sddm.override {
          flavor = "mocha";
          accent = "mauve";
          font = "Noto Sans";
          fontSize = "14";
          loginBackground = false;
          clockEnabled = false;
        })
      ];
    };
  };
}