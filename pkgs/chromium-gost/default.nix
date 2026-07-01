{ stdenv, lib, fetchurl, autoPatchelfHook, wrapGAppsHook3, makeWrapper
, flac, gnome2, harfbuzzFull, nss, snappy, xdg-utils
, alsa-lib, atk, cairo, cups, curl, dbus, expat, fontconfig, freetype
, gdk-pixbuf, glib, gtk3, libX11, libxcb, libXScrnSaver, libXcomposite
, libXcursor, libXdamage, libXext, libXfixes, libXi, libXrandr, libXrender
, libXtst, libdrm, libnotify, libopus, libpulseaudio, libuuid, libxshmfence
, mesa, nspr, pango, systemd, at-spi2-atk, at-spi2-core
, libxkbfile, qt6, vivaldi-ffmpeg-codecs
}:

stdenv.mkDerivation rec {
  pname = "chromium-gost";
  version = "148.0.7778.280";

  src = fetchurl {
    url = "https://github.com/deemru/Chromium-Gost/releases/download/${version}/chromium-gost-${version}-linux-amd64.deb";
    sha256 = "a1e10947f7b3694d18e82f5807e2ed4af1d7e9067e8d46b22fe995e0488aa035";
  };

  nativeBuildInputs = [
    autoPatchelfHook
    wrapGAppsHook3
    makeWrapper
  ];

  buildInputs = [
    flac
    harfbuzzFull
    nss
    snappy
    xdg-utils
    libxkbfile
    alsa-lib
    at-spi2-atk
    at-spi2-core
    atk
    cairo
    cups
    curl
    dbus
    expat
    fontconfig.lib
    freetype
    gdk-pixbuf
    glib
    gnome2.GConf
    gtk3
    libX11
    libXScrnSaver
    libXcomposite
    libXcursor
    libXdamage
    libXext
    libXfixes
    libXi
    libXrandr
    libXrender
    libXtst
    libdrm
    libnotify
    libopus
    libuuid
    libxcb
    libxshmfence
    mesa
    nspr
    nss
    pango
    stdenv.cc.cc.lib
    qt6.qtbase
  ];

  autoPatchelfIgnoreMissingDeps = [
    "libQt5Core.so.5"
    "libQt5Gui.so.5"
    "libQt5Widgets.so.5"
  ];

  unpackPhase = ''
    mkdir -p $out/bin $out/share/icons/hicolor $out/opt $TMP
    cd $TMP
    ar vx $src
    tar --no-overwrite-dir -xvf data.tar.xz -C $TMP/
  '';

  installPhase = ''
    cp -r $TMP/opt/ $out/
    cp -r $TMP/usr/share $out/
    substituteInPlace $out/share/applications/chromium-gost.desktop \
      --replace /usr/ $out/
    substituteInPlace $out/share/applications/chromium-gost.desktop \
      --replace chromium-gost-stable chromium-gost
    ln -sf ${vivaldi-ffmpeg-codecs}/lib/libffmpeg.so $out/opt/chromium-gost/libffmpeg.so
    ln -sf $out/opt/chromium-gost/chromium-gost $out/bin/chromium-gost
    sizes=(16 24 32 48 64 128 256)
    for size in "''${sizes[@]}"; do
      mkdir -p "$out/share/icons/hicolor/''${size}x''${size}/apps"
      ln -s "$out/opt/chromium-gost/product_logo_$size.png" \
        "$out/share/icons/hicolor/''${size}x''${size}/apps/chromium-gost.png"
    done
    # Auto-install bundled default extensions via external_extensions.json
    cd $out/opt/chromium-gost/default_apps
    json="{"
    for crx in *.crx; do
      ext_id="''${crx%-*}"
      ext_ver="''${crx#*-}"
      ext_ver="''${ext_ver%.crx}"
      json+="\"$ext_id\":{\"external_crx\":\"$crx\",\"external_version\":\"$ext_ver\",\"external_update_url\":\"https://clients2.google.com/service/update2/crx\"},"
    done
    json="''${json%,}}"
    echo "$json" > external_extensions.json
  '';

  runtimeDependencies = map lib.getLib [
    libpulseaudio
    curl
    systemd
    vivaldi-ffmpeg-codecs
  ] ++ buildInputs;

  dontWrapQtApps = true;
  dontStrip = true;

  meta = with lib; {
    description = "Chromium with GOST encryption support";
    homepage = "https://cryptopro.ru/products/chromium-gost";
    sourceProvenance = with sourceTypes; [ binaryNativeCode ];
    platforms = [ "x86_64-linux" ];
    mainProgram = "chromium-gost";
  };
}
