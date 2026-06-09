# DO-NOT-EDIT. This file was auto-generated using github:vic/flake-file.
# Use `nix run .#write-flake` to regenerate it.
{
  outputs = inputs: inputs.flake-parts.lib.mkFlake { inherit inputs; } (inputs.import-tree ./modules);

  inputs = {
    den.url = "github:denful/den";
    determinate.url = "https://flakehub.com/f/DeterminateSystems/determinate/*";
    devshell.url = "github:numtide/devshell";
    dms-plugin-registry = {
      url = "github:AvengeMedia/dms-plugin-registry";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-file.url = "github:vic/flake-file";
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    hy3.url = "github:outfoxxed/hy3/hl0.52.0";
    hypr-dynamic-cursors.url = "github:VirtCode/hypr-dynamic-cursors/8c1679b87c54e97145cae83e622956d720e88bef";
    hyprland.url = "github:hyprwm/Hyprland/v0.52.0";
    hyprland-plugins.url = "github:hyprwm/hyprland-plugins/v0.52.0";
    import-tree.url = "github:vic/import-tree";
    ncro.url = "github:feel-co/ncro";
    nirimod = {
      url = "github:srinivasr/nirimod";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nix-maid.url = "github:viperML/nix-maid";
    nixfmt-rs.url = "github:Mic92/nixfmt-rs";
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    noctalia = {
      url = "github:noctalia-dev/noctalia-shell/v5";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    torrserver.url = "github:YouROK/TorrServer";
  };
}
