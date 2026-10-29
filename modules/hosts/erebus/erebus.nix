{ den, inputs, lib, pkgs, ... }:
let
in
{
  den.aspects.erebus = {
    includes = [
      den.aspects.core
      den.aspects.core.tailscale
      den.aspects.server.hermes-agent
      den.aspects.server.hermes-webui
      den.aspects.server.email
      den.aspects.server.sillytavern
      den.aspects.server.fishaudio-proxy
      den.aspects.server.hr-bot
      den.aspects.server.sops
      den.aspects.sops-cli
    ];

    nixos = { config, pkgs, lib, ... }: {
      imports = [
        inputs.disko.nixosModules.disko
        ./_disko.nix
        ./_hardware-configuration.nix
      ];

      # ── Low-RAM / OOM safety (erebus has 7.8 GiB; nix evals can spike) ─────
      # zram compressed swap absorbs a memory spike so a heavy eval doesn't
      # push the box into a thrash-lockup (NixOS ships no swap by default).
      zramSwap.enable = true;
      zramSwap.memoryPercent = 50;
      # Persistent journal across reboots (so an OOM is recoverable next time).
      services.journald.storage = "persistent";
      services.journald.settings.Journal.SystemMaxUse = "2G";
      # oomd: act before the kernel OOM thrash. Graduate limits: system slice
      # is less latency-critical (60%); ROOT stays the 80% net. We do NOT lower
      # the user slice here: Hermes + this agent's nix subprocesses share one
      # cgroup (user@998/…/hermes-gateway), so oomd can't kill one without the
      # other — we rely on zram headroom instead of risking an eager user-slice
      # cull.
      systemd.oomd = {
        enable = true;
        enableRootSlice = true;
        enableSystemSlice = true;
        enableUserSlices = true;
      };
      systemd.slices."system".sliceConfig.ManagedOOMMemoryPressureLimit = "60%";
      # Kill-last for services the box can't lose.
      systemd.services.sshd.serviceConfig.ManagedOOMPreference = "avoid";
      systemd.services.tailscaled.serviceConfig.ManagedOOMPreference = "avoid";
      systemd.services.nix-daemon.serviceConfig.ManagedOOMPreference = "avoid";

      boot.loader.grub = {
        enable = true;
        efiSupport = false;
      };
      boot.loader.systemd-boot.enable = lib.mkForce false;

      systemd.network.enable = true;
      networking.useNetworkd = true;

      systemd.network.networks."10-ens3" = {
        matchConfig.Name = "ens3";
        address = [ "148.253.214.185/32" ];
        routes = [
          { Gateway = "10.0.0.1"; }
          { Destination = "10.0.0.1/32"; }
        ];
        networkConfig.DNS = [ "8.8.8.8" "8.8.4.4" ];
      };

      nix.settings = {
        trusted-users = [ "likivik" ];
        require-sigs = false;
      };

      services.openssh = {
        enable = true;
        openFirewall = true;
        settings = {
          PermitRootLogin = "no";
          PasswordAuthentication = false;
        };
      };

      networking.firewall.enable = true;
      # Ports are granted onto wires: services declare ports, this host decides where
      # they appear. `lockSshToTailscale` is superseded — ssh is granted on the tailnet
      # wire only, which is the same result without a second, competing definition.
      networkFirewall.enable = true;
      networkFirewall.ifaces = {
        wan = "ens3";
        tailnet = "tailscale0";
        podman0 = "podman0";
        lo = "lo";
      };
      # NAT-punched peer traffic arrives on ens3 from the peer's public address,
      # before decapsulation, so no interface-scoped rule can ever match it. This
      # is the one port that legitimately has to be global.
      networkFirewall.global.udp = [ 41641 ];
      networkFirewall.services = {
        ssh.ports = [ 22 ];
        forgejo.ports = [ 3443 ];
        sillytavern.ports = [ 8001 ];
        hermes-api.ports = [ 8642 ];
        hermes-dashboard.ports = [ 9119 ];
        tts.ports = [ 8880 ];
        fishaudio.ports = [ 8099 ];
      };
      networkFirewall.grants = {
        ssh = [ "tailnet" ];
        forgejo = [ "tailnet" ];
        sillytavern = [ "tailnet" ];
        hermes-api = [ "tailnet" ];
        hermes-dashboard = [ "tailnet" ];
        tts = [ "tailnet" ];
        fishaudio = [ "tailnet" "lo" "podman0" ];
      };

      swapDevices = [ { device = "/swapfile"; size = 4096; } ];

      users.users.hermes.extraGroups = [ "users" "systemd-journal" "gitdev" ];

      # Lets serenity's agent stop THIS host's Telegram poller during a cutover,
      # so the two never poll one token together (they would not conflict
      # loudly — they would split updates). sshd's StrictModes refuses
      # ~/.ssh/authorized_keys here because /var/lib/hermes is mode 2770
      # (group-writable), so the key goes in the other path sshd trusts,
      # /etc/ssh/authorized_keys.d/%u — which is also the declarative one.
      users.users.hermes.openssh.authorizedKeys.keys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAxgjvMCf4tUu9geCOifsHdlMK9md9D0ykkcxca47WeD hermes@serenity->erebus (flip)"
      ];

      sops.secrets = {
        # hermes-webui consumes this as an EnvironmentFile. Declared per host
        # (the shared aspect cannot name a host's secrets file).
        "hermes/webui-password" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0400";
          restartUnits = [ "hermes-webui.service" ];
        };

        "tailscale/auth-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "root";
          group = "root";
          mode = "0600";
        };
        "hermes/env" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes/telegram-bot-token" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes/hr-bot-token" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes/exa-api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes/minimax-api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes/synthetic-api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes/api-server-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        # Salem profile's gateway API key (own listener on :8643)
        "hermes/salem-api-server-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        # Salem profile's Telegram bot token (The Witch Queen bot)
        "hermes/salem-bot-token" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        # Dashboard username/password auth (dashboard_auth/basic plugin) —
        # lets mobile clients (rusty4444 app) log in without Nous OAuth.
        "hermes/dashboard-basic-auth-hash" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes/dashboard-basic-auth-secret" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        # Langfuse — Hermes Agent traces (project: hermes-erebus)
        "langfuse/hermes-erebus/public-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "langfuse/hermes-erebus/secret-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes-mitmproxy/github/pat-hermes-full" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes-mitmproxy/llm-providers/openrouter/api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        # Added so LiteLLM (graphiti-free pool) can read them at runtime.
        # Keys already present in secrets/erebus/secrets.yaml (encrypted).
        "hermes-mitmproxy/llm-providers/groq/api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes-mitmproxy/llm-providers/huggingface/api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes-mitmproxy/llm-providers/mistral/api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        # Langfuse — LiteLLM proxy traces (project: graphiti-litellm)
        "langfuse/graphiti-litellm/public-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "langfuse/graphiti-litellm/secret-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "email/gmail/account1/adress" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0400";
        };
        "email/gmail/account1/app-password" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0400";
        };
        "email/gmail/account2/adress" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0400";
        };
        "email/gmail/account2/app-password" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0400";
        };
      };

      users.users.likivik.initialHashedPassword = "$6$1FZNn7nnzCyHhgke$jyU9Ou3/5F2IHWLMGPc/bCDMQctvmKRXWCT6SAmUjhnHXmiOVFMhh4vVFxAoHZ8izk.QhQoyFZlvut6WOxXgb0";
      users.users.likivik.openssh.authorizedKeys.keys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIECMxs9cBFN8Adq8AJ9I62gVNFTkgNkr0ikg+VkWbHx1 hermes@erebus"
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
      ];

      security.sudo.extraRules = [
        {
          users = [ "likivik" ];
          commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
        }
        {
          users = [ "hermes" ];
          commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
        }
      ];

      services.tailscale.authKeyFile =
        config.sops.secrets."tailscale/auth-key".path;
      services.tailscale.extraUpFlags = lib.mkAfter [
        "--advertise-tags=tag:server,tag:exit-node,tag:nix-binary-caches"
        "--advertise-exit-node"
        "--advertise-connector"
      ];

      # Tailscale app connector requires IP forwarding to route traffic
      # for the configured domains (install.determinate.systems,
      # cache.flakehub.com, nix-community.cachix.org, hyprland.cachix.org,
      # cache.nixos.org) through this host to the public internet.
      boot.kernel.sysctl."net.ipv4.ip_forward" = 1;
      boot.kernel.sysctl."net.ipv6.conf.all.forwarding" = 1;


      systemd.services.fix-ts-gro = {
        description = "Fix UDP GRO forwarding for Tailscale exit node performance";
        wants = [ "network-online.target" ];
        after = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig.Type = "oneshot";
        script = ''
          ${pkgs.ethtool}/bin/ethtool -K ens3 rx-udp-gro-forwarding on rx-gro-list off
        '';
      };

      environment.systemPackages = with pkgs; [
        nodejs_22 uv git gh pkgs.jujutsu
        # Office document skills (docx/xlsx/powerpoint): soffice + pandoc + poppler
        # npm helpers `docx` and `pptxgenjs` are installed by the skill on first require
        libreoffice
        pandoc
        poppler-utils
        ffmpeg
        (python3.withPackages (ps: [ ps.numpy ps.pillow ]))
      ];



    };
  };
}
