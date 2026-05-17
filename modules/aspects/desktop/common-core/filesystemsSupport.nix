{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.filesystemsSupport = {
    nixos =
      { config, pkgs, ... }:
      {
        boot.supportedFilesystems = [ "fat32" "exfat" "ntfs" ];

        services.fstrim.enable = true;

        environment.systemPackages = with pkgs; [
          dosfstools
          mtools
        ];
      };
  };
}