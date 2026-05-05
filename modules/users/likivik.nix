{ inputs, den, ... }:
{
  # user aspect
  den.aspects.likivik = {
    includes = [
      den.provides.primary-user
      (den.provides.user-shell "bash")
    ];

    homeManager =
      { pkgs, ... }:
      {

      };

    # user can provide NixOS configurations
    # to any host it is included on
    nixos = { pkgs, user, ... }: {
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
