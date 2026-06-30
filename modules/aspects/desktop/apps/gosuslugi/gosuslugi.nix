{ den, lib, ... }: let
  cfg = "gosuslugi";
in {
  den.aspects.${cfg} = {
    nixos = { pkgs, ... }: let
      gosuslugiPkg = pkgs.callPackage ../../../../../pkgs/gosuslugi-plugin { };
    in {
      environment.systemPackages = [ gosuslugiPkg ];

      systemd.tmpfiles.rules = [
        "L+ /opt/iitrust - - - - ${gosuslugiPkg}/opt/iitrust"
      ];

      environment.etc."chromium/native-messaging-hosts/chrome.gosuslugi.plugin.json".source =
        "${gosuslugiPkg}/etc/chromium/native-messaging-hosts/chrome.gosuslugi.plugin.json";
      environment.etc."chromium/native-messaging-hosts/opera.gosuslugi.plugin.json".source =
        "${gosuslugiPkg}/etc/chromium/native-messaging-hosts/opera.gosuslugi.plugin.json";
    };
  };
}