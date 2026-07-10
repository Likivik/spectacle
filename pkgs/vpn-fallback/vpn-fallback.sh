#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/vpn-fallback"
mkdir -p "$DATA_DIR"

is_running() {
  local name="$1"
  case "$name" in
    zapret) systemctl is-active zapret >/dev/null 2>&1 ;;
    byedpi) pgrep -x ciadpi >/dev/null 2>&1 ;;
    v2ray) systemctl is-active xray-vless >/dev/null 2>&1 ;;
  esac
}

require_not_running() {
  for tool in zapret byedpi v2ray; do
    if [ "$tool" != "$1" ] && is_running "$tool"; then
      echo "error: $tool is already running. Stop it first: vpn-fallback $tool off" >&2
      exit 1
    fi
  done
}

case "${1:-help}" in
  zapret)
    case "${2:-status}" in
      on)
        require_not_running zapret
        sudo systemctl start zapret
        echo "zapret started"
        ;;
      off)
        sudo systemctl stop zapret
        echo "zapret stopped"
        ;;
      status)
        if is_running zapret; then
          echo "zapret: running"
        else
          echo "zapret: stopped"
        fi
        ;;
      logs)
        sudo journalctl -u zapret -f
        ;;
      *)
        echo "Usage: vpn-fallback zapret {on|off|status|logs}" >&2
        exit 1
        ;;
    esac
    ;;
  byedpi)
    case "${2:-status}" in
      on)
        require_not_running byedpi
        # Default args: bind to localhost:1080, disorder=1 for DPI bypass
        # Override via BYEDPI_ARGS env var if needed
        read -r -a ARGS <<< "${BYEDPI_ARGS:--i [IP_ADDRESS] -p 1080 --disorder 1}"
        nohup ciadpi "${ARGS[@]}" > "$DATA_DIR/byedpi.log" 2>&1 &
        echo $! > "$DATA_DIR/byedpi.pid"
        echo "byedpi (ciadpi) started, PID $!"
        echo "point apps at socks5h://[IP_ADDRESS]:1080"
        ;;
      off)
        if [ -f "$DATA_DIR/byedpi.pid" ]; then
          kill "$(cat "$DATA_DIR/byedpi.pid")" 2>/dev/null || true
          rm -f "$DATA_DIR/byedpi.pid"
        fi
        pkill -x ciadpi 2>/dev/null || true
        echo "byedpi stopped"
        ;;
      status)
        if [ -f "$DATA_DIR/byedpi.pid" ] && kill -0 "$(cat "$DATA_DIR/byedpi.pid")" 2>/dev/null; then
          echo "byedpi (ciadpi): running (PID $(cat "$DATA_DIR/byedpi.pid"))"
        elif is_running byedpi; then
          echo "byedpi (ciadpi): running (PID $(pgrep -x ciadpi))"
        else
          echo "byedpi (ciadpi): stopped"
        fi
        ;;
      logs)
        tail -f "$DATA_DIR/byedpi.log"
        ;;
      *)
        echo "Usage: vpn-fallback byedpi {on|off|status|logs}" >&2
        exit 1
        ;;
    esac
    ;;
  v2ray)
    case "${2:-status}" in
      on)
        require_not_running v2ray
        sudo systemctl start xray-vless
        echo "v2ray (xray-core TUN) started"
        ;;
      off)
        sudo systemctl stop xray-vless
        echo "v2ray stopped"
        ;;
      status)
        if is_running v2ray; then
          echo "v2ray (xray-core TUN): running"
        else
          echo "v2ray (xray-core TUN): stopped"
        fi
        ;;
      logs)
        sudo journalctl -u xray-vless -f
        ;;
      *)
        echo "Usage: vpn-fallback v2ray {on|off|status|logs}" >&2
        exit 1
        ;;
    esac
    ;;
  status)
    echo "=== connection tool status ==="
    echo -n "zapret: "; is_running zapret && echo "running" || echo "stopped"
    echo -n "byedpi (ciadpi): "; is_running byedpi && echo "running" || echo "stopped"
    echo -n "v2ray (xray-core TUN): "; is_running v2ray && echo "running" || echo "stopped"
    ;;
  help|--help|-h)
    echo "vpn-fallback — manual switch for alternative VPN/circumvention tools"
    echo ""
    echo "Usage:"
    echo "  vpn-fallback status                    Show all tool states"
    echo "  vpn-fallback zapret   {on|off|status|logs}"
    echo "  vpn-fallback byedpi   {on|off|status|logs}"
    echo "  vpn-fallback v2ray    {on|off|status|logs}"
    echo ""
    echo "Zapret:  system-wide DPI bypass (transparent, no per-app config)"
    echo "         run 'blockcheck' once to find working params,"
    echo "         then add them to vpn.nix and rebuild."
    echo ""
    echo "byedpi:  local SOCKS5 proxy on [IP_ADDRESS]:1080 (via ciadpi)"
    echo "         point apps at socks5h://[IP_ADDRESS]:1080"
    echo "         override args via BYEDPI_ARGS env var"
    echo ""
    echo "v2ray:   system-wide VLESS Reality TUN tunnel (via xray-core)"
    echo "         config at /opt/vless/config.json"
    echo "         optional sops encryption supported"
    echo ""
    echo "Data: $DATA_DIR"
    ;;
  *)
    echo "Usage: vpn-fallback {zapret|byedpi|v2ray|status|help}" >&2
    exit 1
    ;;
esac