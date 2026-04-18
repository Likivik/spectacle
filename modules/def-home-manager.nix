# This file: home-manager stuffs
{ inputs, ... }:
{
  flake-file.inputs = {
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.default.homeManager.home.stateVersion = "25.11";
}