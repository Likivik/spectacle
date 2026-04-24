{
  config,
  pkgs,
  lib,
  ...
}:

{
  imports = [ ../../collections/Desktops/KDE ];

  # Define a user account. Don't forget to set a password with ‘passwd’
  users.users.likivik = {
    isNormalUser = true;
    home = "/home/likivik";
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
    ];
  };

  home-manager.users.likivik.imports = [ ./home-manager ];
}
