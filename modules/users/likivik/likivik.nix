{ inputs, den, ... }:
{
  # user aspect
  den.aspects.likivik = {
    includes = [
      den.provides.primary-user
      (den.provides.user-shell "bash")
      den.aspects.firefox
    ];

    nixos =
      { pkgs, user, ... }:
      {
        users.users.${user.userName} =
          {
            initialPassword = "vm";
            extraGroups = [
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
              "video"
            ];
          };
      };
  };
}
