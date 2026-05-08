# This file: nixos default stuffs
{ inputs, den, lib, pkgs, ... }:
{

  /* ------------------------------------------------------------------------
                                  Home manager
    ------------------------------------------------------------------------- */
  
  den.default.homeManager.home.stateVersion = "25.11"; # Set HM version with which you started, never change for proper backward compatability

  den.schema.user.classes = lib.mkDefault [ "homeManager" ]; # enable HM for every user by default
  den.ctx.hm-host = {
    home-manager.useGlobalPkgs = true; # TODO: ???
    home-manager.useUserPackages = true; # TODO: ???
  };
}