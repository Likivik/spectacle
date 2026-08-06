{
  lib,
  inputs,
  ...
}:
{
  perSystem =
    {
      pkgs,
      ...
    }:
    let
      inherit (pkgs) python3Packages;
      # Vendored: falkordb (Python client) is not in nixpkgs.
      falkordb-py = python3Packages.callPackage ../../pkgs/graphiti/falkordb-py.nix { };
      graphiti-core = python3Packages.callPackage ../../pkgs/graphiti/core.nix {
        inherit falkordb-py;
      };
      graphiti-mcp = python3Packages.callPackage ../../pkgs/graphiti/mcp.nix {
        inherit graphiti-core;
      };
    in
    {
      packages = {
        inherit graphiti-core graphiti-mcp;
      };
    };
}