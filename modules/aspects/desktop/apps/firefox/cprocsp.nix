{ den, lib, ... }:

let
  certs = {
    mintsifryRoot = ./certs/mintsifry-root.crt;
    mintsifrySub = ./certs/mintsifry-sub.crt;
  };

  addonId = "ru.cryptopro.nmcades@cryptopro.ru";
in
{
  den.aspects.cprocsp = {

    nixos = { pkgs, ... }: let
      cprocspPkg = pkgs.callPackage ../../../../../pkgs/cprocsp { };

      # The package ships config64.ini with @ac_default_prefix@ left
      # unsubstituted and no providers listed, so CryptAcquireContext fails with
      # 0x80090017/0x8009001d and nothing (cpconfig, csptest, the browser plugin)
      # can open a container. This is the vendor template after the prefix
      # substitution and with the GOST providers 75/80/81 baked in, so
      # `cpconfig -defprov` is never needed at runtime. Table format mirrors what
      # `cpconfig -defprov -setdef` writes: cpconfig wants `\\` between the key
      # components and a quote around any name that contains spaces.
      config64 = ../../../../../pkgs/cprocsp/config64.ini;
    in {
      services.pcscd.enable = true;

      services.udev.extraRules = ''
        SUBSYSTEM=="usb", ATTRS{idVendor}=="0a89", TAG+="uaccess"
      '';

      # pcscd (built with polkit) rejects every non-root PC/SC client with
      # "IsClientAuthorized() ... NOT authorized for action: access_pcsc".
      # Root CLI tools keep working, so the failure only shows up in the
      # browser plugin, which runs as the desktop user.
      security.polkit.extraConfig = ''
        polkit.addRule(function (action, subject) {
          if (
            (action.id === "org.debian.pcsc-lite.access_pcsc" ||
              action.id === "org.debian.pcsc-lite.access_card") &&
            subject.isInGroup("users")
          ) {
            return polkit.Result.YES;
          }
        });
      '';

      environment.sessionVariables = {
        LD_LIBRARY_PATH = [ "/opt/cprocsp/lib/amd64" ];
      };

      environment.systemPackages = [ cprocspPkg ];

      systemd.tmpfiles.rules = [
        "L+ /opt/cprocsp - - - - ${cprocspPkg}/opt/cprocsp"
        # CSP writes its key store and per-user state here. The package ships
        # these dirs read-only inside the store, so they must be recreated
        # writable on the real filesystem.
        "d /var/opt/cprocsp 0755 root root -"
        "d /var/opt/cprocsp/keys 0755 root root -"
        "d /var/opt/cprocsp/users 0755 root root -"
      ];

      environment.etc = let
        nmhManifest = pkgs.writeText "ru.cryptopro.nmcades.json" (builtins.toJSON {
          name = "ru.cryptopro.nmcades";
          description = "CryptoPro CAdES Browser Plug-in";
          path = "${cprocspPkg}/bin/cprocsp-nmh";
          type = "stdio";
          allowed_origins = [ "chrome-extension://iifchhfnnmpdbibifmljnfjhpififfog/" ];
        });
      in {
        "opt/cprocsp/config64.ini".source = config64;
        "ssl/certs/mintsifry-root.crt".source = certs.mintsifryRoot;
        "ssl/certs/mintsifry-sub.crt".source = certs.mintsifrySub;
        "chromium/native-messaging-hosts/ru.cryptopro.nmcades.json".source = nmhManifest;
        "opt/chrome/native-messaging-hosts/ru.cryptopro.nmcades.json".source = nmhManifest;
      };

      programs.firefox.policies.Certificates.Install = [
        "/etc/ssl/certs/mintsifry-root.crt"
        "/etc/ssl/certs/mintsifry-sub.crt"
      ];
    };

    maid = { pkgs, ... }: let
      cprocspPkg = pkgs.callPackage ../../../../../pkgs/cprocsp { };
    in {
      file.xdg_config."mozilla/firefox/gov-sign/extensions/${addonId}.xpi".source =
        "${cprocspPkg}/share/mozilla/extensions/{ec8030f7-c20a-464f-9b0e-13a3a9e97384}/${addonId}.xpi";
    };
  };
}
