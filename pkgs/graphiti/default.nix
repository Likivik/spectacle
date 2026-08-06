{ pkgs }:

{
  core = pkgs.callPackage ./core.nix { };
  mcp = pkgs.callPackage ./mcp.nix {
    graphiti-core = (pkgs.callPackage ./core.nix { });
  };
}