{ den, inputs, lib, pkgs, ... }: {
  flake-file.inputs = {
    noctalia = {
      url = "github:noctalia-dev/noctalia-shell/v5";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.desktop.desktopManagers.noctalia = {
    includes = [
      den.aspects.desktop.desktopManagers.niri
    ];

    nixos = { config, pkgs, ... }: {
      environment.systemPackages = [
        inputs.noctalia.packages.${pkgs.stdenv.hostPlatform.system}.default
      ];

      networking.networkmanager.enable = lib.mkDefault true;
      hardware.bluetooth.enable = lib.mkDefault true;
      services.tuned.enable = lib.mkDefault true;
      services.upower.enable = lib.mkDefault true;

      services.displayManager.gdm = {
        enable = true;
      };
      services.displayManager.defaultSession = "niri";

      services.gnome.gnome-keyring.enable = true;
      security.polkit.enable = true;
    };

    maid = { user, ... }: {
      file.xdg_config."noctalia".source = ./../../../../../modules/users/likivik/dotfiles/noctalia;
    };
  };
}
