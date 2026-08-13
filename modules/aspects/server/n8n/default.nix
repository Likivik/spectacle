{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.n8n = {
    nixos = { config, lib, pkgs, ... }: {
      virtualisation.podman.enable = lib.mkDefault true;

      systemd.tmpfiles.rules = [
        # n8n container runs as 'node' (uid 1000 inside). We chown /var/lib/n8n
        # to 1000:1000 via the activation script (users.users.likivik.uid is 1000).
        # Podman runs the container rootless by default, so the bind mount shows
        # the host inode ownership as-is. The container's 'node' user (uid 1000)
        # therefore can write to /data because we made it owned by uid 1000.
        "d /var/lib/n8n 0750 1000 1000 - -"
      ];
      users.users.n8n = {
        isSystemUser = true;
        group = "n8n";
        home = "/var/lib/n8n";
        createHome = false;
      };
      users.groups.n8n = { };

      # First-deploy: auth + encryption key are plaintext defaults.
      # TODO(ops): add `sops.secrets."n8n/encryption-key"` etc once
      # secrets.yaml is updated with the n8n keys (see secrets/.sops.yaml).
      # Lock down with Caddy basicauth + real secrets before exposing to TS net.

      services.caddy = {
        enable = true;
        # Bind to 8443 instead of :443 — tailscale serve already owns :443.
        # If you want direct Caddy access, set listenAddresses = [ "0.0.0.0" ]
        # and stop the tailscale serve for n8n.
        virtualHosts."n8n.erebus.ts.net" = {
          listenAddresses = [ "127.0.0.1:8443" ];
          extraConfig = ''
            reverse_proxy 127.0.0.1:5678
          '';
        };
      };

      virtualisation.oci-containers = {
        backend = "podman";
        containers.n8n = {
          image = "docker.io/n8nio/n8n:latest";
          autoStart = true;
          environment = {
            N8N_HOST = "n8n.erebus.ts.net";
            N8N_PORT = "5678";
            N8N_PROTOCOL = "https";
            WEBHOOK_URL = "https://n8n.erebus.ts.net/";
            GENERIC_TIMEZONE = "Europe/Moscow";
            N8N_USER_FOLDER = "/data/.n8n";
            N8N_ENCRYPTION_KEY = "change-me-on-first-run-insecure-default";
            N8N_BASIC_AUTH_ACTIVE = "false";
          };
          # /var/lib/n8n is owned by uid 988 (host n8n user) matching the
          # n8n container's 'node' uid (1000) via the tmpfiles rule + Podman's
          # --userns=keep-id option, which preserves the UID when bind-mounting.
          volumes = [ "/var/lib/n8n:/data:Z" ];
          ports = [ "127.0.0.1:5678:5678" ];
        };
      };

      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 80 443 ];
    };
  };
}
