{ config, pkgs, ... }:
{
  # Bootloader --------------------------------------------------------------
  boot = {
    loader = {
      systemd-boot = {
        enable = true; # enable systemd-boot
        consoleMode = "max";
        configurationLimit = 25; # Maximum number of latest generations in the boot menu.
      };
      efi.canTouchEfiVariables = true; # ???
    };

    # tmp -------------------------------------------------------------------
    tmp.cleanOnBoot = true; # Cuz I like it clean

    # kernel ----------------------------------------------------------------
    # kernelPackages = pkgs.linuxKernel.packages.linux_lqx;
    # zfs.package = pkgs.zfs_2_4;
  };

}
