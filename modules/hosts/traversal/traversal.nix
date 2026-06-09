{ den, lib, inputs, ... }: {
  den.aspects.traversal = {

    includes = [
      den.aspects.core
      den.aspects.desktop.common-core

      den.aspects.desktop.desktopManagers.noctalia

      den.aspects.dev
      
      den.aspects.firefox
    ];

    nixos = {config, modulesPath, ... }: {
      imports = [ (modulesPath + "/installer/scan/not-detected.nix")];

      # services.openssh.enable = true;

      boot.initrd.availableKernelModules = [ "nvme" "xhci_pci" "thunderbolt" "usb_storage" "sd_mod" "sdhci_pci" ];
      boot.initrd.kernelModules = [ ];
      boot.kernelModules = [ "kvm-amd" ];
      boot.extraModulePackages = [ ];

      fileSystems."/" =
        { device = "/dev/disk/by-uuid/ef9e9419-e98c-4667-a569-e1afeedf3df4";
          fsType = "btrfs";
        };

      fileSystems."/boot" =
        { device = "/dev/disk/by-uuid/CABA-4BEE";
          fsType = "vfat";
          options = [ "fmask=0077" "dmask=0077" ];
        };

      swapDevices =
        [ { device = "/dev/disk/by-uuid/1385a7cc-ed8e-4567-a77d-0a11bf7f8ac1"; }
        ];

      # Enables DHCP on each ethernet and wireless interface. In case of scripted networking
      # (the default) this is the recommended approach. When using systemd-networkd it's
      # still possible to use this option, but it's recommended to use it in conjunction
      # with explicit per-interface declarations with `networking.interfaces.<interface>.useDHCP`.
      networking.useDHCP = lib.mkDefault true;
      # networking.interfaces.enp2s0.useDHCP = lib.mkDefault true;
      # networking.interfaces.wlo1.useDHCP = lib.mkDefault true;

      nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
      hardware.cpu.amd.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;

    };


  };
}
