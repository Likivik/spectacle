{ inputs, den, ... }:
{
  den.aspects.server.forgejo = {
    nixos = { config, lib, pkgs, ... }: {
      services.forgejo = {
        enable = true;

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
        };
      };

      # Create the ZFS-pool + backup data dirs owned by the forgejo user.
      # `install -d` is idempotent (creates only when absent, won't clobber).
      # Runs at activation — after /Storage (ZFS) is mounted and the forgejo
      # user exists — so the dirs exist before forgejo.service's
      # ReadWritePaths bind-mounts them.
      # /Storage is 0770 likivik:users. forgejo must be able to traverse it to
      # reach its own /Storage/forgejo dirs; add it to the users group.
      users.users.forgejo.extraGroups = [ "users" ];

      system.activationScripts.forgejo-dirs = lib.stringAfter [ "users" "specialfs" ] ''
        install -d -o forgejo -g forgejo -m 0750 \
          /Storage/forgejo \
          /Storage/forgejo/repositories \
          /Storage/forgejo/lfs
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
    };
  };
}
