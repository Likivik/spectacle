# This file: nixos default stuffs
{ inputs, den, lib, pkgs, ... }:
{
  /* ------------------------------------------------------------------------
                                      NixOS
    ------------------------------------------------------------------------- */
  den.default.nixos.system.stateVersion = "25.11"; # set Nixpkgs version you start with, never change for proper backward compatability
  den.default.networking.firewall.enable = true; # enable firewall everywhere
	flake.den = den;

  /* ------------------------------------------------------------------------
                                  Home manager
    ------------------------------------------------------------------------- */

  den.default.homeManager.home.stateVersion = "25.11"; # Set HM version with which you started, never change for proper backward compatability
  den.schema.user.classes = lib.mkDefault [ "homeManager" "maid" ]; # enable HM class for every user by default

  # hm-host schema: includes are resolved as aspects for any host with HM users.
  # nixos blocks here apply system-wide to all HM-enabled hosts.
  den.schema.hm-host.includes = [
    {
      nixos = {
        home-manager.useGlobalPkgs = true;
        home-manager.useUserPackages = true;
      };
    }
  ];


  den.default.includes = [
    /* ------------------------------ Den Batteries ----------------------------- */
    den.provides.hostname # TODO: ??? this Automatically sets hostname, but isn't it already automatically set as per host schema?
    den.provides.define-user # Automatically create users + their homes, by just adding them to hosts

    den.provides.mutual-provider  # TODO: ??? Learn why this is useful ${user}.provides.${host} and ${host}.provides.${user}
    /* --------------------------------- Aspects -------------------------------- */


  ];

}
