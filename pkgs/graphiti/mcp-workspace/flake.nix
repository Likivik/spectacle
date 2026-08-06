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

      uvLockedOverlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      # Per uv2nix docs (overriding-build-systems.html): uv doesn't lock
      # build systems. Use `resolveBuildSystem` to inject build backend
      # deps for any package being built from sdist. Without this, packages
      # break with ModuleNotFoundError on hatchling/meson-py/setuptools.
      # Pattern: mapAttrs to overrideAttrs, adding nativeBuildInputs.
      # (https://pyproject-nix.github.io/uv2nix/patterns/overriding-build-systems.html)
      buildSystemOverrides = final: prev: let
        inherit (final) resolveBuildSystem;
        inherit (builtins) mapAttrs;
        # Per-package spec: { <build-backend> = [optional-extras] }
        # Examples below cover common build backends seen in mcp_server's
        # transitive deps; extend as uv.lock grows.
        specs = {
          attrs = { hatchling = [ ]; };
          falkordb = { hatchling = [ ]; hatch-vcs = [ ]; };
          graphiti-core = { hatchling = [ ]; hatch-fancy-pypi-readme = [ ]; };
          markupsafe = { setuptools = [ ]; };
          numpy = { meson-python = [ ]; ninja = [ ]; };
          jinja2 = { setuptools = [ ]; };
          pyyaml = { setuptools = [ ]; cython = [ ]; };
          cffi = { setuptools = [ ]; };
          cryptography = { setuptools = [ ]; };
          brotli = { setuptools = [ ]; };
          pyasn1 = { setuptools = [ ]; };
          rust-python = { setuptools = [ ]; };
          certifi = { setuptools = [ ]; };
          pydantic = { hatchling = [ ]; };
          packaging = { flit-core = [ ]; };
          python-dotenv = { hatchling = [ ]; };
          charset-normalizer = { hatchling = [ ]; };
        };
      in mapAttrs (name: spec:
        prev.${name}.overrideAttrs (old: {
          nativeBuildInputs = (old.nativeBuildInputs or [ ])
            ++ resolveBuildSystem spec;
        })
      ) specs;

      # Apply PR #1500 patch to graphiti-core (sdist build).
      pyprojectOverrides = final: prev: {
        graphiti-core = prev.graphiti-core.overrideAttrs (old: {
          patches = (old.patches or [ ]) ++ [
            ../patches/edge-search.patch
          ];
          patchFlags = (old.patchFlags or [ ]) ++ [ "-p1" ];
        });
      };

      projectName = "mcp-server";

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
            buildSystemOverrides
            pyprojectOverrides
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
          app = envs.${system}.all;
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
