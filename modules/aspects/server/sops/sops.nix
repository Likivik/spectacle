{ inputs, den, lib, pkgs, ... }:
{
  flake-file.inputs = {
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.server.sops = {
    nixos = { pkgs, ... }: {
      imports = [ inputs.sops-nix.nixosModules.sops ];

      sops = {
        # Servers use ssh-to-age permanently — the age key is derived from
        # the host's SSH ed25519 key. No TPM migration needed.
        age.sshKeyPaths = [ "/etc/ssh/ssh_host_ed25519_key" ];
        age.plugins = [ pkgs.age-plugin-tpm ];
        defaultSopsFile = lib.mkForce null;
      };

      environment.systemPackages = [ pkgs.age ];
    };
  };
}
