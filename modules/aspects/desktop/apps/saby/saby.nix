{ den, lib, ... }: let
  cfg = "saby";

  nmhName = "ru.tensor.sbis_plugin_nmh";
  addonId = "pbcgcpeifkdjijdjambaakmhhpkfgoec";
in {
  den.aspects.${cfg} = {
    nixos = { pkgs, ... }: let
      sabyPkg = pkgs.callPackage ../../../../../pkgs/saby-nmh { };
    in {
      environment.systemPackages = [ sabyPkg ];

      systemd.tmpfiles.rules = [
        "L+ /opt/nmh-transport - - - - ${sabyPkg}/opt/nmh-transport"
      ];

      environment.etc = let
        nmhManifest = pkgs.writeText "${nmhName}.json" (builtins.toJSON {
          name = nmhName;
          description = "Saby Plugin Native Messaging Host";
          path = "${sabyPkg}/bin/saby-nmh";
          type = "stdio";
          allowed_origins = [ "chrome-extension://${addonId}/" ];
        });
        operaManifest = pkgs.writeText "opera.${nmhName}.json" (builtins.toJSON {
          name = nmhName;
          description = "Saby Plugin Native Messaging Host";
          path = "${sabyPkg}/bin/saby-nmh";
          type = "stdio";
          allowed_origins = [ "chrome-extension://npijgiimlfmdighlfbbhjmnjicedfooc/" ];
        });
      in {
        "chromium/native-messaging-hosts/${nmhName}.json".source = nmhManifest;
        "opt/chrome/native-messaging-hosts/${nmhName}.json".source = nmhManifest;
        "opt/chrome/native-messaging-hosts/opera.${nmhName}.json".source = operaManifest;
      };
    };
  };
}
