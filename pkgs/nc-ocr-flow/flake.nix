{
  description = "nc-ocr-flow (uv2nix workspace)";

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

  outputs = { self, nixpkgs, pyproject-nix, uv2nix, pyproject-build-systems, ... }:
    let
      inherit (nixpkgs) lib;
      forAllSystems = lib.genAttrs lib.systems.flakeExposed;
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
      uvLockedOverlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
        dependencies = workspace.deps.default;
      };
      projectName = "nc-ocr-flow";
      pythonSets = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
            python = pkgs.python313;
        in (pkgs.callPackage pyproject-nix.build.packages { inherit python; })
            .overrideScope (lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              uvLockedOverlay
            ]));
    in {
      packages = forAllSystems (system: {
        # mkVirtualEnv bundles the project's deps into a single Python
        # site-packages tree so the entry-point script can resolve
        # `import pikepdf` etc. without callers needing to set PYTHONPATH.
        ${projectName} = pythonSets.${system}.mkVirtualEnv projectName { ${projectName} = [ ]; };
      });
      apps = forAllSystems (system: {
        ${projectName} = {
          type = "app";
          program = "${self.packages.${system}.${projectName}}/bin/nc-ocr-flow";
        };
      });
    };
}
