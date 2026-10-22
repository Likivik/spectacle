{ den, inputs, ... }:
{

  den.aspects.serenity = {

    includes = [
      den.aspects.core
      den.aspects.desktop.common-core
      den.aspects.desktop.common-extra.peripherals-extra

      den.aspects.desktop.desktopManagers.kde

      den.aspects.dev

      den.aspects.cprocsp
      den.aspects.firefox

      den.aspects.server.nc-rag
      den.aspects.server.forgejo
      den.aspects.server.sops

      # ── Hermes Agent (moved here from erebus, 2026-10-05) ───────────────
      # Brings the gateway user units, dashboard, and the agent's local
      # dependency stack: graphiti MCP + FalkorDB (:6379), LiteLLM (:4000),
      # llama (:8081), browser CDP (:9222).
      # Also included: email (himalaya MCP — it runs *on the agent host*, not
      # as a separate service). Deliberately NOT included: searxng (unused —
      # web.search_backend is exa), sillytavern, fishaudio-proxy.
      # hr-bot stays on erebus.
      den.aspects.server.hermes-agent
      den.aspects.server.hermes-webui
      den.aspects.server.email
    ];

    maid = {
      file.home.".nix-maid-test".text = ''
        Hello from nix-maid!
        This was generated on: {{date}}
        My home directory is: {{home}}
      '';
    };

    nixos =
      {
        pkgs,
        config,
        lib,
        modulesPath,
        ...
      }:
      {

        imports = [
          # provides basic hardware detection/drivers
          (modulesPath + "/installer/scan/not-detected.nix")
        ];

        boot.initrd.availableKernelModules = [
          "xhci_pci"
          "ahci"
          "usbhid"
          "usb_storage"
          "sd_mod"
        ];
        boot.initrd.kernelModules = [ ];
        boot.kernelModules = [ "kvm-intel" ];
        boot.extraModulePackages = [ ];

        # SSH server
        services.openssh = {
          enable = true;
          settings = {
            PermitRootLogin = "no";
            PasswordAuthentication = false;
          };
        };

        # Tailscale control channel: force the "noise" dialer onto port 443.
        #
        # Tailscale's control client prefers plaintext HTTP on port 80 for the
        # control-plane upgrade (the Noise handshake rides along in the HTTP
        # upgrade request, saving a round trip) and only falls back to
        # HTTPS:443 when port 80 fails *fast*. On serenity's ISP path, port 80
        # is interfered with after that upgrade: registration succeeds, then
        # the /machine/map long-poll is killed every 2 minutes, forever, so the
        # node never holds a netmap. Symptom: the tailnet shows serenity
        # offline and every peer sees rx 0, while the host itself has working
        # internet.
        #
        #   control: map response long-poll timed out!            (every ~2m)
        #   control: lite map update error after 2m0.001s: Post
        #     "https://controlplane.tailscale.com/machine/map": context canceled
        #   health(warnable=not-in-map-poll): error: Unable to connect to the
        #     Tailscale coordination server ...
        #
        # Verified 2026-09-12 on serenity (tailscale 1.102.3, state file valid,
        # node authorized):
        #   http://controlplane.tailscale.com/health   -> times out
        #   https://controlplane.tailscale.com/health  -> immediate response
        #
        # Upstream knob: TS_FORCE_NOISE_443 in control/controlhttp/client.go —
        # "necessary when networks or middle boxes are messing with port 80",
        # cf. tailscale#13597 and hassio-addons#688.
        systemd.services.tailscaled.serviceConfig.Environment = lib.mkAfter [
          "TS_FORCE_NOISE_443=true"
        ];

        # Declarative tailscale prefs, applied post-start by tailscaled-set.service
        # (module wires `after = tailscaled.service`; runs `tailscale set <flags>`
        # once the backend is Running). Runtime `tailscale set` changes are
        # overwritten on every activation — keep this block in sync.
        services.tailscale.extraSetFlags = [
          "--exit-node=erebus"
          "--exit-node-allow-lan-access=true"
        ];

        # ── sops (TPM-bound identity for serenity) ───────────────────────
        # Serenity is a TPM host: decrypt with the TPM age identity, NOT
        # ssh-to-age (the generic server.sops aspect defaults to sshKeyPaths;
        # override to the TPM keyFile).
        sops.age.keyFile = "/var/lib/sops/tpm-identity.txt";
        sops.age.sshKeyPaths = lib.mkForce [ ];

        # ── provision secrets from a systemd UNIT, not the activation script ──
        # Default is `systemd.sysusers.enable || services.userborn.enable` (both
        # false here) → activation, which runs BEFORE systemd's units exist.
        # That ordering gap is the root of two separate hazards:
        #   * the old hand-rolled sops-env generator raced
        #     systemd-tmpfiles-setup, and there was no way to order it — both
        #     ran during activation;
        #   * the serenity-smoke gate's dummy age key had to be threaded into
        #     setupSecrets' deps, because no unit ran early enough to place it.
        # With this on, `sops-install-secrets.service` (oneshot, wantedBy+before
        # sysinit.target, after local-fs.target) does the work and the ordering
        # becomes declarative. It is also the path sops-nix itself tests.
        #
        # Behaviour that changes: `restartUnits` now goes through systemctl
        # (SOPS_RESTART_UNITS_VIA_SYSTEMCTL=1). `hermes/webui-password` uses it,
        # so that path is exercised by the smoke gate.
        #
        # Serenity FIRST, deliberately. This changes how EVERY secret on the
        # host is provisioned, each host builds its own closure, and the smoke
        # gate only covers serenity — erebus, traversal and poweredge still use
        # activation and need their own verification before they follow.
        # Tracked: https://github.com/Likivik/spectacle/issues/2
        sops.useSystemdActivation = true;

        sops.secrets."registration-token" = {
          sopsFile = ../../../secrets/serenity/secrets.yaml;
          owner = "gitea-runner";
          group = "gitea-runner";
          mode = "0600";
        };

        # ── Hermes Agent: secrets + runtime wiring ───────────────────────
        # Same shape as erebus.nix's block: the *host* declares the sops
        # secrets the shared aspects consume. All of these live in serenity's
        # own file (TPM identity) — nothing decrypts across hosts.
        # Agent secrets live in their own file, encrypted to serenity's three
        # recipients (X25519 + TPM). Built on erebus from the existing values —
        # encryption needs only the public recipients, so no cross-host
        # decryption and no TPM plugin dance. Verified by TPM round-trip.
        #
        # NOT via sops.defaultSopsFile: the shared server/sops aspect
        # mkForce-nulls it deliberately, so every host names its file per secret.

        users.users.hermes.extraGroups = [ "users" "systemd-journal" "gitdev" ];

        # (The agent's own bge-m3 embedder is skipped on this host inside the
        # hermes-agent aspect: nc-rag already runs the identical model on :8081,
        # CUDA-accelerated, so graphiti shares that one instead of a duplicate.)

        # Tooling the agent's skills and MCP servers expect (mirrors erebus):
        # nodejs+npx for the npx-based MCP servers, jj/gh for repo work, and
        # the office/PDF stack for the document skills.
        environment.systemPackages = with pkgs; [
          nodejs_22
          uv
          git
          gh
          pkgs.jujutsu
          libreoffice
          pandoc
          poppler-utils
          ffmpeg
          (python3.withPackages (ps: [ ps.numpy ps.pillow ]))
        ];

        sops.secrets = {
          # Env + platform tokens
          "hermes/env" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes/telegram-bot-token" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes/salem-bot-token" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          # Model + search provider keys
          "hermes/exa-api-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes/minimax-api-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes/synthetic-api-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          # Gateway API listeners (default :8642, salem :8643)
          "hermes/api-server-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes/salem-api-server-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          # Dashboard basic auth (mobile clients without Nous OAuth)
          "hermes/dashboard-basic-auth-hash" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes/dashboard-basic-auth-secret" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          # hermes-webui's EnvironmentFile. Declared per host (webui.nix cannot
          # name a host's file); restartUnits is required — sops-nix reloadUnits
          # sends a signal the python server ignores.
          "hermes/webui-password" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0400"; restartUnits = [ "hermes-webui.service" ]; };
          # Langfuse — agent traces (same project: it is the same agent, moved)
          "langfuse/hermes-erebus/public-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "langfuse/hermes-erebus/secret-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          # Langfuse — LiteLLM proxy traces
          "langfuse/graphiti-litellm/public-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "langfuse/graphiti-litellm/secret-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          # Provider keys LiteLLM reads at runtime
          "hermes-mitmproxy/github/pat-hermes-full" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes-mitmproxy/llm-providers/openrouter/api-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes-mitmproxy/llm-providers/groq/api-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes-mitmproxy/llm-providers/huggingface/api-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          "hermes-mitmproxy/llm-providers/mistral/api-key" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0600"; };
          # Email MCP (himalaya runs on the agent host and cats these)
          "email/gmail/account1/adress" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0400"; };
          "email/gmail/account1/app-password" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0400"; };
          "email/gmail/account2/adress" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0400"; };
          "email/gmail/account2/app-password" = { sopsFile = ../../../secrets/serenity/hermes-secrets.yaml; owner = "hermes"; group = "hermes"; mode = "0400"; };
        };

        # ── Cutover complete (Stage B, 2026-10-05) ───────────────────────
        # Erebus is stopped AND masked, so the gateways may start here again.
        # The Stage-A  overrides are deliberately
        # gone: a reboot on this host must bring the messaging control plane
        # up by itself. If the poller ever moves back to erebus, re-add them
        # there-first and mask this side, in that order — two pollers on one
        # token silently split updates.

        # Open UDP 41641 (WireGuard endpoint) at the global firewall level.
        # Interface-scoped rules are useless here: peer punches arrive from the
        # NAT-mapped external port (e.g. 185.237.239.110:1481), and by then they
        # have not been decapsulated onto tailscale0 yet.
        services.tailscale.openFirewall = true;

        users.users.likivik.openssh.authorizedKeys.keys = [
          # hermes@erebus
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIECMxs9cBFN8Adq8AJ9I62gVNFTkgNkr0ikg+VkWbHx1 hermes@erebus"
          # likivik@traversal
          "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
        ];

        security.sudo.extraRules = [
          {
            users = [ "likivik" ];
            commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
          }
          # The agent operates the fleet from this host too (its gateway runs as
          # the hermes user), so it gets the same NOPASSWD the erebus install has.
          {
            users = [ "hermes" ];
            commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
          }
        ];

        # ── /Git: repos + jj workspaces on the SSD ───────────────────────────
        # Replaces the old /panther + `bind /panther/Git → /Storage/Git` pair.
        # That bind was ordered only against panther.mount, never against
        # Storage.mount, so on 2026-10-21 the ZFS /Storage mounted over it and
        # the entire tree appeared to vanish. /Git's parent is `/`, mounted
        # first by construction — no ordering dance, no bind.
        #
        # gitpool lives on the 119 GiB Apacer SSD: zstd compression (the CI Rust
        # target dir alone is 75 GiB uncompressed) and per-dataset quotas so a
        # runaway build hits its own ceiling instead of filling the disk.
        fileSystems."/Git" = {
          device = "gitpool/git";
          fsType = "zfs";
        };

        # Belt for the same failure mode: a slow SATA link must not drop the box
        # into rescue. The import script polls for up to this long.
        systemd.services."zfs-import-gitpool".serviceConfig.TimeoutStartSec = "180";

        # CI build caches, same pool: they must not live on the ZFS HDD where
        # random writes cost the whole box (ARC eviction + 75 GiB of churn).
        fileSystems."/var/cache/forgejo-ci" = {
          device = "gitpool/ci-cache";
          fsType = "zfs";
        };

        fileSystems."/" = {
          device = "/dev/disk/by-uuid/812b6d5f-dc5d-4ee7-a576-e4644011d1c3";
          fsType = "ext4";
        };

        fileSystems."/boot" = {
          device = "/dev/disk/by-uuid/E385-6E2F";
          fsType = "vfat";
        };

        swapDevices = [
          { device = "/dev/disk/by-uuid/f8ffc153-dd5c-41cc-9827-49a5788c697b"; }
        ];

        powerManagement.cpuFreqGovernor = "performance";
        hardware.cpu.intel.updateMicrocode = config.hardware.enableRedistributableFirmware;

        # ZFS
        boot.supportedFilesystems = [ "zfs" ];
        boot.zfs.forceImportRoot = false;
        networking.hostId = "ad7406b6";
        services.zfs.autoScrub.enable = true;
        # gitpool: the SSD pool behind /Git and the CI caches (see above).
        boot.zfs.extraPools = [ "serenity_onetb_zpool" "gitpool" ];
        # zfs-import scans ONLY this path. Pointing it at a by-label directory
        # that contains a single device is why gitpool was "in state MISSING,
        # waiting" for 60 s at boot on 2026-10-22 and local-fs failed into
        # rescue: the SSD was never in the search path. by-id covers both
        # pools and is the NixOS default.
        boot.zfs.devNodes = "/dev/disk/by-id";
        boot.initrd.supportedFilesystems = [ "zfs" ];

        # Nvidia driver
        services.xserver.videoDrivers = [ "nvidia" ];
        hardware.nvidia.open = true;

        hardware.graphics = {
          enable = true;
          enable32Bit = true;
          extraPackages = with pkgs; [
            intel-media-driver
          ];
        };

        boot = {
          blacklistedKernelModules = [
            "nouveau"
          ];
          # zswap sits *in front of* zram and would intercept the pages zram
          # is meant to hold (ArchWiki zram), so it has to stay off. It is
          # already `N` on this host; pinned here so a future kernel/config
          # default flip cannot silently neutralise the zram swap below.
          kernelParams = [ "nvidia_drm.modeset=1" "zswap.enabled=0" ];
        };

        # Remote desktop: rustdesk dropped 2026-09-07 — no Hydra cache (job
        # removed from latest eval, vendor-hash nondeterminism #527155), so
        # it source-rebuilds on every nixpkgs bump and stalls deploys 40+ min.
        # The Wayland unattended-login fix never landed; if it's needed again
        # use a pinned rev with the vendor fix or gnome-remote-desktop.

        # Auto-pull was removed here on 2026-10-06. The Hermes agent now runs on
        # Serenity and does its work in its own jj workspace, so a blind
        # `git pull --ff-only origin dev` into /Storage/Git/spectacle buys nothing
        # and can fight whatever a session has in the canonical checkout. Deploys
        # are explicit: dry-build -> serenity-smoke -> detached nixos-rebuild.
        # (Traversal still autopulls its own checkout.)

        # KRDP (KDE Remote Desktop / krdpserver) was removed 2026-10-20: its
        # user unit crash-looped — 80,295 SIGABRT dumps in one boot — and the
        # `Restart = on-failure` + `RestartSec = 5` policy never tripped
        # systemd's start limiter, so it restarted forever. The drkonqi
        # symbolication it triggered (88 failed units, 63k journal error
        # lines/day) is what drove four global OOM kills. Re-add only with a
        # bounded StartLimitBurst and a verified-working krdpserver.

        # ── Memory hardening (2026-10-21) ────────────────────────────────────
        # 15 GiB box, 8.8 GiB disk swap, no cgroup memory bounds at all: a
        # runaway build or a crash-looping coredump symboliser drove five
        # *global* kernel OOM kills in one week (2026-10-16 .. 10-20), i.e. the
        # kernel picked victims box-wide with no reclaim fallback. Two levers,
        # neither of them lethal:
        #
        # 1. zram — compressed swap held in RAM, given a higher priority than
        #    the disk partition, so a spike is absorbed with no disk thrash.
        #    NixOS `memoryPercent` is the *uncompressed* zram capacity; 50% of
        #    15 GiB ≈ the min(ram/2, 16G) that zram-generator ships as default.
        #    Serenity is not hibernated (zram cannot back hibernation), and
        #    swapon order is by priority, so /dev/sdb3 stays the slow fallback.
        zramSwap.enable = true;
        zramSwap.memoryPercent = 50;

        # 2. oomd — kill inside a cgroup *before* the kernel thrash-locks the
        #    whole box. systemd slices, as on erebus.
        systemd.oomd = {
          enable = true;
          enableRootSlice = true;
          enableSystemSlice = true;
          enableUserSlices = true;
        };
        systemd.slices."system".sliceConfig.ManagedOOMMemoryPressureLimit = "60%";
        # user.slice holds the hermes gateway *and* whatever build a session
        # runs (2026-10-21: a Gradle/KMP build held 4.5 GiB, 3.4 GiB of it in
        # swap). The default 60% pressure cull there would take the agent down
        # together with the build, so raise the threshold and mark the things
        # the box cannot lose kill-last — oomd then picks the build scope in
        # the same slice instead.
        systemd.slices."user".sliceConfig.ManagedOOMMemoryPressureLimit = "80%";
        systemd.user.services.hermes-gateway.serviceConfig.ManagedOOMPreference = "avoid";
        systemd.services.sshd.serviceConfig.ManagedOOMPreference = "avoid";
        systemd.services.tailscaled.serviceConfig.ManagedOOMPreference = "avoid";
        systemd.services.nix-daemon.serviceConfig.ManagedOOMPreference = "avoid";
        # The upstream swap-based rule assumes a slow disk swap; a zram device
        # reaches 90%-used far sooner and would cull healthy cgroups. Raise the
        # bar so PSI (the pressure limits above) is what decides.
        environment.etc."systemd/oomd.conf.d/10-serenity.conf".text = ''
          [OOM]
          SwapUsedLimit = 95%
        '';
      };

  };
}
