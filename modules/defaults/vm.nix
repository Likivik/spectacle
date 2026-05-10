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
    {
      # we take `packages` in `perSystem` and define them as a function
      # that takes name: and conf: as arguments
      packages = lib.mapAttrs ( name: conf:
          pkgs.writeShellApplication {
            name = name;
            # Shell script content to launch the VM
            text = ''
              # Display message when starting VM
              echo "💻 Starting VM for ${name}"

              # Set QEMU options to allocate 8GB RAM and launch the VM
              export QEMU_OPTS="-m 8192"
              ${conf.config.system.build.vm}/bin/run-${conf.config.networking.hostName}-vm "$@"
            '';
          }
        ) inputs.self.nixosConfigurations;
    };
}
