{ lib, stdenv, fetchFromGitHub, fetchzip, fetchurl, zstd }:

let
  arcAurora = stdenv.mkDerivation {
    name = "arc-aurora-cursors";
    src = fetchFromGitHub {
      owner = "yeyushengfan258";
      repo = "ArcAurora-Cursors";
      rev = "9689e49487818bface315f8cf1d2c4f860f050a7";
      hash = "sha256-u/x8aEeOskv6R8uCB4ojn9tXxTxflejWACxgp03o9PI=";
    };
    installPhase = ''
      mkdir -p $out/share/icons
      cp -r dist/* $out/share/icons/
    '';
  };

  afterglow = stdenv.mkDerivation {
    name = "afterglow-cursors";
    src = fetchFromGitHub {
      owner = "yeyushengfan258";
      repo = "Afterglow-Cursors";
      rev = "424a3326827f3bc56856fc5a3a1cce8da1ea3ecd";
      hash = "sha256-Kv4/MyuZXicM0rT89lZZd7AUwxb55bq0lYEetSybFTk=";
    };
    installPhase = ''
      mkdir -p $out/share/icons
      cp -r dist/* $out/share/icons/
    '';
  };

  aosp = stdenv.mkDerivation {
    name = "aosp-cursors";
    src = fetchzip {
      url = "https://github.com/Tech-Tac/aosp-cursors/releases/download/1.1.0/aosp-cursors-linux-1.1.0.tar.xz";
      hash = "sha256-0ym7ky6apj50bfcwzh7swnnzxpy7amj5zzn11xri3sc8viygaazp";
    };
    installPhase = ''
      mkdir -p $out/share/icons
      cp -r aosp-cursors/* $out/share/icons/
    '';
  };

  pixelfun2 = stdenv.mkDerivation {
    name = "pixelfun2-cursors";
    src = fetchurl {
      url = "https://aur.archlinux.org/cgit/aur.git/plain/xcur-pixelfun-all-merge.tar.zst?h=xcursor-pixelfun-all";
      hash = "sha256-1dwn3wl358aahw14y9zq83k4z0vphvvpr75qvzyr0srnrhxga705";
    };
    nativeBuildInputs = [ zstd ];
    unpackPhase = ''
      zstd -d < $src | tar xf -
    '';
    installPhase = ''
      mkdir -p $out/share/icons
      cp -r ./* $out/share/icons/
    '';
  };
in {
  inherit arcAurora afterglow aosp pixelfun2;
}
