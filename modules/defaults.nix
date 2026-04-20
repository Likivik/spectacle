# This file: nixos default stuffs
{ inputs, ... }:
{

  den.default.nixos.system.stateVersion = "25.11";
  den.default.homeManager.home.stateVersion = "25.11";

    # These are functions that produce configs
  # den.default.includes = [ 
  #   den.provides.define-user # Automatically create users + their homes, by just adding them to hosts
  #   # TODO: ??? does this not happen automatically? ${user}.provides.${host} and ${host}.provides.${user}
  #   den.provides.mutual-provider
  #   # TODO: ??? this Automatically sets hostname, but isn't it already automatically set as per host schema?
  #   den.provides.hostname 

  # ];
}