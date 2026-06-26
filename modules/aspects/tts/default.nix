{ den, lib, ... }:
{
  den.aspects.tts = {
    nixos = { config, pkgs, ... }: {
      virtualisation.oci-containers = {
        backend = lib.mkDefault "podman";
        containers = {
          kokoro-tts = {
            image = "ghcr.io/remsky/kokoro-fastapi-cpu:v0.2.0post4";
            autoStart = true;
            ports = [ "127.0.0.1:8880:8880" ];
            volumes = [ "kokoro-models:/app/data" ];
            extraOptions = [
              "--pull=newer"
            ];
          };
        };
      };
    };
  };
}
