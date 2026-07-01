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

      environment.etc = let
        chromeManifest = pkgs.writeText "chrome.gosuslugi.plugin.json" (builtins.toJSON {
          description = "chrome.gosuslugi.plugin";
          name = "chrome.gosuslugi.plugin";
          allowed_origins = [ "chrome-extension://jabjbhgjaidecageckilhonbggakppme/" ];
          path = "${gosuslugiPkg}/bin/gosuslugi-nmh";
          type = "stdio";
        });
        operaManifest = pkgs.writeText "opera.gosuslugi.plugin.json" (builtins.toJSON {
          description = "opera.gosuslugi.plugin";
          name = "opera.gosuslugi.plugin";
          allowed_origins = [ "chrome-extension://npijgiimlfmdighlfbbhjmnjicedfooc/" ];
          path = "${gosuslugiPkg}/bin/gosuslugi-nmh";
          type = "stdio";
        });
      in {
        "chromium/native-messaging-hosts/chrome.gosuslugi.plugin.json".source = chromeManifest;
        "chromium/native-messaging-hosts/opera.gosuslugi.plugin.json".source = operaManifest;
      };
    };
  };
}