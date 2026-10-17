{ den, inputs, lib, pkgs, ... }: {
  den.aspects.poweredge = {
    includes = [
      den.aspects.server.core
      den.aspects.server.sops
      den.aspects.server.nextcloud
      # nc-ocr disabled — superseded by workflow_ocr app (R0Wi-DEV) +
      # ocrmypdf in systemPackages. Module kept on disk for history;
      # can be deleted after workflow-ocr is verified.
      # den.aspects.server.nc-ocr
      den.aspects.server.workflow-ocr
      den.aspects.server.immich
      # immich-nc-bridge disabled — requires Extism WASM rewrite + real npm deps hash.
      # Re-enable once plugin SDK integration lands.
      # den.aspects.server.immich-nc-bridge
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
          # hermes@serenity — the agent running on serenity deploys this host
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAxgjvMCf4tUu9geCOifsHdlMK9md9D0ykkcxca47WeD hermes@serenity-flip-2026-10-05"
          # likivik@traversal
          "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
          # likivik@serenity
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
        ];
      };

      # Low-privilege receiver for serenity's Forgejo backups (forgejo dump →
      # rsync'd over the tailnet). Intentionally NOT nologin: rsync needs a real
      # shell for its remote trampoline. Security = no sudo + `restrict` on the
      # key (no agent/pty/port-forward) + $HOME locked to
      # /tank/backups/serenity/forgejo. So this user CAN get an interactive
      # shell, but only as an unprivileged user with nothing writable outside its
      # home. Acceptable for a homelab; add a forced `command=` for hard restriction.
      users.users.forgejo-backup = {
        isSystemUser = true;
        group = "forgejo-backup";
        home = "/tank/backups/serenity/forgejo";
        # rsync needs a real shell to run its remote server trampoline (nologin
        # breaks it). Security is kept via: no sudo, `restrict` on the key, and
        # home locked to the backup dir.
        shell = "/run/current-system/sw/bin/bash";
        openssh.authorizedKeys.keys = [
          # forgejo user on serenity (pushed forgejo dumps nightly); `restrict`
          # disables agent/port-forwarding/pty. Writable only in its home.
          "restrict ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC7qnde9dh/4V4fJ7WyMAVDt2Tl0Ylx2VpUthWB7BVmj forgejo-backup@serenity"
        ];
      };
      users.groups.forgejo-backup = { };

      # Rootless podman was attempted (per-service users, subuid/subgid,
      # linger, sdnotify) but rootless has known issues with pasta port
      # forwarding on podman 5.x — connections accepted but immediately
      # dropped. Reverted to rootful: simpler, works. Containers run as
      # root on this single-tenant host.

      security.sudo.extraRules = [{
        users = [ "likivik" ];
        commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
      }];

      # Provision secrets through systemd rather than the activation script.
      # The activation script runs before systemd exists, which is the ordering
      # gap behind issue #2. With this set, sops-nix generates
      # sops-install-secrets.service (wantedBy sysinit.target) and applies
      # rotations with `systemctl try-restart` instead of writing an
      # activation-restart list.
      #
      # erebus deliberately does NOT set this. It has seven activation scripts
      # written as `stringAfter [ setupSecrets ]`, and setupSecrets is
      # `mkIf (regularSecrets != {} && !useSystemdActivation)` — so flipping the
      # flag there would silently unanchor them, and hermes-secrets-env would
      # write an env file with empty values for every token.
      sops.useSystemdActivation = true;

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
        # No restartUnits, deliberately. The four workflow-ocr units bind this as a
        # LoadCredential but their scripts never read it — verified: zero references
        # to $CREDENTIALS_DIRECTORY/mail_smtppassword in any of them. The real
        # consumer is Nextcloud's own mail, which reads the secret per PHP request
        # via nix_read_secret, so a rotation takes effect without a restart.
      };

      sops.secrets."tailscale/auth-key" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root";
        group = "root";
        mode = "0400";
        # tailscaled-autoconnect only runs `tailscale up --auth-key ...` when the
        # daemon is in NeedsLogin/NeedsMachineAuth/Stopped, so a rotated key is
        # ignored while it stays Connected. Restarting tailscaled forces that cycle.
        restartUnits = [ "tailscaled.service" ];
      };

      sops.secrets."cloudflare/poweredge-tunnel-token" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root";
        group = "root";
        mode = "0400";
        # Without this, a rebuild writes the new token to /run but the running
        # cloudflared keeps the OLD one in memory — it reads the token once at
        # ExecStart. So a rotated tunnel token would silently not take effect
        # until someone restarted the unit by hand. Discovered while rotating the
        # token after it leaked in secrets/poweredge/secrets.yaml.tmp.
        restartUnits = [ "cloudflared-poweredge.service" ];
      };
      sops.secrets."nextcloud/mcp-app-password" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root";
        group = "root";
        mode = "0400";
        # Read once at unit start by the quadlet's ExecStartPre helper, which cats
        # the credential into /run/nextcloud-mcp.env (the container's
        # EnvironmentFile). Without this the container keeps the old password.
        restartUnits = [ "nextcloud-mcp.service" ];
      };
      sops.secrets."nextcloud/ocr-webhook-secret" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "nextcloud"; group = "nextcloud"; mode = "0400";
        # Three consumers, none of which re-read on their own: the occ
        # config:system:set ocrflow_secret in nextcloud-setup.service.postStart
        # (whose nixpkgs restartTriggers only cover overrideConfig), plus
        # LoadCredential in nc-ocr-webhook and nc-ocr-register-webhook.
        restartUnits = [ "nextcloud-setup.service" "nc-ocr-webhook.service" "nc-ocr-register-webhook.service" ];
      };
      sops.secrets."nextcloud/ocr-webdav-password" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "nextcloud"; group = "nextcloud"; mode = "0400";
        # LoadCredential nc-ocr-password in nc-ocr-webhook (WebDAV auth as likivik),
        # read once at process start.
        restartUnits = [ "nc-ocr-webhook.service" ];
      };
      sops.secrets."nextcloud/minimax-api-key" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "nextcloud"; group = "nextcloud"; mode = "0400";
        # Was declared but wired to nothing: the engine reads NC_OCR_MINIMAX_KEY or
        # NC_OCR_MINIMAX_KEY_FILE (minimax_engine.py:290,293) and the service set
        # neither, so the minimax engine had no credential at all. Now bound as a
        # LoadCredential in nc-ocr-webhook and exported by the start script. The
        # engine is opt-in (NC_OCR_ENGINE=google), so this is inert until selected.
        restartUnits = [ "nc-ocr-webhook.service" ];
      };
      # Google Cloud Vision service-account JSON key (whole-doc OCR engine).
      # Project spectacle-xandria; SA ocr-worker@spectacle-xandria.iam.gserviceaccount.com.
      sops.secrets."nextcloud/ocr-google-key" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "nextcloud"; group = "nextcloud"; mode = "0400";
        # LoadCredential google-ocr-key in nc-ocr-webhook, exported as
        # GOOGLE_APPLICATION_CREDENTIALS, read once at process start.
        restartUnits = [ "nc-ocr-webhook.service" ];
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
          ${lib.getExe pkgs.tailscale} serve --bg --https=8787 http://127.0.0.1:8787
        '';
      };

      # Netmap guard now lives in the shared core.tailscale aspect
      # (modules/aspects/core/tailscale.nix) so every host recovers from a lost
      # netmap, not just this one.

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
        # Every other consumer of a sops secret on this host reads it through
        # LoadCredential, which carries an implicit Requires=/After= on the
        # source path. This unit instead substitutes the token with `$(<path)`
        # in ExecStart, so it has no implicit ordering — and under
        # useSystemdActivation the secrets are placed by a systemd unit rather
        # than by activation, so the edge has to be explicit or the first start
        # reads an empty file. Conditional so it stays correct if the flag is
        # ever turned back off: a Requires= on a nonexistent unit fails the unit.
        after = [ "network-online.target" ]
          ++ lib.optionals config.sops.useSystemdActivation [ "sops-install-secrets.service" ];
        wants = [ "network-online.target" ];
        requires = lib.optionals config.sops.useSystemdActivation [ "sops-install-secrets.service" ];
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
      # 22: SSH — CRITICAL. a8cafce (2026-08-05) closed all tailscale0 ports
      #   with mkForce [], and e871f23 reopened only 6333/6334/8000, forgetting
      #   22. SSH then only worked because tailscaled kept its old iptables
      #   state; the 2026-09-02 flake-update deploy restarted the firewall and
      #   locked every host out of poweredge (physical reboot required).
      # 6333/6334: qdrant HTTP+gRPC (only poweredge itself uses qdrant
      #   internally; keep for nc-rag ops + qdrant dashboard from remote).
      # 8000: nextcloud-mcp MCP endpoint (Hermes MCP client).
      # Other hosts use Tailscale magic DNS to reach
      # http://poweredge.oryx-galaxy.ts.net:8000/mcp.
      networking.firewall.interfaces.tailscale0.allowedTCPPorts = lib.mkForce [ 22 6333 6334 8000 ];
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
            # pi0n00r/nextcloud-mcp-server — hardened fork of cbcoutinho.
            # Bridgette v1.9.9.3 (2026-10-10, f9f595f). Multi-arch image-index
            # digest pins to an immutable OCI manifest list so a same-tag
            # rebuild cannot silently swap the running image:
            #   sha256:fb4833666580ba996437c93b7775cb28c87e978399e4e3c2b83c6f86d6e093b4
            # (amd64 sha256:1fc77279052502d7b79e9e4c1b7df2582b563e755fae1af3bd57ca35245006d1
            #  arm64 sha256:b8d104a2f76fed5fa2a0f59f444ce0e25f85ac47f4be2ea78f4295a9f8d30fc7)
            # Release notes: https://github.com/pi0n00r/nextcloud-mcp-server/releases/tag/v1.9.9.3
            image = "ghcr.io/pi0n00r/nextcloud-mcp-server:v1.9.9.3@sha256:fb4833666580ba996437c93b7775cb28c87e978399e4e3c2b83c6f86d6e093b4";
            # --network=host: same rationale as qdrant (sidestep netavark DNAT bug)
            networks = [ "host" ];
            # Env vars per upstream docs (README + 'Required configuration' log).
            # Auth: Basic auth with app password. nc-mcp reads NEXTCLOUD_PASSWORD
            # as a literal string (no file:// support), so we use systemd's
            # LoadCredential= (below): systemd binds the sops secret at
            # /run/secrets/nextcloud/mcp-app-password into
            # CREDENTIALS_DIRECTORY/mcp-password at unit start, then
            #   1. ExecStartPre= reads %d/mcp-password and writes a single-line
            #      KEY=VALUE env file to /run/nextcloud-mcp.env (mode 0600, tmpfs)
            #   2. EnvironmentFile= feeds it into the container as env vars
            # Note: app passwords created BEFORE 2FA enforcement get flagged
            # 'PasswordLoginForbidden' by Nextcloud's Sabre DAV. To regenerate:
            #   occ user:add-app-password likivik --name='nc-mcp'
            # (any newly-created app password works with 2FA + twofactor_enforced)
            # Vector sync: needs bge-m3 + qdrant (on serenity + local).
            environmentFiles = [ "/run/nextcloud-mcp.env" ];
            environments = {
              # Container uses Network=host, so localhost reaches nginx directly.
              # Tailscale-serve terminates TLS on the tailnet IP, not localhost —
              # using https:// from inside the container breaks (SSL wrong version).
              NEXTCLOUD_HOST = "http://127.0.0.1:80";
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
              ENABLE_SEMANTIC_SEARCH = "true";
              QDRANT_URL = "http://127.0.0.1:6333";
              OLLAMA_BASE_URL = "http://serenity:11434";
              OLLAMA_EMBEDDING_MODEL = "bge-m3";
              SEARCH_MODE = "hybrid";  # dense (via Ollama/proxy) + sparse (Qdrant BM25)

              # --- Vector-sync tuning ---------------------------------------
              # NB: the correct env-var name is VECTOR_SYNC_SCAN_INTERVAL, NOT
              # VECTOR_SYNC_INTERVAL — the latter is silently ignored (upstream
              # docs/configuration.md and env.sample). The deploy previously
              # set VECTOR_SYNC_INTERVAL=60, which v1.5.1.1 ignored and fell
              # back to the (then 3600s) default. v1.9.x tightened the default
              # to 300s. Keep 60s for snappy indexing on this small instance;
              # bump to 300+ once steady-state.
              VECTOR_SYNC_SCAN_INTERVAL = "60";
              # --- File indexing tags ---------------------------------------
              # VECTOR_SYNC_TAG / VECTOR_SYNC_KEYWORD_TAG name the two system
              # tags the file scanner matches against. Defaults are
              # `vector-index` (hybrid) and `keyword-index` (BM25-only) — set
              # explicitly here so a future upstream rename doesn't silently
              # change behaviour. Both tags are *on* by default; either one,
              # applied to a file OR a folder (folder tag recursively selects
              # descendants), is sufficient. Hybrid wins if both are present.
              # See docs/configuration.md §"Per-document keyword vs hybrid".
              #
              # To make the ENTIRE Nextcloud tree searchable, the operator
              # must create both tags once and apply `vector-index` at the
              # tree root. The server cannot do that for itself:
              #   occ systemtag:add vector-index --visibility visible --assignable
              #   occ systemtag:add keyword-index --visibility visible --assignable
              #   # Then in the Nextcloud UI or via WebDAV: apply vector-index
              #   # to /<user>/files/ (the tag inherits down).
              VECTOR_SYNC_TAG = "vector-index";
              VECTOR_SYNC_KEYWORD_TAG = "keyword-index";
              # EXCLUDED_TAGS — tag-based file/folder exclusion (issue #710,
              # PR #765 in v1.9.x). Comma-separated list of system-tag names
              # whose tagged files / folders are hidden from EVERY WebDAV MCP
              # tool — listings, reads, writes, deletes, moves, copies, search.
              # A folder tag recursively excludes everything beneath it via
              # path-prefix match. The vector-sync scanner also honors this
              # set (PR #765): a file tagged `vector-exclude` is NOT
              # indexed even if it sits under a folder tagged `vector-index`.
              # Default: empty (feature off). Setting the env var to a tag
              # name that does not exist in Nextcloud is a no-op, so it is
              # safe to ship the config ahead of `occ systemtag:add`.
              # Threat model: create the tag --user-assignable=false so
              # users cannot bypass the exclusion by removing the tag from a
              # file in the WebUI. The tag itself is created manually:
              #   occ systemtag:add vector-exclude \
              #     --visibility visible --assignable false
              EXCLUDED_TAGS = "vector-exclude";
              # --- Multi-format indexing (v1.9.5+) ---------------------------
              # v1.5.1.1 hard-coded a PDF-only MIME filter inside the file
              # scanner; with no PDF files tagged, the Qdrant collection
              # stayed at 0 file points (the reason nothing was indexed).
              # v1.9.5 added native DOCX/PPTX/XLSX readers (ADR-036/038) and
              # v1.9.8.3 expanded tagged-file discovery to "every type an
              # enabled processor can read" by default — PDF, DOCX, XLSX,
              # PPTX, plain text, Markdown, CSV, Outlook .msg are all picked
              # up under a `vector-index` system tag with no env var.
              #
              # VECTOR_SYNC_INDEXABLE_MIME_TYPES is therefore intentionally
              # UNSET. Setting it to e.g. `application/pdf` would re-impose
              # the v1.5.x narrow scope. Setting it empty disables indexing
              # entirely (counter-intuitively; upstream logs a warning).
              # Optional heavier backends, deliberately OFF here:
              #   ENABLE_TESSERACT=true     — lightweight OCR for images
              #   ENABLE_DOCLING=true       — Docling for scanned PDFs / VLM
              #   COLLABORA_URL=http://...  — legacy .doc/.xls/.ppt + ODF
              # Tesseract is the cheapest image path; Docling + VLM (ADR-032)
              # is gated on EMBEDDING_GATEWAY_URL on a GPU host and is not
              # needed for the common formats.
              # --- Throttle / size caps (left at upstream defaults) --------
              #   VECTOR_SYNC_PROCESSOR_WORKERS   = 3   (concurrent indexers)
              #   VECTOR_SYNC_QUEUE_MAX_SIZE      = 10000  (back-pressure cap)
              #   VECTOR_SYNC_MAX_INDEX_FAILURES  = 5    (dead-letter after 5)
              #   VECTOR_SYNC_FAST_CONCURRENCY    = unset (inherit workers)
              #   VECTOR_SYNC_STRUCTURED_CONCURRENCY = unset
              #   DOCUMENT_CHUNK_SIZE             = 2048 chars per chunk
              #   DOCUMENT_CHUNK_OVERLAP          = 200  chars
              #   DOCUMENT_MAX_PDF_SIZE_MB        = 50   (applies to ALL
              #                                            doc types, not
              #                                            just PDFs — name
              #                                            is a misnomer)
              #   DOCUMENT_PARSE_PROCESS_SLOTS    = 2    (concurrent parse
              #                                            subprocesses)
              #   DOCUMENT_PARSE_TIMEOUT_SECONDS  = 120  (per-doc wall clock)
              #   VERIFICATION_CONCURRENCY        = unset (search-side
              #                                            fan-out only)
              # No master pause / drain switch. Indexing is continuous per
              # VECTOR_SYNC_SCAN_INTERVAL; once a scan starts, it runs to
              # queue drain. To stop: drop VECTOR_SYNC_SCAN_INTERVAL very high
              # (effectively pause), or stop the container.
              # --- First-pass cost estimate ----------------------------------
              # The initial scan re-queues the whole tagged corpus every
              # interval (PR #921 confirmed). For the full Nextcloud tree
              # on this instance (~hundreds to a few thousand files of the
              # common types), chunking at ~1 chunk/page for PDFs
              # (DOCUMENT_CHUNK_PAGE_AWARE=true) and ~2048 chars per chunk
              # for DOCX/XLSX/PPTX/MD/CSV, the first pass embeds in the
              # background while serving searches. Per-chunk embedding is a
              # single POST /api/embed against serenity's llama.cpp proxy
              # (bge-m3, 1024-dim) — expect tens of ms / chunk there, so
              # VECTOR_SYNC_PROCESSOR_WORKERS=3 caps the request rate at
              # ~30 chunks/s before Qdrant write becomes the bottleneck.
              # Subsequent scans are incremental (ETag-based change
              # detection, per ADR-010); only changed / newly-tagged /
              # newly-tagged-folder files are re-embedded. Deletions evict
              # after a grace period.
            };
          };
          # systemd service config: encrypt sops secret → LoadCredentialEncrypted →
          # ExecStartPre writes env file → EnvironmentFile feeds container.
          # Helper script: convert credential file → env file.
          # Defined outside serviceConfig to keep serviceConfig pure.
          serviceConfig = {
            Restart = "always";
            # systemd-native credentials: bind the sops plaintext straight into
            # CREDENTIALS_DIRECTORY/mcp-password at unit start (no separate
            # encrypt-oneshot, no blob, no cross-unit ordering hazard). The sops
            # secret is already plaintext at /run/secrets. RequiresMountsFor
            # orders us after the sops secrets mount.
            LoadCredential = "mcp-password:${config.sops.secrets."nextcloud/mcp-app-password".path}";
            RequiresMountsFor = [ "/run/secrets" ];
            # ExecStartPre runs the helper script defined in the let block.
            ExecStartPre = "${toString pkgs.bash}/bin/bash ${ncMcpCredsToEnvScript}";
          };
        };
      };
      # systemd loads the sops secret directly as a credential (see LoadCredential
      # above); no encrypt-oneshot / blob / ordering needed.
      # Ensure qdrant storage dirs exist (rootful quadlets: root-owned).
      system.activationScripts."nc-rag-qdrant-dirs".text = ''
        mkdir -p /var/lib/qdrant/storage /var/lib/qdrant/snapshots
        chmod 0750 /var/lib/qdrant /var/lib/qdrant/storage /var/lib/qdrant/snapshots
      '';
      # Forgejo backup receiver home (idempotent; owner has no shell/sudo).
      system.activationScripts."forgejo-backup-dir".text = ''
        install -d -o forgejo-backup -g forgejo-backup -m 0700 /tank/backups/serenity/forgejo
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
