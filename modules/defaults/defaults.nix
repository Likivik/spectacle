# This file: nixos default stuffs
{ inputs, den, lib, pkgs, ... }:
let
  # Register graphiti-mcp (built by uv2nix sub-flake from uv.lock) as
  # `pkgs.graphiti-mcp` so every NixOS-aspect can reference it directly.
  graphitiMcpOverlay = (final: prev: {
    graphiti-mcp = inputs.graphiti-mcp-workspace.packages.x86_64-linux.graphiti-mcp;
  });
in
{
  /* ------------------------------------------------------------------------
                                      NixOS
    ------------------------------------------------------------------------- */
  den.default.nixos.system.stateVersion = "25.11"; # set Nixpkgs version you start with, never change for proper backward compatability
  den.default.networking.firewall.enable = true; # enable firewall everywhere
  den.default.os.nixpkgs.overlays = [ graphitiMcpOverlay ];

  # VM resources belong on the build-vm variant, NOT on the host config:
  # virtualisation/build-vm.nix imports qemu-vm.nix only inside
  # `virtualisation.vmVariant`, so a host-level `virtualisation.memorySize` does
  # not exist (nixpkgs#196755). Setting memorySize here feeds BOTH the `-m` flag
  # and the memfd shared-memory backend, which QEMU requires to match - which is
  # why the old `QEMU_OPTS="-m 8192"` launcher flag aborted the VM outright.
  # mkDefault so a RAM-tight host can override downwards.
  den.default.nixos.virtualisation.vmVariant.virtualisation = {
    memorySize = lib.mkDefault 8192;
    cores = lib.mkDefault 4;
  };
	flake.den = den;

  /* ------------------------------------------------------------------------
                                  Home manager
    ------------------------------------------------------------------------- */

  den.default.homeManager.home.stateVersion = "25.11"; # Set HM version with which you started, never change for proper backward compatability
  den.schema.user.classes = lib.mkDefault [ "homeManager" "maid" ]; # enable HM class for every user by default

  # hm-host schema: includes are resolved as aspects for any host with HM users.
  # nixos blocks here apply system-wide to all HM-enabled hosts.
  den.schema.hm-host.includes = [
    {
      nixos = {
        home-manager.useGlobalPkgs = true;
        home-manager.useUserPackages = true;
        home-manager.backupFileExtension = "backup";
        # HM's wayland module creates systemd tray.target that conflicts with
        # NixOS-managed ~/.config/systemd/user/ (read-only store symlink).
        # Override here for all users. No HM services depend on tray.target.
        home-manager.sharedModules = [
          { systemd.user.targets = lib.mkForce {}; }
        ];
      };
    }
  ];


  den.schema.user.includes = [
    den.provides.host-aspects
  ];

  den.default.includes = [
    /* ------------------------------ Den Batteries ----------------------------- */
    den.provides.hostname # TODO: ??? this Automatically sets hostname, but isn't it already automatically set as per host schema?
    den.provides.define-user # Automatically create users + their homes, by just adding them to hosts
    /* --------------------------------- Aspects -------------------------------- */


  ];

}
