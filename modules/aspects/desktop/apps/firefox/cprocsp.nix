{ den, lib, ... }:

let
  certs = {
    mintsifryRoot = ./certs/mintsifry-root.crt;
    mintsifrySub = ./certs/mintsifry-sub.crt;
  };

  govPolicyJSON = builtins.toJSON {
    policies.Certificates.Install = [
      "DIST_DIR_PLACEHOLDER/mintsifry-root.crt"
      "DIST_DIR_PLACEHOLDER/mintsifry-sub.crt"
    ];
  };
in
{
  den.aspects.cprocsp = {

    nixos = { pkgs, ... }: {
      services.pcscd.enable = true;

      services.udev.extraRules = ''
        # Rutoken EDS (all models — VID 0a89)
        SUBSYSTEM=="usb", ATTRS{idVendor}=="0a89", TAG+="uaccess"
      '';

      environment.sessionVariables = {
        LD_LIBRARY_PATH = [ "/opt/cprocsp/lib/amd64" ];
      };
    };

    homeManager =
    { lib, ... }:
    {

      programs.firefox.profiles.gov-sign = {
        id = 1;
        name = "gov-sign";
        settings = {
          "browser.theme.content-theme" = 2;
          "browser.theme.toolbar-theme" = 3;
          "browser.shell.checkDefaultBrowser" = false;
        };
      };

      home.activation.installMintsifryCA = lib.hm.dag.entryAfter ["writeBoundary"] ''
        PROFILE_DIR=$(ls -d "$HOME/.mozilla/firefox/"*.gov-sign 2>/dev/null | head -1)
        if [ -z "$PROFILE_DIR" ]; then
          echo "cprocsp: gov-sign profile not found, skipping CA install"
          exit 0
        fi

        DIST_DIR="$PROFILE_DIR/distribution"
        mkdir -p "$DIST_DIR"

        cp -f ${certs.mintsifryRoot} "$DIST_DIR/mintsifry-root.crt"
        cp -f ${certs.mintsifrySub} "$DIST_DIR/mintsifry-sub.crt"

        echo '${govPolicyJSON}' \
          | sed "s|DIST_DIR_PLACEHOLDER|$DIST_DIR|g" \
          > "$DIST_DIR/policies.json"

        echo "cprocsp: installed Минцифры CA into gov-sign profile"
      '';
    };

  };
}
