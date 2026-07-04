{ den, lib, ... }: let
  cfg = "chromium-gost";
in {
  den.aspects.${cfg} = {
    nixos = { pkgs, ... }: let
      chromiumGost = pkgs.callPackage ../../../../../pkgs/chromium-gost { };
    in {
      environment.systemPackages = [ chromiumGost ];

      environment.sessionVariables = {
        CHROME_GOST = "chromium-gost";
      };

      environment.etc."chromium/policies/managed/policy.json".text = ''
        {
          "policies": {
            "BackgroundModeEnabled": true,
            "AutoFillEnabled": false,
            "PasswordManagerEnabled": false,
            "ExtensionInstallForcelist": [
              "pbcgcpeifkdjijdjambaakmhhpkfgoec;https://clients2.google.com/service/update2/crx",
              "hnhppcgejeffnbnioloohhmndpmclaga;https://clients2.google.com/service/update2/crx",
              "nejicfcnfnecdilmajlppdcgbjilgeec;https://clients2.google.com/service/update2/crx",
              "akpjpngckapnibajopggmfhnchfpnkkf;https://clients2.google.com/service/update2/crx",
              "momffihklfhkoakghidmkdocdkbfmoac;https://clients2.google.com/service/update2/crx",
              "kbeplgmhdbgnbpfkcmndbhjfadkhinhn;https://clients2.google.com/service/update2/crx",
              "nhbmmgegnhdhkcclaandbaipceebnckc;https://clients2.google.com/service/update2/crx"
            ]
          }
        }
      '';

      environment.etc."chromium/extensions/pbcgcpeifkdjijdjambaakmhhpkfgoec.json".source =
        pkgs.writeText "pbcgcpeifkdjijdjambaakmhhpkfgoec.json" (builtins.toJSON {
          external_crx = "${chromiumGost}/opt/chromium-gost/default_apps/pbcgcpeifkdjijdjambaakmhhpkfgoec-26.3213.2.crx";
          external_version = "26.3213.2";
          external_update_url = "https://clients2.google.com/service/update2/crx";
        });
    };
  };
}
