 { inputs, den, lib, ... }:
{

  den.aspects.spectacle = {

      includes = [

        den.aspects.desktop.desktopManagers.gnome
        den.aspects.firefox
        den.aspects.desktop.common-core.peripherals-base
        den.aspects.torrserver

      ];

      nixos = {
        boot.loader.systemd-boot.enable = true;
        boot.loader.efi.canTouchEfiVariables = true;
        fileSystems."/" = {
          device = "tmpfs";
          fsType = "tmpfs";
          options = [ "mode=0755" ];
        };
      };

  };

}