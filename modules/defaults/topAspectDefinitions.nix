{ inputs, den, lib, ... }:
{
  imports = [
  ];

  den.aspects.core = {
    includes = lib.mkDefault [
      den.aspects.core.bootloader
      den.aspects.core.determinate-nix
      den.aspects.core.default-locale
      den.aspects.core.nix
      den.aspects.core.ncro
    ];
  };

  den.aspects.desktop = {};
  den.aspects.desktop.apps = {
    includes = lib.mkDefault [
      den.aspects.desktop.apps.firefox
    ];
  };
  den.aspects.desktop.common-core = {
    includes = lib.mkDefault [
      den.aspects.desktop.common-core.desktop-inbox
      den.aspects.desktop.common-core.filesystems-support
      den.aspects.desktop.common-core.networking
      den.aspects.desktop.common-core.package-sources
      den.aspects.desktop.common-core.peripherals-base
      den.aspects.desktop.common-core.printers-scanners
      den.aspects.desktop.common-core.remote-desktops
      den.aspects.desktop.common-core.vpn
    ];
  };
  den.aspects.desktop.common-extra = {
    includes = lib.mkDefault [
      den.aspects.desktop.common-extra.gaming
      den.aspects.desktop.common-extra.peripherals-extra
    ];
  };
  den.aspects.desktop.desktopManagers = {
    includes = lib.mkDefault [
      den.aspects.desktop.desktopManagers.Cosmic
      den.aspects.desktop.desktopManagers.GNOME
      den.aspects.desktop.desktopManagers.Hyprland
      den.aspects.desktop.desktopManagers.KDE
    ];
  };

  den.aspects.dev = {
    includes = lib.mkDefault [
      den.aspects.flatpak-build
      den.aspects.android
      den.aspects.dev-fonts
      den.aspects.git
      den.aspects.direnv
      den.aspects.docker
      # den.aspects.hindsight
      den.aspects.opencode
      den.aspects.qt-inspection
      den.aspects.shell-commands
      den.aspects.bash
      # den.aspects.elvish
      # den.aspects.zsh
      den.aspects.ssh
      # den.aspects.stash
      den.aspects.virtualization
    ];
  };

  den.aspects.server = {};
}
