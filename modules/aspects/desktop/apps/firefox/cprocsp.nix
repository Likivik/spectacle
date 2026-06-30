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
    in {
      services.pcscd.enable = true;

      services.udev.extraRules = ''
        SUBSYSTEM=="usb", ATTRS{idVendor}=="0a89", TAG+="uaccess"
      '';

      environment.sessionVariables = {
        LD_LIBRARY_PATH = [ "/opt/cprocsp/lib/amd64" ];
      };

      environment.systemPackages = [ cprocspPkg ];

      systemd.tmpfiles.rules = [
        "L+ /opt/cprocsp - - - - ${cprocspPkg}/opt/cprocsp"
      ];

      environment.etc = {
        "ssl/certs/mintsifry-root.crt".source = certs.mintsifryRoot;
        "ssl/certs/mintsifry-sub.crt".source = certs.mintsifrySub;
        "opt/chrome/native-messaging-hosts/ru.cryptopro.nmcades.json".source =
          "${cprocspPkg}/usr/lib/mozilla/native-messaging-hosts/ru.cryptopro.nmcades.json";
        "chromium/native-messaging-hosts/ru.cryptopro.nmcades.json".source =
          "${cprocspPkg}/usr/lib/mozilla/native-messaging-hosts/ru.cryptopro.nmcades.json";
      };

      programs.firefox = {
        nativeMessagingHosts.packages = [ cprocspPkg ];
        policies.Certificates.Install = [
          "/etc/ssl/certs/mintsifry-root.crt"
          "/etc/ssl/certs/mintsifry-sub.crt"
        ];
      };
    };

    maid = { pkgs, ... }: let
      cprocspPkg = pkgs.callPackage ../../../../../pkgs/cprocsp { };
    in {
      file.xdg_config."mozilla/firefox/gov-sign/extensions/${addonId}.xpi".source =
        "${cprocspPkg}/share/mozilla/extensions/{ec8030f7-c20a-464f-9b0e-13a3a9e97384}/${addonId}.xpi";
    };
  };
}
