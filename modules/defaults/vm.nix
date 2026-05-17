/* --------------------------------------------------------------------------
  What this does:

  Allows you to run `nix run .#<hostname>` to start the VM
  for any host defined in the flake.
  --------------------------------------------------------------------------- */

{
  inputs,
  ...
}:
{
  perSystem =
    {
      pkgs,
      lib,
      ...
    }:
    let
      # Filter NixOS configurations that match the current system architecture
      hostsForSystem = lib.filterAttrs (
        _: conf: conf.pkgs.stdenv.hostPlatform.system == pkgs.stdenv.hostPlatform.system
      ) (inputs.self.nixosConfigurations or { });
    in
    {
      # we take `packages` in `perSystem` and define them as a function
      # that takes name: and conf: as arguments
      packages = lib.mapAttrs ( hostname: conf:
          pkgs.writeShellApplication {
            name = hostname;
            # Shell script content to launch the VM
            text = ''
              # Display message when starting VM
              echo "💻 Starting VM for ${hostname}"

              # Set QEMU options to allocate 8GB RAM and launch the VM
              export QEMU_OPTS="-m 8192"
              ${conf.config.system.build.vm}/bin/run-${conf.config.networking.hostName}-vm "$@"
            '';
          }
        ) hostsForSystem;
    };
}
