# VPN fallback tools

Three alternatives for when AmneziaVPN isn't working:
- **Zapret** (system-wide DPI bypass)
- **byedpi** (local SOCKS proxy with DPI bypass)
- **v2ray** (system-wide VLESS Reality TUN tunnel via xray-core)

Managed via a single `vpn-fallback` dispatcher on PATH.

## One-time setup: Zapret params

Zapret is installed but **inert** by default (placeholder params). To activate it:

1. Find working params for your network:
   ```bash
   nix-shell -p zapret nftables --command blockcheck
   ```
2. Copy the working params into `modules/aspects/desktop/common-core/vpn.nix`:
   ```nix
   services.zapret.params = [
     "--dpi-desync=some-option"
     # ... whatever blockcheck suggests
   ];
   ```
3. Rebuild: `nh os switch .#<host>`

After this, Zapret is ready to start/stop at will.

## Daily use

```bash
# Check what's running
vpn-fallback status

# Zapret — system-wide, transparent (no per-app config)
vpn-fallback zapret on
vpn-fallback zapret off
vpn-fallback zapret status
vpn-fallback zapret logs

# byedpi — local SOCKS5 proxy on [IP_ADDRESS]:1080 (via ciadpi)
vpn-fallback byedpi on
vpn-fallback byedpi off
vpn-fallback byedpi status
vpn-fallback byedpi logs

# v2ray — system-wide VLESS Reality TUN tunnel (via xray-core)
# config at /opt/vless/config.json (see VLESS Reality section)
vpn-fallback v2ray on
vpn-fallback v2ray off
vpn-fallback v2ray status
vpn-fallback v2ray logs
```

All three are **mutexed**: `vpn-fallback` refuses to start one tool while
another is running. Stop the active tool before switching.

To override byedpi's default args (`ciadpi -i [IP_ADDRESS] -p 1080 --disorder 1`):
```bash
BYEDPI_ARGS="-i [IP_ADDRESS] -p 1080 --disorder 1 --auto=torst --tlsrec 1+s" vpn-fallback byedpi on
```

## VLESS Reality (via xray-core TUN)

System-wide VLESS Reality tunnel using xray-core in TUN mode. Captures all
traffic and routes it through a VLESS Reality server, with routing rules
bypassing Russian domains (.ru) and Tailscale/local IPs.

### One-time setup

1. **Buy a VLESS Reality key** from a Telegram provider (e.g., `@Grimbird_bot`).

2. **Create the config file** from template:
   ```bash
   cp /var/lib/spectacle/secrets/vless/config.template.json /opt/vless/config.json
   sudo chown root:root /opt/vless/config.json
   sudo chmod 600 /opt/vless/config.json
   ```

3. **Fill in your VLESS Reality fields** — parse your `vless://...` URI:
   | URI field    | JSON field                        |
   |-------------|-----------------------------------|
   | server IP   | `outbounds[0].settings.vnext[0].address` |
   | port        | `outbounds[0].settings.vnext[0].port`    |
   | uuid/id     | `outbounds[0].settings.vnext[0].users[0].id` |
   | sni         | `outbounds[0].streamSettings.realitySettings.serverName` |
   | pbk (publicKey) | `outbounds[0].streamSettings.realitySettings.publicKey` |
   | sid (shortId)   | `outbounds[0].streamSettings.realitySettings.shortId` |
   | flow        | `outbounds[0].settings.vnext[0].users[0].flow` |

   Common flow values: `xtls-rprx-vision`, `` (empty/none).

4. **(Optional) Sops-encrypt the config:**
   ```bash
   sudo sops --encrypt /opt/vless/config.json | sudo tee /opt/vless/config.json
   ```
   The `ExecStartPre` in the systemd service auto-detects sops-encrypted files
   by checking for the `sops` magic header.

5. **Rebuild**: `nh os switch .#<host>`

### Routing whitelist

The template includes built-in bypasses for:
- **Russian sites** (`.ru` domain suffix) → direct
- **Tailscale** (`100.64.0.0/10`) → direct
- **Local IPs** (`127.0.0.0/8`, `192.168.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`) → direct

To add or remove from the whitelist, edit `/opt/vless/config.json`:
```json
"routing": {
  "rules": [
    {"type": "field", "domain": ["geosite:category-ru", "example.com"], "outboundTag": "direct"},
    {"type": "field", "ip": ["1.2.3.4/32"], "outboundTag": "direct"}
  ]
}
```
Then restart: `sudo systemctl restart xray-vless`

## Bypass test

```bash
# Zapret: curl a blocked site directly
curl https://example.com

# byedpi: curl via the SOCKS5 proxy
curl --proxy socks5h://[IP_ADDRESS]:1080 https://ifconfig.me

# v2ray: curl while tunnel is active
# (TUN mode captures all traffic automatically)
curl https://ifconfig.me
```

## Diagnostics

```bash
ip route get [IP_ADDRESS]          # verify routing when zapret is active
systemctl status zapret
journalctl -u zapret -n 50
systemctl status xray-vless
journalctl -u xray-vless -n 50
```

## Cleanup

To fully remove these tools:
- Set `services.zapret.enable = false` in vpn.nix
- Remove `vpnFallback`, `byedpi`, and `xray` from systemPackages
- Remove the `systemd.services.xray-vless` and `systemd.tmpfiles.rules` entries
- Rebuild