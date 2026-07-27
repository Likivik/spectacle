{ den, ... }:
{
  den.aspects.kde-env-dedup = {
    nixos =
      { pkgs, ... }:
      let
        env-dedup = pkgs.stdenv.mkDerivation {
          pname = "env-dedup";
          version = "unstable-2026";

          src = pkgs.fetchFromGitHub {
            owner = "alexjp";
            repo = "env-dedup";
            rev = "9df9f75c47bef6957245b0bf6f32720a67dad3a0";
            sha256 = "sha256-05d7amy6zd5mld55y19r59bcr4nixig4cxncqq97vq7wxhf23sb8";
          };

          buildInputs = [ pkgs.gcc ];

          buildPhase = ''
            gcc -shared -fPIC -o libenv_dedup_dynamic.so env_dedup_dynamic.c -ldl
          '';

          installPhase = ''
            mkdir -p $out/lib
            cp libenv_dedup_dynamic.so $out/lib/
          '';
        };
      in
      {
        environment.etc."xdg/plasma-workspace/env/00-env-dedup.sh" = {
          text = ''
            #!/bin/sh
            export LD_PRELOAD="${env-dedup}/lib/libenv_dedup_dynamic.so"
          '';
          mode = "0755";
        };
      };
  };
}
