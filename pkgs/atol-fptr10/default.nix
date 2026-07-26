{ lib, stdenv, dpkg, autoPatchelfHook
, qt5, libGL, libX11
, makeWrapper
}:

stdenv.mkDerivation {
  pname = "atol-fptr10";
  version = "10.10.9.0";

  src = ./debs;

  nativeBuildInputs = [ dpkg autoPatchelfHook qt5.wrapQtAppsHook makeWrapper ];

  buildInputs = [
    stdenv.cc.cc.lib
    qt5.qtbase
    libGL
    libX11
  ];

  installPhase = ''
    runHook preInstall

    for deb in $src/*.deb; do
      dpkg-deb -x "$deb" "$out"
    done

    mkdir -p "$out/bin"
    for bin_name in epc-bridge atol-fptr-rpc-server fptr10_t; do
      bin_path=$(find "$out" -type f -executable -name "$bin_name" 2>/dev/null | head -1)
      if [ -n "$bin_path" ]; then
        ln -sf "$bin_path" "$out/bin/$bin_name"
      fi
    done

    mkdir -p "$out/lib/udev/rules.d"
    cat > "$out/lib/udev/rules.d/90-atol-fptr.rules" << 'RULE'
SUBSYSTEM=="usb", ATTRS{idVendor}=="2912", MODE="666"
RULE

    mkdir -p "$out/share/icons"
    cp "${./atol-icon.png}" "$out/share/icons/atol-icon.png"

    runHook postInstall
  '';

  postFixup = ''
    wrapProgram $out/bin/fptr10_t \
      --set QT_PLUGIN_PATH "${qt5.qtbase.bin}/lib/qt-${qt5.qtbase.version}/plugins"
  '';

  dontStrip = true;

  meta = with lib; {
    description = "ATOL. Драйвер ККТ v.10 — Комплект драйверов торгового оборудования АТОЛ";
    homepage = "http://www.atol.ru";
    sourceProvenance = with sourceTypes; [ binaryNativeCode ];
    platforms = [ "x86_64-linux" ];
  };
}
