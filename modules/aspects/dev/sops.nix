{ den, lib, ... }:
{
  den.aspects.sops-cli = {
    nixos = { pkgs, ... }: {
      environment.systemPackages = with pkgs; [
        sops
        age-plugin-tpm
      ];
    };
  };
}
