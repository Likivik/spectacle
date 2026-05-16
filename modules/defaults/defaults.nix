# This file: nixos default stuffs
{ inputs, den, lib, pkgs, ... }:
{
  /* ------------------------------------------------------------------------
                                      NixOS
    ------------------------------------------------------------------------- */
  den.default.nixos.system.stateVersion = "25.11"; # set Nixpkgs version you start with, never change for proper backward compatability
  den.default.networking.firewall.enable = true; # enable firewall everywhere
	flake.den = den;
  den.default.includes = [

    /* ------------------------------ Den Batteries ----------------------------- */
    den.provides.hostname # TODO: ??? this Automatically sets hostname, but isn't it already automatically set as per host schema?
    den.provides.define-user # Automatically create users + their homes, by just adding them to hosts

    den.provides.mutual-provider  # TODO: ??? Learn why this is useful ${user}.provides.${host} and ${host}.provides.${user}
    /* --------------------------------- Aspects -------------------------------- */


  ];

}
