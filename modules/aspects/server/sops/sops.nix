{ inputs, den, lib, pkgs, ... }:
{
  flake-file.inputs = {
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.server.sops = {
    nixos = { ... }: {
      imports = [ inputs.sops-nix.nixosModules.sops ];

      sops = {
        # Bootstrap: use the vps's host SSH key (ssh-to-age).
        # After first boot, a TPM identity can be created and this
        # can be swapped to:
        #   age.keyFile = "/var/lib/sops/tpm-identity.txt";
        #   age.plugins = [ pkgs.age-plugin-tpm ];
        age.sshKeyPaths = [ "/etc/ssh/ssh_host_ed25519_key" ];
        age.plugins = [ pkgs.age-plugin-tpm ];
        defaultSopsFile = lib.mkForce null;
      };
    };
  };
}
