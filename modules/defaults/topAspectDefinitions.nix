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
<<<<<<< HEAD
      den.aspects.desktop.common-core.desktop-inbox
      den.aspects.desktop.common-core.filesystems-support
=======
      den.aspects.desktop.common-core.desktopInbox
      den.aspects.desktop.common-core.filesystemsSupport
>>>>>>> explore
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
<<<<<<< HEAD
      den.aspects.desktop.common-extra.peripherals-extra
=======
      den.aspects.desktop.common-extra.peripheralsExtra
>>>>>>> explore
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
<<<<<<< HEAD
      den.aspects.dev.flatpak-build
=======
      den.aspects.dev.Flatpak-build
>>>>>>> explore
      den.aspects.dev.android
      den.aspects.dev.audiobookshelf
      den.aspects.dev.dev-fonts
      den.aspects.dev.direnv
      den.aspects.dev.docker
      den.aspects.dev.qt-inspection
      den.aspects.dev.shell-commands
      den.aspects.dev.shells.bash
      den.aspects.dev.shells.elvish
      den.aspects.dev.shells.zsh
      den.aspects.dev.ssh
      den.aspects.dev.stash
      den.aspects.dev.virtualization
    ];
  };

  den.aspects.server = {};
}
