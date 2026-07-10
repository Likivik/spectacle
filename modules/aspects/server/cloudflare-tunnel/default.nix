{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.cloudflare-tunnel = {
    nixos = { config, lib, pkgs, ... }: {
      virtualisation.oci-containers = {
        backend = lib.mkDefault "podman";
        containers.cloudflared = {
          image = "cloudflare/cloudflared:latest";
          autoStart = true;
          cmd = [ "tunnel" "run" ];
          environmentFiles = [ config.sops.secrets."cloudflare/tunnel-token".path ];
          ports = [ "127.0.0.1:2000:2000" ];
        };
      };

      virtualisation.podman.enable = lib.mkDefault true;
    };
  };
}
