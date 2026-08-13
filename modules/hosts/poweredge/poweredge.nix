{ den, inputs, lib, pkgs, ... }: {
  den.aspects.poweredge = {
    includes = [
      den.aspects.server.core
      den.aspects.server.sops
      den.aspects.server.nextcloud
      den.aspects.server.nc-ocr
      den.aspects.server.immich
      den.aspects.server.evc-team-relay
      den.aspects.server.obsidian-collab
      den.aspects.server.trilium
      den.aspects.server.nc-rag
    ];

    nixos = { config, lib, pkgs, ... }: let
      # Helper script to convert a systemd-decrypted credential file
      # into a single-line env var file. Used by ExecStartPre so the
      # password never appears in Nix store or as a literal env var
      # embedded in unit files.
      ncMcpCredsToEnvScript = pkgs.writeShellScript "nc-mcp-creds-to-env" ''
        set -eu
        : "''${CREDENTIALS_DIRECTORY:?must be set by systemd}"
        install -m 0600 /dev/null /run/nextcloud-mcp.env
        printf 'NEXTCLOUD_PASSWORD=%s\n' \
          "$(cat "$CREDENTIALS_DIRECTORY/mcp-password")" \
          > /run/nextcloud-mcp.env
      '';
    in {
      imports = [
        inputs.disko.nixosModules.disko
        inputs.quadlet-nix.nixosModules.quadlet
        ./_disko.nix
        ./_hardware-configuration.nix
      ];
      nix.settings.trusted-users = [ "likivik" ];

      services.openssh = {
        enable = true;
        settings = {
          PermitRootLogin = "no";
          PasswordAuthentication = false;
        };
      };

      users.users.likivik = {
        isNormalUser = true;
        extraGroups = [ "wheel" ];
        hashedPassword = "$y$j9T$CflOiBqf7adw8VPM1HjjD0$I.UH24kDyF8m75kAe3c4pO87oujxnUah7vBIDuTetR9";
        openssh.authorizedKeys.keys = [
          # hermes@erebus
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIECMxs9cBFN8Adq8AJ9I62gVNFTkgNkr0ikg+VkWbHx1 hermes@erebus"
          # likivik@traversal
          "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
          # likivik@serenity
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
        ];
      };

      # Rootless podman was attempted (per-service users, subuid/subgid,
      # linger, sdnotify) but rootless has known issues with pasta port
      # forwarding on podman 5.x — connections accepted but immediately
      # dropped. Reverted to rootful: simpler, works. Containers run as
      # root on this single-tenant host.

      security.sudo.extraRules = [{
        users = [ "likivik" ];
        commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
      }];

      sops.secrets."nextcloud/admin-password" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "nextcloud";
        group = "nextcloud";
        mode = "0600";
      };

      sops.secrets."resend/api-key" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "nextcloud";
        group = "nextcloud";
        mode = "0600";
      };

      sops.secrets."tailscale/auth-key" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root";
        group = "root";
        mode = "0400";
      };

      sops.secrets."cloudflare/poweredge-tunnel-token" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root";
        group = "root";
        mode = "0400";
      };
      sops.secrets."nextcloud/mcp-app-password" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root";
        group = "root";
        mode = "0400";
      };
      # OAuth2 client credentials for nc-mcp. Registered via:
      #   occ oauth2:add-client nc-mcp <redirect_uri>
      # nc-mcp uses client_credentials flow against Nextcloud OAuth2 endpoint
      # (works for users with 2FA — app passwords are blocked).
      sops.secrets."nextcloud/oauth2-client-id" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root"; group = "root"; mode = "0400";
      };
      sops.secrets."nextcloud/oauth2-client-secret" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root"; group = "root"; mode = "0400";
      };

      services.tailscale.authKeyFile =
        config.sops.secrets."tailscale/auth-key".path;
      services.tailscale.extraUpFlags = lib.mkAfter [
        "--advertise-tags=tag:server,tag:exit-node"
        "--advertise-exit-node"
        "--advertise-routes=192.168.0.100/32"
        "--accept-routes"
        "--exit-node=erebus"
      ];

      systemd.services.tailscale-serve = {
        description = "Tailscale Serve — HTTPS proxy to Nextcloud + Immich";
        after = [ "tailscaled.service" "tailscaled-autoconnect.service" ];
        wants = [ "tailscaled.service" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          ${lib.getExe pkgs.tailscale} serve --bg --https=443 http://127.0.0.1:80
          ${lib.getExe pkgs.tailscale} serve --bg --https=8443 http://127.0.0.1:3001
          ${lib.getExe pkgs.tailscale} serve --bg --https=5984 http://127.0.0.1:5984
          ${lib.getExe pkgs.tailscale} serve --bg --https=8787 http://127.0.0.1:8787
        '';
      };

      services.fail2ban = {
        enable = true;
        jails.nextcloud = {
          filter = {
            Definition = {
              failregex = "^.*\"remoteAddr\":\"<HOST>\".*Login failed.*$";
              ignoreregex = "";
            };
          };
          settings = {
            enabled = true;
            backend = "auto";
            port = "80,443";
            protocol = "tcp";
            maxretry = 5;
            bantime = "86400";
            findtime = "43200";
            logpath = "/tank/nextcloud/data/nextcloud.log";
          };
        };
      };

      systemd.services.cloudflared-poweredge = {
        description = "Cloudflare Tunnel — poweredge";
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          ExecStart = "${pkgs.bash}/bin/bash -c 'exec ${pkgs.cloudflared}/bin/cloudflared tunnel --no-autoupdate --protocol http2 run --token \"$(<${config.sops.secrets."cloudflare/poweredge-tunnel-token".path})\"'";
          Restart = "on-failure";
          RestartSec = 5;
        };
      };

      # Podman 0.0.0.0:X:X publishes work; 127.0.0.1:X:X silently drops
      # packets after DNAT on this NixOS+podman. Firewall restricts the
      # published ports to loopback only (not exposed to LAN).
      # Compare erebus kokoro-tts (works, 0.0.0.0) vs falkordb (broken, 127.0.0.1).
      networking.firewall.interfaces.eno1.allowedTCPPorts = lib.mkForce [ ];
      # tailscale0: ports exposed over Tailscale for cross-host MCP access.
      # 6333/6334: qdrant HTTP+gRPC (only poweredge itself uses qdrant
      #   internally; keep for nc-rag ops + qdrant dashboard from remote).
      # 8000: nextcloud-mcp MCP endpoint (Hermes MCP client).
      # Other hosts use Tailscale magic DNS to reach
      # http://poweredge.oryx-galaxy.ts.net:8000/mcp.
      networking.firewall.interfaces.tailscale0.allowedTCPPorts = lib.mkForce [ 6333 6334 8000 ];
      networking.firewall.interfaces.lo.allowedTCPPorts = lib.mkForce [ 2000 6333 6334 8000 ];

      # Tailscale route hijack: tailscaled installs `10.88.0.0/16 dev tailscale0`
      # in its own table (52). podman0 also uses 10.88.0.0/16, so without
      # a higher-priority rule the kernel routes podman container traffic
      # to tailscale0 → silently dropped. Force the main table to handle
      # the podman subnet first. See poweredge deploy notes (Aug 2026).
      boot.kernel.sysctl."net.ipv4.conf.lo.route_localnet" = 1;
      systemd.services."podman-route-override" = {
        description = "Force 10.88.0.0/16 to use main table (podman0), not table 52 (tailscale0)";
        wantedBy = [ "multi-user.target" ];
        after = [ "tailscaled.service" "podman.service" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          ${pkgs.iproute2}/bin/ip rule add to 10.88.0.0/16 lookup main priority 100 || true
        '';
      };

      # Qdrant + nextcloud-mcp as Podman Quadlets (rootful).
      # Quadlets handle sdnotify, restart, and lifecycle natively — sidestepping
      # oci-containers module quirks. See modules/aspects/server/nc-rag/nc-rag.nix
      # for the rationale on why quadlets (Tailscale route hijack, pasta netns).
      virtualisation.quadlet = {
        enable = true;
        containers.qdrant = {
          autoStart = true;
          containerConfig = {
            # DaoCloud mirror to dodge Docker Hub unauthenticated pull rate limit.
            image = "m.daocloud.io/docker.io/qdrant/qdrant:v1.18.2";
            # --network=host: container shares host netns → qdrant listens on
            # host's 0.0.0.0:6333 directly. Sidesteps netavark bridge + DNAT bug
            # (FORWARD chain stays at 0 packets on poweredge NixOS 26.11).
            # Trade-off: "insecure" per podman docs, fine for internal RAG.
            networks = [ "host" ];
            volumes = [
              "/var/lib/qdrant/storage:/qdrant/storage"
              "/var/lib/qdrant/snapshots:/qdrant/snapshots"
            ];
            environments = {
              QDRANT__SERVICE__HOST = "0.0.0.0";
              QDRANT__TELEMETRY_DISABLED = "true";
            };
          };
          serviceConfig = { Restart = "always"; };
        };
        containers.nextcloud-mcp = {
          autoStart = true;
          containerConfig = {
            image = "ghcr.io/pi0n00r/nextcloud-mcp-server:v1.5.1.1";
            # --network=host: same rationale as qdrant (sidestep netavark DNAT bug)
            networks = [ "host" ];
            # Env vars per upstream docs (README + 'Required configuration' log).
            # Auth: Basic auth with app password. nc-mcp reads NEXTCLOUD_PASSWORD
            # as a literal string (no file:// support), so we use systemd's
            # credential mechanism to hand it the password without plaintext
            # ever living on disk:
            #   1. nc-mcp-encrypt-secret.service (oneshot, Before=nc-mcp.service)
            #      reads the sops secret at /run/secrets/nextcloud/mcp-app-password
            #      and encrypts it with systemd-creds (host-bound key in
            #      /var/lib/systemd/credential.secret), writing the blob to
            #      /run/credentials-cache/nc-mcp/mcp-password.cred
            #   2. nc-mcp.service loads that blob via LoadCredentialEncrypted=,
            #      systemd decrypts it in-memory and exposes the path at %d/mcp-password
            #   3. ExecStartPre= reads %d/mcp-password and writes a single-line
            #      KEY=VALUE env file to /run/nextcloud-mcp.env (mode 0600, tmpfs)
            #   4. EnvironmentFile= feeds it into the container as env vars
            # Note: app passwords created BEFORE 2FA enforcement get flagged
            # 'PasswordLoginForbidden' by Nextcloud's Sabre DAV. To regenerate:
            #   occ user:add-app-password likivik --name='nc-mcp'
            # (any newly-created app password works with 2FA + twofactor_enforced)
            # Vector sync: needs bge-m3 + qdrant (on serenity + local).
            environmentFiles = [ "/run/nextcloud-mcp.env" ];
            environments = {
              NEXTCLOUD_HOST = "https://poweredge.oryx-galaxy.ts.net";
              NEXTCLOUD_USERNAME = "likivik";
              MCP_DEPLOYMENT_MODE = "single_user_basic";
              # Semantic search — ENABLE_SEMANTIC_SEARCH enables Qdrant-backed
              # search. nc-mcp hardcodes Ollama client (POST /api/embed),
              # so we point at the ollama-compat proxy on serenity:11434
              # (deposist/llama.cpp-Control-Deck ollama_proxy.py translating
              # Ollama-native API → llama.cpp's OpenAI endpoints).
              # Why not llama.cpp directly? llama.cpp reverted /api/tags in
              # PR #22165 (April 2026). Why not Ollama? CVE-2026-7482 (9.1).
              # Why proxy on serenity: keeps embedder/reranker on GPU host.
              # VECTOR_SYNC_INTERVAL=60 → re-scan every 60s (default 3600s/1h).
              # Set short here so initial indexing kicks in within minutes of
              # a new note being created, instead of waiting for the next
              # hourly tick. Bump back to 3600 once indexing is healthy.
              ENABLE_SEMANTIC_SEARCH = "true";
              VECTOR_SYNC_INTERVAL = "60";
              QDRANT_URL = "http://127.0.0.1:6333";
              OLLAMA_BASE_URL = "http://serenity:11434";
              OLLAMA_EMBEDDING_MODEL = "bge-m3";
              SEARCH_MODE = "hybrid";  # dense (via Ollama/proxy) + sparse (Qdrant BM25)
            };
          };
          # systemd service config: encrypt sops secret → LoadCredentialEncrypted →
          # ExecStartPre writes env file → EnvironmentFile feeds container.
          # Helper script: convert credential file → env file.
          # Defined outside serviceConfig to keep serviceConfig pure.
          serviceConfig = {
            Restart = "always";
            # systemd decrypts the blob in-memory, exposes at
            # /run/credentials/<unit>/mcp-password
            LoadCredentialEncrypted = "mcp-password:/run/credentials-cache/nc-mcp/mcp-password.cred";
            # ExecStartPre runs the helper script defined in the let block.
            ExecStartPre = "${toString pkgs.bash}/bin/bash ${ncMcpCredsToEnvScript}";
          };
        };
      };
      # systemd-creds encrypt the sops secret at boot, write encrypted blob
      # to /run/credentials-cache/nc-mcp/. Runs BEFORE nc-mcp.service so the
      # LoadCredentialEncrypted= resolves successfully.
      systemd.services.nc-mcp-encrypt-secret = {
        description = "Encrypt nc-mcp app password with systemd-creds for nc-mcp.service";
        wantedBy = [ "multi-user.target" ];
        before = [ "nc-mcp.service" ];
        # sops-nix installs secrets via systemd activation script during boot
        # (NOT a separate systemd unit). Rely on NixOS ordering — sops secrets
        # are written to /run/secrets before any systemd unit starts.
        after = [ "local-fs.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          # Don't let anyone read the encrypted blob except root
          UMask = "0077";
        };
        script = ''
          set -e
          mkdir -p /run/credentials-cache/nc-mcp
          # - reads plaintext from sops-installed secret
          # - encrypts with host key (systemd 258+ supports this via creds setup)
          # - writes to /run/credentials-cache/nc-mcp/mcp-password.cred
          tmp=$(mktemp /tmp/nc-mcp-plain-XXXXXX.txt)
          chmod 0600 "$tmp"
          cp ${config.sops.secrets."nextcloud/mcp-app-password".path} "$tmp"
          ${pkgs.systemd}/bin/systemd-creds encrypt \
            --name=mcp-password \
            "$tmp" \
            /run/credentials-cache/nc-mcp/mcp-password.cred
          rm -f "$tmp"
        '';
      };
      # Ensure qdrant storage dirs exist (rootful quadlets: root-owned).
      system.activationScripts."nc-rag-qdrant-dirs".text = ''
        mkdir -p /var/lib/qdrant/storage /var/lib/qdrant/snapshots
        chmod 0750 /var/lib/qdrant /var/lib/qdrant/storage /var/lib/qdrant/snapshots
      '';
      # 8GB swapfile on root SSD
      swapDevices = [{
        device = "/swapfile";
        size = 8192; # 8GB
      }];

      boot.supportedFilesystems = [ "zfs" ];
      boot.zfs.forceImportRoot = false;
      boot.zfs.extraPools = [ "tank" ];
      networking.hostId = "5a099923";

      services.zfs.autoScrub.enable = true;

      services.zfs.autoSnapshot = {
        enable = true;
        frequent = 0;
        hourly = 36;
        daily = 30;
        weekly = 4;
        monthly = 3;
      };

      services.postgresqlBackup = {
        enable = true;
        startAt = "*-*-* 04:00:00";
        databases = [ "nextcloud" "immich" ];
        location = "/tank/backups/postgresql";
        compression = "gzip";
      };
    };
  };
}
