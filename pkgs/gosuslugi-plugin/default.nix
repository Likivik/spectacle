{ stdenv, lib, fetchurl, autoPatchelfHook, coreutils, gnugrep, gnutar, dpkg, binutils
, cups, fontconfig, freetype, libGL, pcsclite, sqlite, xorg
}:

let
  installer = fetchurl {
    url = "https://gu-st.ru/content/Gosplugin/Gosplugin_Linux-Debian_Installer.deb.zip";
    sha256 = "332b321e069c34eda5c22ded50696d5bd58df077408262c74fbe9894e7611ef8";
  };
in stdenv.mkDerivation rec {
  pname = "gosuslugi-plugin";
  version = "1.3.42.0";

  src = installer;

  nativeBuildInputs = [
    autoPatchelfHook
    binutils
    dpkg
    gnutar
    gnugrep
    coreutils
  ];

  buildInputs = [
    cups
    fontconfig
    freetype
    libGL
    pcsclite
    sqlite
    stdenv.cc.cc.lib
    xorg.libX11
    xorg.libxcb
  ];

  unpackPhase = ''
    payload_line=$(${gnugrep}/bin/grep --text --line-number '^PAYLOAD:$' $src | ${coreutils}/bin/cut -d: -f1)
    ${coreutils}/bin/tail -n +$((payload_line + 1)) $src > $TMPDIR/payload.tar
    ${gnutar}/bin/tar -xf $TMPDIR/payload.tar -C $TMPDIR/
    ${dpkg}/bin/dpkg-deb --extract $TMPDIR/*.deb $TMPDIR/pkg
  '';

  installPhase = ''
    mkdir -p $out/opt $out/etc
    cp -r $TMPDIR/pkg/opt/* $out/opt/
    cp -r $TMPDIR/pkg/etc/* $out/etc/
    cp -r $TMPDIR/pkg/usr $out/
  '';

  dontStrip = true;

  meta = with lib; {
    description = "Gosuslugi.ru browser plugin for electronic signature";
    homepage = "https://www.gosuslugi.ru/landing/gosplugin";
    sourceProvenance = with sourceTypes; [ binaryNativeCode ];
    platforms = [ "x86_64-linux" ];
  };
}
