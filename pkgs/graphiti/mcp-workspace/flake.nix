{
  description = "graphiti-mcp-server (uv2nix workspace, pinned to commit 526dcad7)";

  inputs = {
    nixpkgs = {
      url = "github:nixos/nixpkgs/nixos-unstable";
    };
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
  };

  outputs =
    { self
    , nixpkgs
    , pyproject-nix
    , uv2nix
    , pyproject-build-systems
    , ...
    }:
    let
      inherit (nixpkgs) lib;
      forAllSystems = lib.genAttrs lib.systems.flakeExposed;

      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      pythonSets = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python3;
          # Inject our vendored falkordb-py + graphiti-core into the
          # uv2nix pythonSet so core.nix's callPackage resolves correctly.
          graphiti-core = pkgs.python3Packages.callPackage ../core.nix { };
          falkordb-py = pkgs.python3Packages.callPackage ../falkordb-py.nix { };
        in
        (pkgs.callPackage pyproject-nix.build.packages { inherit python; })
          .overrideScope (lib.composeManyExtensions [
            pyproject-build-systems.overlays.wheel
            overlay
            (final: prev: {
              # Force mcp_server's `graphiti-core[falkordb]>=0.29.2`
              # and core.nix's `falkordb-py` arg to our Nix-built derivations.
              graphiti-core = graphiti-core;
              falkordb-py = falkordb-py;
            })
          ])
      );
    in
    {
      packages = forAllSystems (system: {
        default = self.packages.${system}.graphiti-mcp;
        graphiti-mcp =
          let
            pkgs = nixpkgs.legacyPackages.${system};
            pythonSet = pythonSets.${system};
            virtualenv = pythonSet.mkVirtualEnv "graphiti-mcp-server-env" workspace.deps.all;
          in
          pkgs.runCommand "graphiti-mcp-server-${system}" { } ''
            mkdir -p $out/bin
            ln -s ${virtualenv}/bin/main $out/bin/graphiti-mcp-server 2>/dev/null || true
            ln -s ${virtualenv} $out/lib
            cp -r ${./.}/* $out/lib/ 2>/dev/null || true
          '';
      });
    };
}
