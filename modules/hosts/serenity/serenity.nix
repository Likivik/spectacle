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
      den.aspects.server.olmocr-vision
      den.aspects.server.surya-server
      den.aspects.server.monkey-server
      den.aspects.server.forgejo
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

        security.sudo.extraRules = [{
          users = [ "likivik" ];
          commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
        }];

        fileSystems."/panther" = {
          device = "/dev/disk/by-uuid/b1f69b8f-cc97-4879-9942-ac8df1e0f6d8";
          fsType = "ext4";
          options = [
            "defaults"
            "user"
            "rw"
          ];
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
        boot.zfs.extraPools = [ "serenity_onetb_zpool" ];
        boot.zfs.devNodes = "/dev/disk/by-label/serenity_onetb_zpool";
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
          kernelParams = [ "nvidia_drm.modeset=1" ];
        };

        # Remote desktop: rustdesk dropped 2026-09-07 — no Hydra cache (job
        # removed from latest eval, vendor-hash nondeterminism #527155), so
        # it source-rebuilds on every nixpkgs bump and stalls deploys 40+ min.
        # The Wayland unattended-login fix never landed; if it's needed again
        # use a pinned rev with the vendor fix or gnome-remote-desktop.

        # Auto-pull spectacle repo every 5 min
        systemd.services.spectacle-autopull = {
          description = "Pull spectacle repo from origin";
          after = [ "network-online.target" ];
          wants = [ "network-online.target" ];
          serviceConfig = {
            Type = "oneshot";
            User = "likivik";
            ExecStart = "${pkgs.git}/bin/git -C /Storage/Git/spectacle pull --ff-only origin dev";
          };
        };

        systemd.timers.spectacle-autopull = {
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnBootSec = "2min";
            OnUnitActiveSec = "5min";
          };
        };

        # KRDP — KDE Remote Desktop (RDP server, Wayland-native)
        systemd.user.services.krdp = {
          description = "KDE Remote Desktop (RDP) Server";
          after = [ "graphical-session.target" ];
          wants = [ "graphical-session.target" ];
          wantedBy = [ "default.target" ];

          serviceConfig = {
            Type = "simple";
            ExecStart = "${pkgs.kdePackages.krdp}/bin/krdpserver";
            Restart = "on-failure";
            RestartSec = 5;
          };
        };
      };

  };
}
