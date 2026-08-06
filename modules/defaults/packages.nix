# Flake-level `packages.x` outputs for graphiti (external consumers
# can `nix build github:Likivik/spectacle#graphiti-mcp`).
# graphiti-mcp is built via uv2nix from its uv.lock in
# pkgs/graphiti/mcp-workspace/ — that workspace fully owns Python
# resolution (no Nix substitutes). The uv2nix sub-flake applies PR #1500
# patch to graphiti-core via pyprojectOverrides.
{
  perSystem =
    {
      inputs',
      ...
    }:
    {
      packages = {
        graphiti-mcp = inputs'.graphiti-mcp-workspace.packages.x86_64-linux.graphiti-mcp;
      };
    };
}
