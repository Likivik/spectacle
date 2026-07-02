{ stdenv, lib, fetchurl, dpkg, autoPatchelfHook, bubblewrap, coreutils
, cups, fontconfig, freetype, pcsclite
, gtk3, gdk-pixbuf, pango, cairo, atk, glib
, libX11, libXext, libXinerama, libXfixes, libXcursor, libXrender, libXft
}:

let
  version = "4.13.0.4561";
in stdenv.mkDerivation {
  pname = "kontur-plugin";
  inherit version;

  src = fetchurl {
    url = "https://install.kontur.ru/files/kontur.plugin_amd64.deb";
    sha256 = "sha256-k6wRzEQHx8v0551/HuJpOPimVneAfQuB34ncqG6JrfY=";
  };

  nativeBuildInputs = [ dpkg autoPatchelfHook ];

  buildInputs = [
    stdenv.cc.cc.lib
    atk cairo cups fontconfig freetype
    gdk-pixbuf glib gtk3 pango pcsclite
    libX11 libXcursor libXext libXfixes libXft libXinerama libXrender
  ];

  installPhase = ''
    runHook preInstall

    mkdir -p $out/opt $out/bin
    dpkg-deb -x $src $TMPDIR/pkg
    cp -r $TMPDIR/pkg/opt/kontur.plugin $out/opt/
    rm -f $out/opt/kontur.plugin/kontur.plugin.assistant

    cat > $out/bin/kontur-nmh << 'WRAPPER'
#!/usr/bin/env bash
mkdir -p "$HOME/.config/kontur.plugin" 2>/dev/null || true
exec ${bubblewrap}/bin/bwrap \
  --unshare-user-try \
  --unshare-pid \
  --die-with-parent \
  --new-session \
  --ro-bind /nix/store /nix/store \
  --ro-bind /opt/kontur.plugin /opt/kontur.plugin \
  --ro-bind /opt/cprocsp /opt/cprocsp \
  --ro-bind /etc /etc \
  --bind /run/pcscd /run/pcscd \
  --dev /dev \
  --dev-bind /dev/bus/usb /dev/bus/usb \
  --bind /dev/shm /dev/shm \
  --proc /proc \
  --tmpfs /run \
  --tmpfs /home \
  --bind "$HOME/.config/kontur.plugin" "$HOME/.config/kontur.plugin" \
  --tmpfs /Storage \
  --tmpfs /tmp \
  --share-net \
  --setenv QT_QPA_PLATFORM offscreen \
  -- \
  /opt/kontur.plugin/kontur.plugin.host "$@"
WRAPPER
    chmod +x $out/bin/kontur-nmh

    runHook postInstall
  '';

  dontStrip = true;

  meta = with lib; {
    description = "Kontur.Plugin native messaging host for browser EDS signing";
    homepage = "https://kontur.ru";
    sourceProvenance = with sourceTypes; [ binaryNativeCode ];
    platforms = [ "x86_64-linux" ];
  };
}
