# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, lib, ... }:

{
  imports =
    [ # Include the results of the hardware scan.
      /etc/nixos/hardware-configuration.nix

      # Base
      ../../collections/base
      # Devel
      ../../collections/devel
      # Users
      ../../users/likivik
      
      # Drivers
      #./drivers.nix

      # ZFS
      #./ZFS.nix

      
      
    ];

  networking.hostName = "traversal"; # Define your hostname.

  system.stateVersion = "24.05";
  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion

# Swapiness is nothing but the value of how aggressively you want to use
# the swap partition (or memory), which ranges from 0 to 100.
boot.kernel.sysctl = { "vm.swappiness" = 5;};

}
