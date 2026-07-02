{ den, lib, ... }: let
  cfg = "kontur";

  addonIds = [
    "hnhppcgejeffnbnioloohhmndpmclaga"
    "nejicfcnfnecdilmajlppdcgbjilgeec"
    "akpjpngckapnibajopggmfhnchfpnkkf"
    "momffihklfhkoakghidmkdocdkbfmoac"
    "kbeplgmhdbgnbpfkcmndbhjfadkhinhn"
    "nhbmmgegnhdhkcclaandbaipceebnckc"
  ];
in {
  den.aspects.${cfg} = {
    nixos = { pkgs, ... }: let
      konturPkg = pkgs.callPackage ../../../../../pkgs/kontur-plugin { };
    in {
      environment.systemPackages = [ konturPkg ];

      systemd.tmpfiles.rules = [
        "L+ /opt/kontur.plugin - - - - ${konturPkg}/opt/kontur.plugin"
      ];

      environment.etc = let
        chromeManifest = pkgs.writeText "kontur.plugin.json" (builtins.toJSON {
          name = "kontur.plugin";
          description = "Kontur.Plugin";
          path = "${konturPkg}/bin/kontur-nmh";
          type = "stdio";
          allowed_origins = map (id: "chrome-extension://${id}/") addonIds;
        });
      in {
        "chromium/native-messaging-hosts/kontur.plugin.json".source = chromeManifest;
        "opt/chrome/native-messaging-hosts/kontur.plugin.json".source = chromeManifest;
      };
    };
  };
}
