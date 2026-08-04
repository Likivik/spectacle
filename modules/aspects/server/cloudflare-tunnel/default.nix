{ den, inputs, lib, pkgs, ... }:

# ─── Cloudflare Tunnel (podman) ─────────────────────────────────────
# The cloudflared system user and sops secret are declared in
# hosts/poweredge/poweredge.nix so they can be referenced by the
# systemd.services.cloudflared-poweredge unit (which uses the NixOS
# cloudflared package directly, not the container).
#
# This aspect additionally runs the upstream cloudflared container
# as a rootless podman-managed service for users who want the
# container variant. The sops secret is shared.
{
  den.aspects.server.cloudflare-tunnel = {
    nixos = { config, lib, pkgs, ... }: {
      virtualisation.oci-containers = {
        backend = lib.mkDefault "podman";
        containers.cloudflared = {
          image = "cloudflare/cloudflared:latest";
          autoStart = true;
          podman.user = "cloudflared";   # rootless; per-service user
          cmd = [ "tunnel" "run" ];
          environmentFiles = [ config.sops.secrets."cloudflare/poweredge-tunnel-token".path ];
          ports = [ "127.0.0.1:2000:2000" ];
        };
      };

      virtualisation.podman.enable = lib.mkDefault true;
    };
  };
}
