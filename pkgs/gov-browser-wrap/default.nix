{ lib, stdenv, makeWrapper, bubblewrap, chromium-gost }:

stdenv.mkDerivation {
  pname = "gov-browser-wrap";
  version = chromium-gost.version;

  dontUnpack = true;

  nativeBuildInputs = [ makeWrapper ];

  installPhase = ''
    mkdir -p $out/bin $out/share/applications $out/share/icons/hicolor

    cat > $out/bin/gov-browser << WRAPPER
#!/usr/bin/env bash
set -euo pipefail

BWRAP="${bubblewrap}/bin/bwrap"
CHROME="${chromium-gost}/bin/chromium-gost"

if [ "\''${HOME:-}" = "/homeless-shelter" ] || [ ! -d "\''${HOME:-}" ]; then
  DATA_DIR="/tmp/gov-browser-\''${USER:-unknown}"
else
  DATA_DIR="\''${XDG_DATA_HOME:-\$HOME/.local/share}/gov-browser"
fi

PROFILE_DIR="\$DATA_DIR/profile"

mkdir -p "\$PROFILE_DIR"

ARGS=(
  --unshare-all
  --die-with-parent
  --new-session
  --ro-bind /nix/store /nix/store
  --ro-bind /opt /opt
  --ro-bind /etc/machine-id /etc/machine-id
  --ro-bind /etc/chromium /etc/chromium
  --ro-bind /sys/dev/char /sys/dev/char
  --bind /dev/shm /dev/shm
  --dev-bind /dev/dri /dev/dri
  --dev-bind /dev/bus/usb /dev/bus/usb
  --bind /run/pcscd /run/pcscd
  --proc /proc
  --tmpfs /home
  --setenv HOME "\$DATA_DIR/home"
  --setenv USER "\$USER"
  --setenv LD_LIBRARY_PATH "/opt/cprocsp/lib/amd64:/opt/cprocsp/openssl/lib"
)

WS="\''${XDG_RUNTIME_DIR:-\''${HOME:-/tmp}/run}/\''${WAYLAND_DISPLAY:-wayland-0}"
[ -S "\$WS" ] && ARGS+=(--bind "\$WS" "\$WS")
[ -S "\''${XDG_RUNTIME_DIR}/bus" ] && ARGS+=(--bind "\''${XDG_RUNTIME_DIR}/bus" "\''${XDG_RUNTIME_DIR}/bus")
[ -S "\''${XDG_RUNTIME_DIR}/pipewire-0" ] && ARGS+=(--bind "\''${XDG_RUNTIME_DIR}/pipewire-0" "\''${XDG_RUNTIME_DIR}/pipewire-0")

exec "\$BWRAP" "\''${ARGS[@]}" "\$CHROME" \
  --user-data-dir="\$PROFILE_DIR" \
  --disable-telemetry \
  --no-first-run \
  --password-store=basic \
  "\$@"
WRAPPER
    chmod +x $out/bin/gov-browser

    # Desktop entry
    cat > $out/share/applications/gov-browser.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Gov Browser
Comment=Sandboxed browser for government web services
Exec=$out/bin/gov-browser %U
Icon=gov-browser
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;
EOF

    # Icon — reuse chromium-gost's
    for size in 16 24 32 48 64 128 256; do
      src=${chromium-gost}/share/icons/hicolor/''${size}x''${size}/apps/chromium-gost.png
      if [ -f "\$src" ]; then
        mkdir -p "$out/share/icons/hicolor/''${size}x''${size}/apps"
        ln -sf "\$src" "$out/share/icons/hicolor/''${size}x''${size}/apps/gov-browser.png"
      fi
    done
  '';

  dontFixup = true;

  meta = with lib; {
    description = "Bubblewrap-sandboxed gov browser for secure digital signatures";
    platforms = [ "x86_64-linux" ];
    maintainers = [ ];
  };
}
