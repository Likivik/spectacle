{ lib, ... }:
{
  disko.devices = {
    disk = {
      ssd = {
        type = "disk";
        device = "/dev/disk/by-id/ata-CT240BX500SSD1_2023E401B128";
        content = {
          type = "gpt";
          partitions = {
            ESP = {
              size = "1G";
              type = "EF00";
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot";
                mountOptions = [ "umask=0077" ];
              };
            };
            root = {
              size = "100%";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/";
              };
            };
          };
        };
      };
      hdd1 = {
        type = "disk";
        device = "/dev/disk/by-id/ata-ST4000VN006-3CW104_WW60T7FC";
        content = {
          type = "gpt";
          partitions = {
            zfs = {
              size = "100%";
              content = {
                type = "zfs";
                pool = "tank";
              };
            };
          };
        };
      };
      hdd2 = {
        type = "disk";
        device = "/dev/disk/by-id/ata-TOSHIBA_HDWG440_4230A03FFZ0G";
        content = {
          type = "gpt";
          partitions = {
            zfs = {
              size = "100%";
              content = {
                type = "zfs";
                pool = "tank";
              };
            };
          };
        };
      };
    };
    zpool = {
      tank = {
        type = "zpool";
        mode = "mirror";
        options = {
          ashift = "12";
          autotrim = "on";
        };
        datasets = {
          "nextcloud" = {
            type = "zfs_fs";
            options = {
              mountpoint = "/tank/nextcloud";
              acltype = "posixacl";
              atime = "off";
              compression = "lz4";
              recordsize = "128K";
              xattr = "sa";
            };
          };
          "immich" = {
            type = "zfs_fs";
            options = {
              mountpoint = "/tank/immich";
              acltype = "posixacl";
              atime = "off";
              compression = "lz4";
              recordsize = "1M";
              xattr = "sa";
            };
          };
          "backups" = {
            type = "zfs_fs";
            options = {
              mountpoint = "/tank/backups";
              atime = "off";
              compression = "lz4";
              recordsize = "1M";
            };
          };
          "backups/serenity" = {
            type = "zfs_fs";
            options = {
              mountpoint = "/tank/backups/serenity";
              atime = "off";
              compression = "lz4";
              recordsize = "1M";
            };
          };
          "backups/traversal" = {
            type = "zfs_fs";
            options = {
              mountpoint = "/tank/backups/traversal";
              atime = "off";
              compression = "lz4";
              recordsize = "1M";
            };
          };
          "backups/pixel" = {
            type = "zfs_fs";
            options = {
              mountpoint = "/tank/backups/pixel";
              atime = "off";
              compression = "lz4";
              recordsize = "1M";
            };
          };
        };
      };
    };
  };
}
