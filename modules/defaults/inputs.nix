# This file: pulls stuff needed for den/dendritic stuff
{ inputs, ... }:
{
  imports = [
    (inputs.flake-file.flakeModules.dendritic or { })
    (inputs.den.flakeModules.dendritic or { })

  ];

  # other inputs may be defined at a module using them.
  flake-file.inputs = {
    # nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1"; # flakehub unstable
    # nixpkgs.url = "https://flakehub.com/f/DeterminateSystems/nixpkgs-weekly/0.1";
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    # den.url = "github:vic/den";
    den = {
      # url = "github:denful/den?rev=8101ec865c0bf4027d40b9fd8951e3e435a86d64";
      url = "github:denful/den";
      # url = "github:vic/den/feat/fx-pipeline";
    };
    flake-file.url = "github:vic/flake-file";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    determinate.url = "https://flakehub.com/f/DeterminateSystems/determinate/*";
  };
}
