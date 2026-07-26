{ lib, stdenv, fetchurl, dpkg, autoPatchelfHook, makeWrapper
, zlib, openssl
}:

let
  version = "2.2.17.22";

  src = fetchurl {
    url = "https://kkmserver.ru/Donload/KkmServer.deb";
    sha256 = "6fc44e72a84038364c9d5524fc10e52ea3f9adb15e2f306aa5200348c2395712";
  };
in
stdenv.mkDerivation {
  pname = "kkmserver";
  inherit version src;

  nativeBuildInputs = [ dpkg autoPatchelfHook makeWrapper ];

  buildInputs = [
    stdenv.cc.cc.lib
    zlib
    openssl
  ];

  installPhase = ''
    runHook preInstall

    dpkg-deb -x "$src" "$out"

    mkdir -p "$out/bin"
    ln -sf "$out/opt/kkmserver/kkmserver" "$out/bin/kkmserver"

    # kkmserver deb ships UnitServer.{crt,p12,pem} with mode 0777 (vendor bug —
    # its postinst runs `chmod 777 -R /opt/kkmserver/Settings`). Also drop
    # pre-existing vendor logs (2024-era samples).
    rm -f "$out/opt/kkmserver/Settings/ErrorCrach.log" \
          "$out/opt/kkmserver/Settings/Log.txt" \
          "$out/opt/kkmserver/Settings/Logs.dat" \
          "$out/opt/kkmserver/Settings/Logs.dta" \
          "$out/opt/kkmserver/Settings/ЗаглушкаДляСозданияКаталога.txt"

    # Keep a pristine copy of default Settings for preStart to seed from.
    # The runtime Settings/ dir is bind-mounted over by systemd BindPaths,
    # so we can't read defaults from it inside the service namespace.
    cp -r "$out/opt/kkmserver/Settings" "$out/opt/kkmserver/Settings.defaults"

    # Strip world-writable + setuid/setgid bits so nix-daemon accepts the
    # build output. Then restore owner-write (u+w) so subsequent fixup
    # phases (autoPatchelf) can still patch the files in place.
    find "$out" -type f -exec chmod u-w,go-w,go-s,u-s,g-s {} +
    find "$out" -type f -exec chmod u+w {} +
    find "$out" -type d -exec chmod u-w,go-w,go-s,u-s,g-s {} +
    find "$out" -type d -exec chmod u+w {} +

    runHook postInstall
  '';

  # .NET Core's tracing provider wants liblttng-ust.so.0 (older API) ;
  # nixpkgs only ships .so.1. The runtime gracefully dlopen-fails → no
  # loss of functionality, just no LTTng tracing (which we don't use).
  autoPatchelfIgnoreMissingDeps = [ "liblttng-ust.so.0" ];

  dontStrip = true;

  meta = with lib; {
    description = "KKM Web-server — HTTP сервер для печати чеков на ККТ через JSON/Ajax запросы";
    homepage = "https://kkmserver.ru";
    sourceProvenance = with sourceTypes; [ binaryNativeCode ];
    platforms = [ "x86_64-linux" ];
  };
}
