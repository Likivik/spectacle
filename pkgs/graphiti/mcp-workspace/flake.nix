{
  description = "graphiti-mcp-server (uv2nix workspace, pinned to commit 526dcad7)";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
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
      uvLockedOverlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

      projectName = "mcp-server";  # matches [project.name] in pyproject.toml

      pythonSets = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python3;
        in
        (pkgs.callPackage pyproject-nix.build.packages { inherit python; })
          .overrideScope (lib.composeManyExtensions [
            pyproject-build-systems.overlays.default
            uvLockedOverlay
            (final: prev: {
              # Replace graphiti-core + falkordb-py with our vendored Nix builds.
              graphiti-core = pkgs.python3Packages.callPackage ../core.nix {
                falkordb-py = pkgs.python3Packages.callPackage ../falkordb-py.nix { };
              };
              falkordb-py = pkgs.python3Packages.callPackage ../falkordb-py.nix { };
            })
          ])
      );

      envs = forAllSystems (system: {
        default = pythonSets.${system}.mkVirtualEnv "${projectName}-env" workspace.deps.default;
        all = pythonSets.${system}.mkVirtualEnv "${projectName}-env-all" workspace.deps.all;
      });
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          env = envs.${system}.default;
          app = envs.${system}.all;  # incl. all optional / dev deps
        in
        {
          default = self.packages.${system}.graphiti-mcp;
          graphiti-mcp = pkgs.stdenv.mkDerivation {
            pname = "graphiti-mcp-server";
            version = "1.0.2+526dcad";
            src = ./.;

            nativeBuildInputs = [ pkgs.makeWrapper ];
            buildInputs = [ app ];

            installPhase = ''
              mkdir -p $out/bin
              cp ${./main.py} $out/bin/main
              chmod +x $out/bin/main
              makeWrapper ${app}/bin/python $out/bin/graphiti-mcp-server \
                --add-flags $out/bin/main
              ln -s $out/bin/graphiti-mcp-server $out/bin/mcp-server
            '';
          };
        });
    };
}
