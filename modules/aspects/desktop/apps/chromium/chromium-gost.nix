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
            "PasswordManagerEnabled": false
          }
        }
      '';
    };
  };
}
