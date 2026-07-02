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
    };
  };
}
