{
  den,
  lib,
  inputs,
  ...
}:
{
  den.aspects.traversal = {

    includes = [
      den.aspects.core
      den.aspects.server.sops
      den.aspects.desktop.common-core

      den.aspects.desktop.desktopManagers.dank-material-shell

      den.aspects.dev

      den.aspects.cprocsp
      den.aspects.chromium-gost
      den.aspects.gosuslugi
      den.aspects.saby
      den.aspects.kontur
      den.aspects.firefox
      den.aspects.tts
    ];

    nixos =
      { config, pkgs, modulesPath, ... }:
      {
        imports = [ (modulesPath + "/installer/scan/not-detected.nix") ];

        # sops-nix on traversal uses the TPM identity (no SSH host key).
        sops.age.sshKeyPaths = lib.mkForce [ ];
        sops.age.keyFile = "/var/lib/sops/tpm-identity.txt";

        sops.secrets."obsidian/obsidian-sync-mcp/mcp-auth-token" = {
          sopsFile = ../../../secrets/traversal/secrets.yaml;
          owner = "likivik";
          group = "users";
          mode = "0600";
        };

        # services.openssh.enable = true;

        hardware.amdgpu.initrd.enable = lib.mkDefault true;

        services.xserver.videoDrivers = lib.mkDefault [ "modesetting" ];

        hardware.graphics = {
          enable = lib.mkDefault true;
          enable32Bit = lib.mkDefault true;
        };

        services.tlp.enable = lib.mkDefault (!config.services.power-profiles-daemon.enable);

        services.fstrim.enable = lib.mkDefault true;

        boot.initrd.availableKernelModules = [
          "nvme"
          "xhci_pci"
          "thunderbolt"
          "usb_storage"
          "sd_mod"
          "sdhci_pci"
        ];
        boot.initrd.kernelModules = [ ];
        boot.kernelModules = [ "kvm-amd" ];
        boot.extraModulePackages = [ ];

        fileSystems."/" = {
          device = "/dev/disk/by-uuid/ef9e9419-e98c-4667-a569-e1afeedf3df4";
          fsType = "btrfs";
        };

        fileSystems."/boot" = {
          device = "/dev/disk/by-uuid/CABA-4BEE";
          fsType = "vfat";
          options = [
            "fmask=0077"
            "dmask=0077"
          ];
        };

        swapDevices = [
          { device = "/dev/disk/by-uuid/1385a7cc-ed8e-4567-a77d-0a11bf7f8ac1"; }
        ];

        # Enables DHCP on each ethernet and wireless interface. In case of scripted networking
        # (the default) this is the recommended approach. When using systemd-networkd it's
        # still possible to use this option, but it's recommended to use it in conjunction
        # with explicit per-interface declarations with `networking.interfaces.<interface>.useDHCP`.
        networking.useDHCP = lib.mkDefault true;
        # networking.interfaces.enp2s0.useDHCP = lib.mkDefault true;
        # networking.interfaces.wlo1.useDHCP = lib.mkDefault true;

        services.logind.settings = {
          Login.HandleLidSwitch = "ignore";
          Login.HandleLidSwitchExternalPower = "ignore";
        };

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

        nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
        hardware.cpu.amd.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;

      };

  };
}
