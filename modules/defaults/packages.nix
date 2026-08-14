# Flake-level `packages.x` outputs for graphiti (external consumers
# can `nix build github:Likivik/spectacle#graphiti-mcp`).
# graphiti-mcp is built via uv2nix from its uv.lock in
# pkgs/graphiti/mcp-workspace/ — that workspace fully owns Python
# resolution (no Nix substitutes). The uv2nix sub-flake applies PR #1500
# patch to graphiti-core via pyprojectOverrides.
# TODO: perSystem + inputs' reference broken for non-flake-parts sub-flake.
# Remove this when we figure out the right way to expose it.
{}
