{ lib, stdenv, fetchurl, dpkg, autoPatchelfHook, makeWrapper
, openssl, curl, glib, libxml2, nspr, nss, pcsclite, zlib
, gtk3, gdk-pixbuf, pango, cairo, at-spi2-atk
, libx11, libxxf86vm, libsm, linux-pam, libusb-compat-0_1
, ...
}:

let
  version = "5.0.13003"; # CSP + PKI plugin 2.0.15003 (unified installer)

  src = fetchurl {
    url = "https://keysystems.ru/files/web/Scripts/CryptoPro/linux-amd64c_deb.tgz";
    sha256 = "1d7sbwyjlgadmmjy8qqj1xyk5r82nd2lj9rm3nv7c3znzf3g9kx0";
  };

  addonId = "ru.cryptopro.nmcades@cryptopro.ru";

  firefoxExt = fetchurl {
    name = "cryptopro_extension_for_cades_browser_plug_in-1.1.1-an+fx.xpi";
    url = "https://www.cryptopro.ru/sites/default/files/products/cades/extensions/cryptopro_extension_for_cades_browser_plug_in-1.1.1-an+fx-windows.xpi";
    sha256 = "sha256-VZLAtKPuAC42uiJrEKyOsKEUPJ0pLC0Rsta59aA2ED0=";
  };
in
stdenv.mkDerivation {
  pname = "cprocsp";
  inherit version;

  srcs = [ src ];
  sourceRoot = ".";

  nativeBuildInputs = [ dpkg autoPatchelfHook makeWrapper ];

  buildInputs = [
    stdenv.cc.cc.lib
    glib libxml2 curl nspr nss pcsclite openssl.out zlib
    gtk3 gdk-pixbuf pango cairo at-spi2-atk
    libx11 libxxf86vm libsm
    linux-pam libusb-compat-0_1
  ];

  installPhase = ''
    runHook preInstall

    mkdir -p $out
    find . -name '*.deb' -exec dpkg-deb -x {} "$out" \;

    mkdir -p $out/bin
    for bin in "$out"/opt/cprocsp/bin/amd64/* "$out"/opt/cprocsp/sbin/amd64/*; do
      bname=$(basename "$bin")
      [ -x "$bin" ] && [ ! -d "$bin" ] || continue
      # CryptoPro's bundled curl is a Windows/schannel build that shadows
      # system curl — skip it so nixpkgs curl stays authoritative.
      [ "$bname" = "curl" ] && continue
      makeWrapper "$bin" "$out/bin/$bname" \
        --prefix LD_LIBRARY_PATH : "$out/opt/cprocsp/lib/amd64:$out/opt/cprocsp/openssl/lib"
    done

    # Remove Apache SSL module (needs OpenSSL 1.0, not needed for browser signing)
    rm -f "$out/opt/cprocsp/lib/amd64/astra_se_mod_ssl.so"

    ffExtDir="$out/share/mozilla/extensions/{ec8030f7-c20a-464f-9b0e-13a3a9e97384}"
    mkdir -p "$ffExtDir"
    cp ${firefoxExt} "$ffExtDir/${addonId}.xpi"

    # NMH path wrapper expects lib/mozilla, but deb extracts to usr/lib/mozilla
    mkdir -p "$out/lib/mozilla"
    ln -s "$out/usr/lib/mozilla/native-messaging-hosts" "$out/lib/mozilla/native-messaging-hosts"

    runHook postInstall
  '';

  passthru = { inherit addonId; };

  dontStrip = true;
}
