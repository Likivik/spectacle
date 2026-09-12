{ inputs, den, ... }:
{
  den.aspects.server.forgejo = {
    nixos = { config, lib, pkgs, ... }:
      let
        # Combined /bin for the runner container: coreutils+git+nix+nodejs etc.
        # symlinked from the (host) store, bind-mounted so the container needs no
        # package installs and no image rebuild to add a tool — clan-infra /
        # ross-abaker "storeDeps" pattern.
        storeDeps =
          pkgs.runCommand "forgejo-runner-store-deps"
            { }
            ''
              mkdir -p $out/bin
              for dir in ${toString [
                pkgs.coreutils
                pkgs.findutils
                pkgs.gnugrep
                pkgs.gawk
                pkgs.git
                pkgs.nix
                pkgs.bash
                pkgs.jq
                pkgs.nodejs
                pkgs.gnutar  # actions/cache packs archives with tar (mandatory)
                pkgs.zstd   # actions/cache prefers zstd; container needs it to decompress
              ]}; do
                for bin in "$dir"/bin/*; do
                  ln -s "$bin" "$out/bin/$(basename "$bin")"
                done
              done

              # SSL CA certs so nix can reach binary caches
              mkdir -p $out/etc/ssl/certs
              cp -a "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt" \
                "$out/etc/ssl/certs/ca-bundle.crt"
            '';
      in
      {
        services.forgejo = {
          enable = true;

          # 15.0.7 (LTS) → 16.0.3 (rolling): binary-cached in pin, unlocks the
          # Actions job-logs / run-jobs API. v16 runs an irreversible DB
          # migration — back up before deploying (see migration plan).
          package = pkgs.forgejo;

          # stateDir / database.path / customDir stay on the SSD root (defaults)
          repositoryRoot = "/Storage/forgejo/repositories";
          lfs = {
            enable = true;
            contentDir = "/Storage/forgejo/lfs";
          };

          settings = {
            server = {
              DOMAIN = "serenity.oryx-galaxy.ts.net";
              ROOT_URL = "https://serenity.oryx-galaxy.ts.net/";
              HTTP_ADDR = "127.0.0.1";
              HTTP_PORT = 3000;
              SSH_PORT = 22;
              DISABLE_SSH = false;
            };
            service.DISABLE_REGISTRATION = true;

            # v16 removed the `*` default for reverse-proxy trust. tailscale
            # serve terminates TLS and forwards from 127.0.0.1, so trust only
            # loopback (we don't use reverse-proxy auth, this is just hygiene).
            security.REVERSE_PROXY_TRUSTED_PROXIES = "127.0.0.1,::1";

            # Forgejo docs "Recommended settings": for a low-activity instance the
            # default 50k-item / 16h cache is memory-inefficient; twoqueue + a
            # small LRU keeps only frequently-used items.
            cache.ADAPTER = "twoqueue";
            cache.HOST = "{\"size\":100, \"recent_ratio\":0.25, \"ghost_ratio\":0.5}";
          };

          # Enable Forgejo Actions (CI) — app.ini [actions] ENABLED=true.
          settings.actions.ENABLED = true;
        };

        # ── Self-contained CI requirements (the aspect carries its own deps) ──
        # Podman is the job runtime; host may already enable it (mkDefault so
        # a host can override its config).
        virtualisation.podman.enable = lib.mkDefault true;

        # Unprivileged user the *job* runs as inside the runner container.
        users.users.nixuser = {
          group = "nixuser";
          description = "Forgejo Actions job user (inside runner container)";
          home = "/var/empty";
          isSystemUser = true;
        };
        users.groups.nixuser = { };

        # Import the minimal runner image once, at activation: it only carries
        # a passwd/group (nixuser), nix.conf and nsswitch. All real tools are
        # bind-mounted from storeDeps so the image needs (almost) no userland.
        systemd.services.forgejo-runner-nix-image = {
          description = "Import minimal Forgejo Actions nix runner image";
          wantedBy = [ "multi-user.target" ];
          after = [ "podman.service" ];
          requires = [ "podman.service" ];
          path = [ config.virtualisation.podman.package pkgs.gnutar pkgs.shadow pkgs.getent ];
          serviceConfig = {
            RuntimeDirectory = "forgejo-runner-nix-image";
            WorkingDirectory = "/run/forgejo-runner-nix-image";
            Type = "oneshot";
            RemainAfterExit = true;
          };
          script = ''
            set -eux -o pipefail
            mkdir -p etc/nix

            # account table with an unprivileged nixuser for --user nixuser
            touch etc/passwd etc/group
            groupid=$(cut -d: -f3 < <(getent group nixuser))
            userid=$(cut -d: -f3 < <(getent passwd nixuser))
            groupadd --prefix "$(pwd)" --gid "$groupid" nixuser
            emptypassword='$6$1ero.LwbisiU.h3D$GGmnmECbPotJoPQ5eoSTD6tTjKnSWZcjHoVTkxFLZP17W9hRi/XkmCiAMOfWruUwy8gMjINrBMNODc7cYEo4K.'
            useradd --prefix "$(pwd)" -p "$emptypassword" -m -d /tmp -u "$userid" -g "$groupid" -G nixuser nixuser

            cat <<NIX_CONFIG > etc/nix/nix.conf
            accept-flake-config = true
            experimental-features = nix-command flakes
            NIX_CONFIG

            cat <<NSSWITCH > etc/nsswitch.conf
            passwd:    files mymachines systemd
            group:     files mymachines systemd
            shadow:    files

            hosts:     files mymachines dns myhostname
            networks:  files

            ethers:    files
            services:  files
            protocols: files
            rpc:       files
            NSSWITCH

            tar -cv . | ${config.virtualisation.podman.package}/bin/podman import - forgejo-runner-nix
          '';
        };

        services.gitea-actions-runner.package = pkgs.forgejo-runner;
        services.gitea-actions-runner.instances.serenity = {
          enable = true;
          url = "https://serenity.oryx-galaxy.ts.net/";
          name = "serenity";
          # Container-isolated job, as an unprivileged nixuser, with the host
          # store (/nix) + storeDeps/bin mounted in; nix talks to the host daemon.
          labels = [ "nix:docker://forgejo-runner-nix" ];
          # Real tokenFile comes from sops (declared in serenity.nix); the module
          # requires exactly one of token/tokenFile. Fall back to a dummy path
          # when the sops module isn't present (e.g. the hermetic VM test) so the
          # aspect stays self-contained and doesn't force a sops dependency.
          tokenFile = config.sops.secrets."registration-token".path
            or "/run/forgejo-registration/registration-token";
          settings = {
            runner.capacity = 1;
            runner.envs = {
              # Determinate's COMPAT socket (standard Nix daemon protocol).
              # The determinate-nixd.socket path speaks gRPC/HTTP2 and any
              # normal nix client fails with "protocol mismatch, got HTTP/1.1 400".
              NIX_REMOTE = "unix:///nix/var/nix/daemon-socket/socket";
            };
            container = {
              network = "host";
              options = "-e NIX_BUILD_SHELL=/bin/bash -e PAGER=cat -e PATH=/bin -e SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt -e CARGO_HOME=/opt/cargo -e CARGO_TARGET_DIR=/opt/target --user nixuser -v /nix:/nix -v ${storeDeps}/bin:/bin -v ${storeDeps}/etc/ssl:/etc/ssl -v /Storage/forgejo/rust-cache:/opt/cargo -v /Storage/forgejo/rust-target:/opt/target";
              valid_volumes = [ "/nix" "${storeDeps}/bin" "${storeDeps}/etc/ssl" "/Storage/forgejo/rust-cache" "/Storage/forgejo/rust-target" ];
            };
            # Forgejo's intended Actions cache: a cache server inside the runner,
            # serving actions/cache (tar archives on the runner's disk, keyed per
            # branch). Works with our host-networked containers (no pasta issue).
            cache = {
              enabled = true;
              dir = "/Storage/forgejo/actcache";
            };
          };
        };

        # The runner must not start before its image is imported.
        systemd.services.gitea-runner-serenity.after = [ "forgejo-runner-nix-image.service" ];
        systemd.services.gitea-runner-serenity.requires = [ "forgejo-runner-nix-image.service" ];

        # The module uses DynamicUser; keep a real user so it can (a) read the
        # sops tokenFile (0600 gitea-runner) and (b) drive the root podman socket
        # via the podman group. The *job* still runs as nixuser inside the container.
        users.users.gitea-runner = {
          isSystemUser = true;
          group = "gitea-runner";
          createHome = true;
          home = "/Storage/forgejo/runner";
        };
        users.groups.gitea-runner = { };
        users.users.gitea-runner.extraGroups = [ "users" "podman" ]; # traverse /Storage + launch containers
        systemd.services.gitea-runner-serenity.serviceConfig.DynamicUser = lib.mkForce false;

        # Create the ZFS-pool + backup data dirs owned by the forgejo user.
        # `install -d` is idempotent (creates only when absent, won't clobber).
        # /Storage is 0770 likivik:users. forgejo must be able to traverse it to
        # reach its own /Storage/forgejo dirs; add it to the users group.
        users.users.forgejo.extraGroups = [ "users" ];

        system.activationScripts.forgejo-dirs = lib.stringAfter [ "users" "specialfs" ] ''
          # Parent is 0770 forgejo:users so both forgejo (owner) and gitea-runner
          # (via the users group) can traverse into it; subdirs stay per-user.
          install -d -o forgejo -g users -m 0770 /Storage/forgejo
          chown forgejo:users /Storage/forgejo 2>/dev/null || true
          chmod 0770 /Storage/forgejo
          install -d -o forgejo -g forgejo -m 0750 \
            /Storage/forgejo/repositories \
            /Storage/forgejo/lfs
          # actions/cache server dir — owned by the runner (gitea-runner) user.
          install -d -o gitea-runner -g gitea-runner -m 0750 /Storage/forgejo/actcache
          # Persistent Rust cargo cache (Layer 2): the runner job runs as nixuser
          # inside a container whose bind-mounted /opt dirs preserve host
          # ownership — nixuser:nixuser 0770 lets the in-container job read/write.
          install -d -o nixuser -g nixuser -m 0770 \
            /Storage/forgejo/rust-cache \
            /Storage/forgejo/rust-target
          install -d -o forgejo -g forgejo -m 0700 /var/backup/forgejo
        '';

        # ProtectSystem=strict + ReadWritePaths: the module only opens the leaf
        # paths (repositories, lfs) read-write; the parent /Storage/forgejo is
        # read-only in the sandbox, so Forgejo's storage MkdirAll fails on the
        # parent with EPERM even though forgejo owns it. Open the parent too.
        systemd.services.forgejo.serviceConfig.ReadWritePaths = lib.mkBefore [ "/Storage/forgejo" ];

        # Expose Forgejo on the tailnet over HTTPS. tailscale serve is imperative
        # state; a oneshot re-applies it after every boot/rebuild. HTTP stays
        # loopback-only (127.0.0.1:3000); serve fronts it with a tailnet cert.
        systemd.services."tailscale-serve-forgejo" = {
          description = "Expose Forgejo on the tailnet over HTTPS (tailscale serve)";
          after = [ "tailscaled.service" "forgejo.service" ];
          wants = [ "tailscaled.service" ];
          wantedBy = [ "multi-user.target" ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
          };
          script = ''
            ${pkgs.tailscale}/bin/tailscale serve --bg --https=443 http://127.0.0.1:3000
          '';
        };

        # ── Off-site backups: nightly forgejo dump → poweredge tank/backups ──
        # Best practice: nightly all-in-one forgejo dump (repos+DB+config+LFS),
        # keep 14 dailies locally + on poweredge; poweredge's ZFS daily snapshots
        # of tank/backups/serenity supply the deeper retention layer.
        systemd.timers.forgejo-backup = {
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnCalendar = "*-*-* 03:30:00";
            Persistent = true;
          };
        };
        systemd.services.forgejo-backup = {
          description = "Nightly Forgejo dump -> poweredge /tank/backups/serenity/forgejo";
          after = [ "network-online.target" ];
          wants = [ "network-online.target" ];
          path = with pkgs; [ config.services.forgejo.package rsync openssh coreutils findutils gnugrep ];
          serviceConfig = {
            User = "forgejo";
            Group = "forgejo";
            Type = "oneshot";
            WorkingDirectory = "/var/lib/forgejo";
            Environment = [
              "HOME=/var/lib/forgejo"
              "FORGEJO_WORK_DIR=/var/lib/forgejo"
              "FORGEJO_CUSTOM=/var/lib/forgejo/custom"
            ];
          };
          script = ''
            set -eu
            KEY=/var/lib/forgejo/.ssh/id_forgejo_backup
            KNOWN=/var/lib/forgejo/.ssh/known_hosts
            DEST="forgejo-backup@poweredge.oryx-galaxy.ts.net:/tank/backups/serenity/forgejo"
            OUT=/var/backup/forgejo
            DATE=$(${pkgs.coreutils}/bin/date +%F)
            f="$OUT/forgejo-$DATE.zip"
            # 1. all-in-one dump (repos + sqlite DB + app.ini + LFS + attachments)
            ${config.services.forgejo.package}/bin/forgejo dump --type zip --file "$f"
            # 2. push off-site over the tailnet (dedicated low-priv receiver)
            ${pkgs.rsync}/bin/rsync -az \
              -e "${pkgs.openssh}/bin/ssh -i $KEY -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$KNOWN" \
              "$f" "$DEST"
            # 3. prune local dailies: keep 14
            ${pkgs.coreutils}/bin/ls -1t $OUT/forgejo-*.zip 2>/dev/null \
              | ${pkgs.coreutils}/bin/tail -n +15 \
              | ${pkgs.findutils}/bin/xargs -r rm -f
            # 4. prune remote dailies: keep 14
            ${pkgs.openssh}/bin/ssh -i $KEY -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$KNOWN \
              forgejo-backup@poweredge.oryx-galaxy.ts.net \
              "ls -1t /tank/backups/serenity/forgejo/forgejo-*.zip 2>/dev/null | tail -n +15 | xargs -r rm -f" \
              || true
          '';
        };
      };
  };
}
