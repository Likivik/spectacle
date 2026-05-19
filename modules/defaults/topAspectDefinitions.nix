{ inputs, den, lib, ... }:
{
  imports = [
  ];

  den.aspects.core = {
    includes = lib.mkDefault [
      den.aspects.core.bootloader
      den.aspects.core.determinateNix
      den.aspects.core.defaultLocale
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
      den.aspects.desktop.common-core.desktopInbox
      den.aspects.desktop.common-core.filesystemsSupport
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
      den.aspects.desktop.common-extra.peripheralsExtra
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
      den.aspects.dev.Flatpak-build
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
