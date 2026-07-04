{ stdenv, lib, fetchurl, dpkg, autoPatchelfHook, bubblewrap, coreutils
, util-linux
}:

let
  version = "26.3200-227";

  src = fetchurl {
    url = "https://update.saby.ru/NmhTransport/master/linux/nmh-transport.deb";
    sha256 = "sha256-DTEoXYljixpHD4fKfJoDrA0mtCkEp81fCJFdIT32wHw=";
  };

  nmhName = "ru.tensor.sbis_plugin_nmh";
  addonId = "pbcgcpeifkdjijdjambaakmhhpkfgoec";
in
stdenv.mkDerivation {
  pname = "saby-nmh";
  inherit version src;

  nativeBuildInputs = [ dpkg autoPatchelfHook ];

  buildInputs = [
    stdenv.cc.cc.lib
    util-linux
  ];

  installPhase = ''
    runHook preInstall

    mkdir -p $out/opt/nmh-transport

    dpkg-deb -x "$src" nix-pkg

    cp -r nix-pkg/opt/nmh-transport/temp_nmh/. "$out/opt/nmh-transport/"

    VER=$(ls "$out/opt/nmh-transport/" | grep -E '^[0-9]' | head -1)
    CONFIG="$out/opt/nmh-transport/$VER/service/nmh-transport-config.ini"

    # Disable auto-updater
    substituteInPlace "$CONFIG" \
      --replace-fail "АвтоматическоеОбновление=Да" "АвтоматическоеОбновление=Нет" \
      --replace-fail "ПериодПроверкиОбновления=7200" "ПериодПроверкиОбновления=0"

    mkdir -p $out/bin

    cat > $out/bin/saby-nmh << 'WRAPPER'
#!/usr/bin/env bash
VER=$(ls /opt/nmh-transport/ | grep -E '^[0-9]' | head -1)
exec ${bubblewrap}/bin/bwrap \
  --unshare-user-try \
  --unshare-pid \
  --die-with-parent \
  --new-session \
  --ro-bind /nix/store /nix/store \
  --ro-bind /opt/nmh-transport /opt/nmh-transport \
  --ro-bind /opt/cprocsp /opt/cprocsp \
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
  --setenv LD_LIBRARY_PATH /opt/cprocsp/lib/amd64:/opt/cprocsp/openssl/lib \
  --setenv XDG_STATE_HOME /tmp \
  -- \
  /opt/nmh-transport/"$VER"/service/nmh-transport "$@"
WRAPPER
    chmod +x $out/bin/saby-nmh

    runHook postInstall
  '';

  passthru = { inherit nmhName addonId; };

  dontStrip = true;

  meta = with lib; {
    description = "Saby (Tensor) native messaging host transport for browser EDS signing";
    homepage = "https://saby.ru";
    sourceProvenance = with sourceTypes; [ binaryNativeCode ];
    platforms = [ "x86_64-linux" ];
  };
}
