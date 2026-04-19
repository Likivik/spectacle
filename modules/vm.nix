# enables `nix run .#vm`. it is very useful to have a VM
# you can edit your config and launch the VM to test stuff
# instead of having to reboot each time.
{ inputs, den, ... }:
{
  # USER TODO: remove this tty-autologin used for the VM
  den.aspects.spectacle.includes = [ 
    # (den.provides.tty-autologin "watcher")
    den.aspects.determinate
    ];

  perSystem =
    { pkgs, ... }:
    {
      packages.vm = pkgs.writeShellApplication {
        name = "vm";
          # TODO make it work for other hosts?
          # or better said I want the ......spectacle.... be based on input of
          # `nix run .#vm` command !TODO: look it up
          # ---> would be niccccce to have it interactive with and ability to list 
          # available hosts/vms
        text =
          let
            host = inputs.self.nixosConfigurations.spectacle.config;
          in
          ''
            ${host.system.build.vm}/bin/run-${host.networking.hostName}-vm "$@"
          '';
      };
    };
}