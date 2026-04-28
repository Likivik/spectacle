 { inputs, den, lib, ... }:
{

  den.aspects.spectacle = {

      includes = [

        den.aspects.gnome-desktop
        den.aspects.firefox
        den.aspects.peripherals-base

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