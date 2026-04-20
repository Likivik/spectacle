# This file: pulls stuff needed for den/dendritic stuff
{ inputs, ... }:
{
  imports = [
    (inputs.flake-file.flakeModules.dendritic or { })
    (inputs.den.flakeModules.dendritic or { })
    # inputs.determinate.nixosModules.default
  ];

  # other inputs may be defined at a module using them.
  flake-file.inputs = {
    den.url = "github:vic/den";
    flake-file.url = "github:vic/flake-file";
    determinate.url = "https://flakehub.com/f/DeterminateSystems/determinate/*";
  };



}
