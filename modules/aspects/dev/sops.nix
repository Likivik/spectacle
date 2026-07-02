{ den, lib, ... }:
{
  den.aspects.sops-cli = {
    nixos = { pkgs, ... }: {
      environment.systemPackages = with pkgs; [
        sops
        age-plugin-tpm
      ];

      # sops runs as root (for TPM device access). Preserve env vars
      # set by direnv through `sudo` so the user doesn't need to
      # pass them explicitly.
      security.sudo.extraConfig = ''
        Defaults env_keep += "SOPS_AGE_KEY_FILE SOPS_CONFIG"
      '';
    };
  };
}
