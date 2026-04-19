# This file: nixos default stuffs
{ inputs, ... }:
{
  # Main nixpkgs source
  flake-file.inputs = {
    # nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/0.1"; # flakehub unstable
    # nixpkgs.url = "https://flakehub.com/f/DeterminateSystems/nixpkgs-weekly/0.1";
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  den.default.nixos.system.stateVersion = "25.11";
}