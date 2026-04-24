# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, lib, ... }:

{
  imports =
    [ # Include the results of the hardware scan.
      #/etc/nixos/hardware-configuration.nix


      
      
    ];

  networking.hostName = "nephilim"; # Define your hostname.

  system.stateVersion = "25.05";
  # https://nixos.wiki/wiki/FAQ/When_do_I_update_stateVersion

# Swapiness is nothing but the value of how aggressively you want to use
# the swap partition, which ranges from 0 to 100.
  boot.kernel.sysctl = { "vm.swappiness" = 1;};

}
