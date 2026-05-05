{ inputs, den, user, ... }:
{
  # user aspect
  den.aspects.likivik = {
    includes = [
      den.provides.primary-user
      (den.provides.user-shell "elvish")
      inputs.determinate.nixosModules.default
    ];

    homeManager =
      { pkgs, ... }:
      {
        home.packages = [ pkgs.htop ];
      };

    # user can provide NixOS configurations
    # to any host it is included on
    nixos = { pkgs, ... }: {
      users.users.${user.userName}.extraGroups = [
        "wheel" # to use `sudo`
        "networkmanager" # ethernet/wifi access
        "adbusers" # access to Android Debug Bridge
        "syncthing"
        "libvirtd"
        "docker"
        "podman"
        "input"
        "ydotool"
        "scanner"
        "lp"
        "pipewire"
      ];
    };
  };
}
