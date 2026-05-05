{ inputs,
  den,
  lib,
  config,
  pkgs,
  ...
}:
{

  den.aspects.serenity = {

    includes = [

    ];

    nixos = { modulesPath, ... }: {

      imports = [
        # provides basic hardware detection/drivers
        (modulesPath + "/installer/scan/not-detected.nix")
      ];

      boot.initrd.availableKernelModules = [
        "xhci_pci"
        "ahci"
        "usbhid"
        "usb_storage"
        "sd_mod"
      ];
      boot.initrd.kernelModules = [ ];
      boot.kernelModules = [ "kvm-intel" ];
      boot.extraModulePackages = [ ];

      fileSystems."/panther" = {
        device = "/dev/disk/by-uuid/b1f69b8f-cc97-4879-9942-ac8df1e0f6d8";
        fsType = "ext4";
        options = [
          "defaults"
          "user"
          "rw"
        ];
      };

      fileSystems."/" = {
        device = "/dev/disk/by-uuid/812b6d5f-dc5d-4ee7-a576-e4644011d1c3";
        fsType = "ext4";
      };

      fileSystems."/boot" = {
        device = "/dev/disk/by-uuid/E385-6E2F";
        fsType = "vfat";
      };

      swapDevices = [
        { device = "/dev/disk/by-uuid/f8ffc153-dd5c-41cc-9827-49a5788c697b"; }
      ];

      powerManagement.cpuFreqGovernor = "performance";
      hardware.cpu.intel.updateMicrocode = config.hardware.enableRedistributableFirmware;

      # ZFS
      boot.supportedFilesystems = [ "zfs" ];
      boot.zfs.forceImportRoot = false; # was a legacy option, recommended to avoid "ohshits"
      networking.hostId = "ad7406b6"; # generated with head -c4 /dev/urandom | od -A none -t x4 (ZFS needs it to identify machines)
      #boot.kernelPackages = config.boot.zfs.package.latestCompatibleLinuxPackages; # don't update to unsupported kernel
      services.zfs.autoScrub.enable = true; # enable zfs scrubbing (defaults to weekly/all pools)
      boot.zfs.extraPools = [ "serenity_onetb_zpool" ];
      boot.zfs.devNodes = "/dev/disk/by-label/serenity_onetb_zpool";
      boot.initrd.supportedFilesystems = [ "zfs" ]; # required for zfs;

      # Nvidia driver
      services.xserver.videoDrivers = [ "nvidia" ];
      #services.xserver.videoDrivers = [ "nouveau" ];
      hardware.nvidia.open = true; # kernel modules, support moves to foss

      hardware.graphics = {
        enable = true;
        enable32Bit = true;
        extraPackages = with pkgs; [
          intel-media-driver

        ];
      };

      boot = {
        blacklistedKernelModules = [
          "nouveau"
          #"i915"
        ];
        kernelParams = [ "nomodeset" ];

      };
    };

  };

}
