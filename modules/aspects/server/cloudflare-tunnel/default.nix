{ den, inputs, lib, pkgs, ... }:

# ─── Cloudflare Tunnel (podman rootful) ─────────────────────────────
# Rootful: container runs as root. Simpler, reliable port forwarding,
# matches the rest of the poweredge stack.
# sops secret is declared in hosts/poweredge/poweredge.nix (root:root).
{
  den.aspects.server.cloudflare-tunnel = {
    nixos = { config, lib, pkgs, ... }: {
      virtualisation.oci-containers = {
        backend = lib.mkDefault "podman";
        containers.cloudflared = {
          image = "cloudflare/cloudflared:latest";
          autoStart = true;
          cmd = [ "tunnel" "run" ];
          environmentFiles = [ config.sops.secrets."cloudflare/poweredge-tunnel-token".path ];
          ports = [ "127.0.0.1:2000:2000" ];
        };
      };

      virtualisation.podman.enable = lib.mkDefault true;
    };
  };
}