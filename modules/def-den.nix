# This file: pulls stuff needed for den/dendritic stuff
{ inputs, ... }:
{
  imports = [
    (inputs.flake-file.flakeModules.dendritic or { })
    (inputs.den.flakeModules.dendritic or { })
  ];

  # other inputs may be defined at a module using them.
  flake-file.inputs = {
    den.url = "github:vic/den";
    flake-file.url = "github:vic/flake-file";
  };

  # These are functions that produce configs
  den.default.includes = [ 
    den.provides.define-user # Automatically create users + their homes, by just adding them to hosts
    # TODO: ??? does this not happen automatically? ${user}.provides.${host} and ${host}.provides.${user}
    den.provides.mutual-provider
    # TODO: ??? this Automatically sets hostname, but isn't it already automatically set as per host schema?
    den.provides.hostname 

  ];

}
