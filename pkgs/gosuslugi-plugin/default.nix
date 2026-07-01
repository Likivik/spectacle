{ stdenv, lib, fetchurl, autoPatchelfHook, coreutils, gnugrep, gnutar, dpkg, binutils, bubblewrap
, cups, fontconfig, freetype, harfbuzz, libdrm, libinput, libGL, libjpeg_turbo, mesa
, mtdev, pcsclite, sqlite
, libICE, libSM, libX11, libXi, libXrender, libxcb
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
    harfbuzz
    libdrm
    libGL
    libinput
    libjpeg_turbo
    mesa
    mtdev
    pcsclite
    sqlite
    stdenv.cc.cc.lib
    libICE
    libSM
    libX11
    libXi
    libXrender
    libxcb
  ];

  unpackPhase = ''
    payload_line=$(${gnugrep}/bin/grep --text --line-number '^PAYLOAD:$' $src | ${coreutils}/bin/cut -d: -f1)
    ${coreutils}/bin/tail -n +$((payload_line + 1)) $src > $TMPDIR/payload.tar
    ${gnutar}/bin/tar -xf $TMPDIR/payload.tar -C $TMPDIR/
    ${dpkg}/bin/dpkg-deb --extract $TMPDIR/*.deb $TMPDIR/pkg
  '';

  installPhase = ''
    mkdir -p $out/opt $out/etc $out/bin
    cp -r $TMPDIR/pkg/opt/* $out/opt/
    cp -r $TMPDIR/pkg/etc/* $out/etc/
    cp -r $TMPDIR/pkg/usr $out/

    cat > $out/bin/gosuslugi-nmh << WRAPPER
#!/usr/bin/env bash
exec ${bubblewrap}/bin/bwrap \
  --unshare-user-try \
  --unshare-pid \
  --die-with-parent \
  --new-session \
  --ro-bind /nix/store /nix/store \
  --ro-bind /opt/iitrust /opt/iitrust \
  --ro-bind /etc /etc \
  --bind /run/pcscd /run/pcscd \
  --dev /dev \
  --dev-bind /dev/bus/usb /dev/bus/usb \
  --bind /dev/shm /dev/shm \
  --proc /proc \
  --tmpfs /run \
  --tmpfs /home \
  --tmpfs /Storage \
  --tmpfs /tmp \
  --share-net \
  --setenv HOME /tmp \
  --setenv TMPDIR /tmp \
  --setenv LD_LIBRARY_PATH /opt/iitrust/gosuslugi_plugin/bin:/opt/iitrust/gosuslugi_plugin/lib \
  -- \
  /opt/iitrust/gosuslugi_plugin/bin/gosuslugi_plugin "$@"
WRAPPER
    chmod +x $out/bin/gosuslugi-nmh
  '';

  dontStrip = true;

  meta = with lib; {
    description = "Gosuslugi.ru browser plugin for electronic signature";
    homepage = "https://www.gosuslugi.ru/landing/gosplugin";
    sourceProvenance = with sourceTypes; [ binaryNativeCode ];
    platforms = [ "x86_64-linux" ];
  };
}
