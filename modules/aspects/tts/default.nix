{ den, lib, ... }:
{
  den.aspects.tts = {
    nixos = { config, pkgs, lib, ... }: {
      virtualisation.podman.enable = lib.mkDefault true;
      virtualisation.oci-containers = {
        backend = lib.mkDefault "podman";
        containers = {
          kokoro-tts = {
            image = "ghcr.io/remsky/kokoro-fastapi-cpu:v0.6.0";
            autoStart = true;
            # Bind on all interfaces so Tailscale clients (browser-side TTS fetch)
            # can reach it; firewall restricts to tailscale0 only.
            ports = [ "0.0.0.0:8880:8880" ];
            volumes = [ "kokoro-models:/app/data" ];
            # oci-containers emits --rm by default; do NOT add --restart here
            # (it conflicts with --rm and fails the unit). Systemd restarts
            # the generated unit if the container exits.
            extraOptions = [ "--pull=newer" ];
          };
        };
      };
    };
  };
}
