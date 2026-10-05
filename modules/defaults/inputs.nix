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
    nixpkgs-master.url = "github:NixOS/nixpkgs/master";
    # # Replace github:NixOS/nixpkgs/nixos-unstable
    # nixpkgs.url = "git+https://tsinghua.edu.cn";
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
    nix-maid.url = "github:viperML/nix-maid";
    nixfmt-rs.url = "github:Mic92/nixfmt-rs";
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixos-anywhere = {
      url = "github:nix-community/nixos-anywhere";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # Upstream, pinned to a RELEASE TAG. The tag matters: flake.lock is the only
    # thing that would otherwise move this input, and a tag pin is what keeps a
    # plain  from silently walking the agent forward.
    #
    # v2026.9.24 (Hermes 0.21.5) is the floor for the restart-safe cron fix
    # (upstream #111484, first shipped v2026.9.21): before it a SUCCESSFUL
    # systemd-scope probe was cached permanently, so once the user bus vanished
    # every cron tick still wrapped its worker in ,
    # exited 1, and 100% of scheduled jobs failed forever. Do not pin below
    # v2026.9.21 — the  check guards this.
    #
    # We used to carry a 2-commit deps fork (otel 1.43 pin + langfuse extra);
    # both went upstream, so the fork is gone. Do NOT re-declare this input in
    # an aspect — two definitions conflict and break 
    # (and its check-flake-file guard) outright.
    hermes-agent = {
      url = "github:NousResearch/hermes-agent/v2026.9.24";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    llm-agents = {
      url = "github:numtide/llm-agents.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    quadlet-nix = {
      url = "github:SEIAROTg/quadlet-nix";
    };

    # For packaging graphiti-mcp-server from its uv.lock (its pyproject.toml
    # has no [build-system] block — only installable via uv). uv2nix turns
    # uv.lock into Nix derivations.
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Sub-flake: graphiti-mcp-server packaged via uv2nix from uv.lock.
    graphiti-mcp-workspace = {
      url = "path:./pkgs/graphiti/mcp-workspace";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.uv2nix.follows = "uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.pyproject-build-systems.follows = "pyproject-build-systems";
    };
  };
}
