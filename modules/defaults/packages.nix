# Flake-level `packages.x` outputs for graphiti (external consumers
# can `nix build github:Likivik/spectacle#graphiti-core` etc.).
# Internal modules should still use `pkgs.callPackage ../../pkgs/graphiti/core.nix`
# directly for clarity. This module only exposes packages for *external*
# flake consumers, mirroring the pattern in `vm.nix`.

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
      python = python3Packages.python;
      graphiti-core = python3Packages.callPackage ../../pkgs/graphiti/core.nix {
        # python3Packages attrs visible to callPackage automatically:
        # buildPythonPackage, fetchPypi, hatchling, pydantic, neo4j, openai,
        # tenacity, numpy, python-dotenv, posthog, falkordb, lib
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