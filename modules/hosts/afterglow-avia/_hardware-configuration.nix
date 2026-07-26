# Skeleton generated on 2026-07-25.
# Replace UUIDs/filesystems with real values from `nixos-generate-config --root /mnt`
# once the monoblock is provisioned with NixOS on disk.
{ modulesPath, ... }:
{
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
  ];

  # Detect these on the box:
  #   boot.initrd.availableKernelModules = [ "xhci_pci" "ahci" "usbhid" "usb_storage" "sd_mod" ];
  #   boot.initrd.kernelModules = [ ];
  #   boot.kernelModules = [ "kvm-intel" ];
  #   boot.extraModulePackages = [ ];

  # Intel iGPU — minimal config; expand once hw is detected
  hardware.graphics.enable = true;
  hardware.cpu.intel.updateMicrocode = true;

  # Deterministic hostId — keeps kkmserver license binding stable across reboots.
  # Randomly generated with `head -c4 /dev/urandom | od -A none -t x4`
  networking.hostId = "1a2b3c4d";

  # fileSystems."/" (tmpfs root) is set in afterglow-avia.nix
}