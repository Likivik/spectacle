{ den, inputs, lib, ... }:
{
  den.aspects.afterglow-avia = {

    includes = [
      den.aspects.core
      den.aspects.desktop.desktopManagers.kde
      den.aspects.desktop.common-core
      den.aspects.firefox
    ];

    nixos = { config, lib, pkgs, modulesPath, ... }: let
      atolPkg = pkgs.callPackage ../../../pkgs/atol-fptr10 { };
      kkmPkg = pkgs.callPackage ../../../pkgs/kkmserver { };
    in {
      imports = [
        inputs.disko.nixosModules.disko
        ./_hardware-configuration.nix
        ./_disko.nix
      ];

      nix.settings.trusted-users = [ "likivik" ];
      nix.settings.require-sigs = false;
      users.mutableUsers = false;

      # --- Boot ----------------------------------------------------------
      boot.loader.systemd-boot.enable = true;
      boot.loader.efi.canTouchEfiVariables = true;

      # --- Networking ---------------------------------------------------
      networking.hostName = "afterglow-avia";
      networking.networkmanager.enable = true;

      # kkmserver HTTP endpoint (default port 5893) — local-only by default;
      # remove the restriction if yclients runs on a separate browser client.
      networking.firewall.allowedTCPPorts = [ 5893 ];

      # --- Locale -------------------------------------------------------
      # kkmserver expects ru_RU.UTF-8; keep en_US.UTF-8 for system fallback.
      i18n.defaultLocale = lib.mkForce "ru_RU.UTF-8";
      i18n.extraLocales = [
        "en_US.UTF-8/UTF-8"
      ];
      i18n.extraLocaleSettings = lib.mkForce {

					LC_CTYPE = "ru_RU.UTF-8";
					LC_ADDRESS = "ru_RU.UTF-8";
					LC_MEASUREMENT = "ru_RU.UTF-8";
					LC_MESSAGES = "ru_RU.UTF-8";
					LC_MONETARY = "ru_RU.UTF-8";
					LC_NAME = "ru_RU.UTF-8";
					LC_NUMERIC = "ru_RU.UTF-8";
					LC_PAPER = "ru_RU.UTF-8";
					LC_TELEPHONE = "ru_RU.UTF-8";
					LC_TIME = "ru_RU.UTF-8";
					LC_IDENTIFICATION = "ru_RU.UTF-8";
					LC_COLLATE = "ru_RU.UTF-8";
					# Добавьте эту строку, чтобы Plasma знала приоритет перевода
    			LANGUAGE = "ru_RU.UTF-8:ru";
				};
      time.timeZone = "Europe/Moscow";

      # --- SSH server (admin remote access) -----------------------------
      services.openssh = {
        enable = true;
        settings = {
          PermitRootLogin = "no";
          PasswordAuthentication = false;
        };
      };

      # --- SDDM: hide admin user from login screen ----------------------
      services.displayManager.sddm.settings = {
        Users.HideUsers = "likivik";
      };

      # --- Kernel modules for USB-serial (ATOL 30F USB-to-COM) ----------
      boot.kernelModules = [ "cdc_acm" "usbserial" ];

      # --- Users --------------------------------------------------------
      users.users.likivik = {
        isNormalUser = true;
        extraGroups = [ "wheel" "dialout" "networkmanager" ];
        hashedPassword = "$y$j9T$R9eBnXGe7BSwwvQjckJSR/$1QLr2cy/PuJhanozDxJl2D5Vd9xJZ/WbJdKaRuhsQkB";
        openssh.authorizedKeys.keys = [
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEhOOKKg6lHLhp2x3lAIg6bFheG8SlN+vsnFeTmIRBLo root@bistre-prase24161"
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIECMxs9cBFN8Adq8AJ9I62gVNFTkgNkr0ikg+VkWbHx1 hermes@erebus"
          "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
        ];
      };
      users.users.solarium = {
        isNormalUser = true;
        extraGroups = [ "dialout" "networkmanager" ];
        description = "Solarium ☀️";
        hashedPassword = "$y$j9T$LSvv7LmxMtJpVtn0PYW4y0$FLeIVFs/VPcOgCA01mz.vtKDXnFnZEoW/2VbvBHTMgB";
        openssh.authorizedKeys.keys = [
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEhOOKKg6lHLhp2x3lAIg6bFheG8SlN+vsnFeTmIRBLo root@bistre-prase24161"
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIECMxs9cBFN8Adq8AJ9I62gVNFTkgNkr0ikg+VkWbHx1 hermes@erebus"
          "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
        ];
      };

      security.sudo.extraRules = [{
        users = [ "likivik" ];
        commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
      }];

      # --- udev rules for ATOL USB device -------------------------------
      services.udev.packages = [ atolPkg ];

      # --- systemd services ---------------------------------------------

      systemd.services.kkmserver = {
        description = "kkmserver KKM Web-server (HTTP port 5893)";
        after = [ "network.target" "systemd-udevd.service" "epc-bridge.service" "epc-mdl.service" "atol-fptr-rpc-server.service" ];
        wants = [ "network.target" "systemd-udevd.service" "epc-bridge.service" "epc-mdl.service" "atol-fptr-rpc-server.service" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          Type = "simple";
          User = "kkmserver";
          Group = "kkmserver";
          StateDirectory = "kkmserver";
          WorkingDirectory = "${kkmPkg}/opt/kkmserver";
          # kkmserver -s reads stdin for the exit command ("x").
          # Without a TTY, stdin → EOF → kkmserver exits immediately.
          # script(1) creates a PTY; read() on the slave blocks forever.
          ExecStart = "${pkgs.util-linux}/bin/script -qfc '${kkmPkg}/bin/kkmserver -s' /dev/null";
          Restart = "on-failure";
          RestartSec = 5;
          # Bind-mount rw Settings overlay on top of the nix-store path so
          # .NET's assembly-location-relative path resolution finds writable
          # config/logs (nix store itself is read-only).
          BindPaths = [ "/var/lib/kkmserver/Settings:${kkmPkg}/opt/kkmserver/Settings" ];
          # OpenSSL/Kerberos are dlopened by .NET at runtime
          Environment = [
            "LD_LIBRARY_PATH=${kkmPkg}/opt/kkmserver:${pkgs.openssl.out}/lib:${atolPkg}/usr/lib:${atolPkg}/usr/lib/fptr10"
            "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1"
            "QT_PLUGIN_PATH=${pkgs.qt5.qtbase.bin}/lib/qt-${pkgs.qt5.qtbase.version}/plugins"
          ];
        };
        preStart = ''
          # Copy defaults from the pristine copy (not bind-mounted Settings/)
          DEFAULTS_DIR="${kkmPkg}/opt/kkmserver/Settings.defaults"
          STATE_DIR="/var/lib/kkmserver/Settings"
          mkdir -p "$STATE_DIR"

          for f in SettingsServ.ini UnitServer.crt UnitServer.pem UnitServer.p12 \
                   ch.kkmserver.addin.io.json ff.kkmserver.addin.io.json; do
            [ -e "$STATE_DIR/$f" ] || cp "$DEFAULTS_DIR/$f" "$STATE_DIR/$f"
            [ -e "$DEFAULTS_DIR/$f" ] || true
          done

          chmod -R u+rw "$STATE_DIR"
        '';
      };

      systemd.services.epc-bridge = {
        description = "ATOL EPC Bridge (USB-to-COM for ATOL 30F)";
        after = [ "systemd-udevd.service" ];
        wants = [ "systemd-udevd.service" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          Type = "simple";
          User = "kkmserver";
          Group = "kkmserver";
          ExecStart = "${atolPkg}/bin/epc-bridge";
          Restart = "on-failure";
          RestartSec = 5;
          Environment = [
            "LD_LIBRARY_PATH=${atolPkg}/usr/lib:${atolPkg}/usr/lib/fptr10"
          ];
        };
      };

      systemd.services.epc-mdl = {
        description = "ATOL EPC MDL (Platform Module for ATOL 30F)";
        after = [ "systemd-udevd.service" ];
        wants = [ "systemd-udevd.service" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          Type = "simple";
          User = "kkmserver";
          Group = "kkmserver";
          ExecStart = "${atolPkg}/opt/epc/mdl/bin/epc-mdl";
          Restart = "on-failure";
          RestartSec = 5;
          Environment = [
            "LD_LIBRARY_PATH=${atolPkg}/usr/lib:${atolPkg}/usr/lib/fptr10"
          ];
        };
      };

      systemd.services.atol-fptr-rpc-server = {
        description = "ATOL RPC Server (remote KKM access)";
        after = [ "systemd-udevd.service" "epc-bridge.service" ];
        wants = [ "systemd-udevd.service" "epc-bridge.service" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          Type = "simple";
          User = "kkmserver";
          Group = "kkmserver";
          ExecStart = "${atolPkg}/bin/atol-fptr-rpc-server";
          Restart = "on-failure";
          RestartSec = 5;
          Environment = [
            "LD_LIBRARY_PATH=${atolPkg}/usr/lib:${atolPkg}/usr/lib/fptr10"
          ];
        };
      };

      # --- kkmserver system user (needs dialout for serial access) -----
      users.users.kkmserver = {
        isSystemUser = true;
        group = "kkmserver";
        extraGroups = [ "dialout" ];
        home = "/var/lib/kkmserver";
        shell = pkgs.bash;
      };
      users.groups.kkmserver = { };

      # --- tempfiles for ATOL log/data dirs -----------------------------
      systemd.tmpfiles.rules = [
        "d /var/lib/kkmserver/Settings 0755 kkmserver kkmserver -"
        "d /var/log/ATOL/AtolEpcBridge 0755 kkmserver kkmserver -"
        "d /var/log/AtolFptrRpcServer 0755 kkmserver kkmserver -"
        "d /var/lib/AtolFptrRpcServer 0755 kkmserver kkmserver -"
        "d /var/log/epc/epcbridge 0755 kkmserver kkmserver -"
        "d /var/log/epc/mdl 0755 kkmserver kkmserver -"
        "d /var/log/epc/upd 0755 kkmserver kkmserver -"
        "d /etc/epc/epcbridge 0755 kkmserver kkmserver -"
        "f /etc/epc/epcbridge/config.yml 0644 kkmserver kkmserver -"
        "d /etc/epc/mdl 0755 kkmserver kkmserver -"
      ];

      # --- KDE desktop launchers ----------------------------------------
      environment.systemPackages = [
        atolPkg
        kkmPkg
        pkgs.chromium
        (pkgs.makeDesktopItem {
          name = "kkmserver-webui";
          exec = "${pkgs.firefox}/bin/firefox http://localhost:5893/";
          icon = "${kkmPkg}/opt/kkmserver/html/Logo-KkmServer.png";
          comment = "KkmServer Web Interface — config and diagnostics";
          desktopName = "KkmServer";
          categories = [ "Network" ];
        })
        (pkgs.makeDesktopItem {
          name = "atol-fptr10-test";
          exec = "${atolPkg}/bin/fptr10_t";
          icon = "${atolPkg}/share/icons/atol-icon.png";
          comment = "ATOL Driver Test Utility — test KKM connection, send test checks";
          desktopName = "ATOL KKT Test";
          categories = [ "Utility" ];
        })
      ];

      # --- Firefox native messaging host for kkmserver browser add-in --
      environment.etc = let
        kkmNmhManifest = pkgs.writeText "kkmserver.addin.io.json" (builtins.toJSON {
          name = "kkmserver.addin.io";
          description = "KkmServer Addin";
          path = "${kkmPkg}/opt/kkmserver/kkmserver";
          type = "stdio";
        });
      in {
        "chromium/native-messaging-hosts/kkmserver.addin.io.json".source = kkmNmhManifest;
        "opt/chrome/native-messaging-hosts/kkmserver.addin.io.json".source = kkmNmhManifest;
      };

    };

  };

}