{ config, pkgs, lib, ... }:

{
  # ZFS
  boot.supportedFilesystems = [ "zfs" ];
  boot.zfs.forceImportRoot = false; # was a legacy option, recommended to avoid "ohshits"
  networking.hostId = "ad7406b6"; # generated with head -c4 /dev/urandom | od -A none -t x4 (ZFS needs it to identify machines)
  #boot.kernelPackages = config.boot.zfs.package.latestCompatibleLinuxPackages; # don't update to unsupported kernel
  services.zfs.autoScrub.enable = true; # enable zfs scrubbing (defaults to weekly/all pools)
  boot.zfs.extraPools = [ "serenity_onetb_zpool" ];
  boot.zfs.devNodes = "/dev/disk/by-label/serenity_onetb_zpool";
  boot.initrd.supportedFilesystems = [ "zfs" ]; # required for zfs;
}
