
At this point I have only dealt with NixOS, HomeManager.
Not sure if this would work simillarly on darwin or wsl or other Linux.

After adding new function, aspect, file, module you likely need to do the following:
```bash
# 1. Make sure file is tracked, otherwise flake will miss it
# sloppy but quick way:
git add -A && git commit -m "Your message here"

# 2. Actually write your changes into the flake.nix file
# It will add your new inputs and expose outputs (for steps 4,5 to work for example)
nix run .#write-flake

# 3. Make sure newly added sources (inputs) are fetched from the internets.
nix flake update # or nix flake update den -> 'den' can be any other input

# 4. I like to check validity of my changes by using --dry-run
nix build .#vm --dry-run

# 5. Start the virtual machine by .#name
nix run .#vm
```

nix run .#write-flake && nix flake update && nix build .#vm --dry-run





## VMs for testing:

We can use built-in VM builder `build-vm` for testing our configurations before applying to hardware or remote host.

The built-in VM builder is explicitly designed to answer the question: "If I apply this exact configuration to my real hardware, what will the OS look like?"

Zero Configuration Needed: You don't have to change your host configuration at all. You just write your physical host config, and the builder automatically wraps it in a QEMU script.

Hardware Mocking: It safely stubs out the physical stuff (like your bootloader and physical file systems) and replaces them with a virtual disk for the test run, while keeping all your UI, users, aspects, and packages exactly as they will be on the real machine.

### How to do it manually:
```bash
# This builds the VM for the host
nixos-rebuild build-vm --flake .#yourhostname

# This runs the VM (it creates a virtual disk file in your current directory)
./result/bin/run-yourhostname-vm
# Size is not huge - GNOME desktop with core apps and firefox would be around 300MiB
```

### You can apply various QEMU options like so:
```bash
# If you just want to test it once and throw away the disk state when you close the window, you can run
QEMU_OPTS="-snapshot" ./result/bin/run-yourhostname-vm

# Change the amount of available memory (so the vm is more responsive for GUI session)
QEMU_OPTS="-m 8192" ./result/bin/run-yourhostname-vm
```

For more options:
[QEMU manpages](https://www.qemu.org/docs/master/system/qemu-manpage.html)
### Automating creation of test VMs
You can start by writing a simple version for just a single host:
```bash
{ inputs, den, ... }:
{
  # This enables autologin for specific user on specific host (through Den battery)
  den.aspects.yourHostname.includes = [
    (den.provides.tty-autologin "yourUser")
  ];

  perSystem =
    { pkgs, ... }:
    {
    # Here we simply create a shell script that combines and runs the
    # commands we learned in the previous sections
      packages.vm = pkgs.writeShellApplication {
        # Selecting a name by which we will `nix run .#yourHostnameVM
        name = "yourHostnameVm"; # -> or make it whatever you want
        # As name suggests - the actual text of the script
        text =
        # we keep the ability to use `let` `in` blocks
          let
            host = inputs.self.nixosConfigurations.spectacle.config;
          in
          ''
            export QEMU_OPTS="-m 8192 ''${QEMU_OPTS:-}"
            ${host.system.build.vm}/bin/run-${host.networking.hostName}-vm "$@"
          '';
          # This part between '' is the actual script
          # it sets ram to 8GB and does some ensurance that options get
          # passed throug correctly
          # Then just finds the ./result and runs /bin/
          # run-yourHostname-vm
      };
    };
}
```

