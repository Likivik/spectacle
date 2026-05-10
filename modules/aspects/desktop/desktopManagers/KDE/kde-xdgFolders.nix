{ inputs, den, ... }:
{
  den.aspects.kde-xdgFolders = {
    nixos = { config, pkgs, lib, ... }: {
      nixpkgs.overlays = [
        (final: prev: {
          kdePackages = prev.kdePackages // {
            plasma-workspace =
              let
                basePkg = prev.kdePackages.plasma-workspace;

                xdgdataPkg = pkgs.stdenv.mkDerivation {
                  name = "${basePkg.name}-xdgdata";
                  buildInputs = [ basePkg ];
                  dontUnpack = true;
                  dontFixup = true;
                  dontWrapQtApps = true;
                  installPhase = ''
                    mkdir -p $out/share
                    ( IFS=:
                      for DIR in $XDG_DATA_DIRS; do
                        if [[ -d "$DIR" ]]; then
                          cp -r $DIR/. $out/share/
                          chmod -R u+w $out/share
                        fi
                      done
                    )
                  '';
                };

                derivedPkg = basePkg.overrideAttrs {
                  preFixup = ''
                    for index in "''${!qtWrapperArgs[@]}"; do
                      if [[ ''${qtWrapperArgs[$((index+0))]} == "--prefix" ]] && [[ ''${qtWrapperArgs[$((index+1))]} == "XDG_DATA_DIRS" ]]; then
                        unset -v "qtWrapperArgs[$((index+0))]"
                        unset -v "qtWrapperArgs[$((index+1))]"
                        unset -v "qtWrapperArgs[$((index+2))]"
                        unset -v "qtWrapperArgs[$((index+3))]"
                      fi
                    done
                    qtWrapperArgs=("''${qtWrapperArgs[@]}")
                    qtWrapperArgs+=(--prefix XDG_DATA_DIRS : "${xdgdataPkg}/share")
                    qtWrapperArgs+=(--prefix XDG_DATA_DIRS : "$out/share")
                  '';
                };
              in
              derivedPkg;
          };
        })
      ];
    };
  };
}