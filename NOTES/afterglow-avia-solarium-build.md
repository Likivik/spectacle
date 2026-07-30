# afterglow-avia — Solarium admin monoblock migration

> Goal: replace Windows on a basic work monoblock (solarium admin) with NixOS.
> Components: ATOL 30F KKM (USB-to-COM), kkmserver HTTP-KKM bridge (talks to
> yclients in browser), PAX S300 payment terminal (T-Bank, INPAS protocol;
> already flashed by bank).

## Status (2026-07-25)

✅ **Builds successfully.** `nix build .#nixosConfigurations.afterglow-avia.config.system.build.toplevel` exits 0.

### Created files

| File | Purpose |
|---|---|
| `pkgs/atol-fptr10/default.nix` | autoPatchelf wrapper for 7 ATOL ДТО 10.10.9.0 debs (~35 MB vendored) |
| `pkgs/atol-fptr10/debs/*.deb` | 7 vendored debs: epc-mdl, epc-upd, libfptr10, libfptr10-gui, epc-bridge, fptr10-rpc-server, fptr10-test-util |
| `pkgs/kkmserver/default.nix` | autoPatchelf wrapper for KkmServer.deb (fetched via fetchurl from kkmserver.ru) |
| `modules/hosts/afterglow-avia/afterglow-avia.nix` | Host config: gnome + firefox + common-core + sops; 3 systemd services; udev rules; users; locale |
| `modules/hosts/afterglow-avia/_hardware-configuration.nix` | Skeleton — replace UUIDs/filesystems at provisioning time |
| `modules/hosts/host-user-definitions.nix` | Registered `afterglow-avia` host with users `likivik` (admin) + `solarium` (restricted) |

### Decisions

- One-off host config (no aspect extraction for now) — refactor to `den.aspects.pos-kkmserver` only if a 2nd kiosk appears
- ATOL debs vendored in-tree (~35 MB git bloat, one-time cost, SHA-pinned via `dpkg-deb -x` against `./debs`)
- kkmserver fetched from `https://kkmserver.ru/Donload/KkmServer.deb` (stable link, SHA-pinned)
- Clean install (no dual-boot — "some retard already nuked windows")
- `likivik` = admin (NOPASSWD sudo); `solarium` = restricted staff user (no sudo)
- `secrets/afterglow-avia/secrets.yaml` (sops, not created yet)

### Known issues / next steps

1. **`_hardware-configuration.nix` is a skeleton** — must be regenerated on the box via `nixos-generate-config --root /mnt`.
2. **SOPS secrets are commented out** — uncomment + create `secrets/afterglow-avia/secrets.yaml` at provisioning time for:
   - `afterglow-avia/likivik-password` (user)
   - `afterglow-avia/solarium-password` (user)
   - `afterglow-avia/UnitServer.p12` (kkmserver HTTPS cert; original is lost, kkmserver will regenerate)
3. **kkmserver license** — `SettingsServ.ini::KeyMainHashedString` binds to host UUID/MAC. Reserve `networking.hostId` (currently placeholder `1a2b3c4d`) and PIN a MAC via udev rule before first boot. License transfer requires contacting kkmserver support.
4. **kkmserver lttng-ust**: `.NET tracing provider wants liblttng-ust.so.0 while nixpkgs has .so.1 — ignored via `autoPatchelfIgnoreMissingDeps`. No loss of functionality, just no LTTng tracing.
5. **kkmserver Settings perms**: vendor ships `UnitServer.{crt,p12,pem}` with mode 0777 (auto-deny would reject). `pkgs/kkmserver/default.nix` strips world-writable/setuid bits in installPhase; runtime state is symlinked to `/var/lib/kkmserver/Settings` via systemd `StateDirectory` + pre-start script.
6. **Yclients integration** — confirm at the customer site that yclients branch settings point to `http://localhost:5893` (kkmserver default port).
7. **Firefox CORS / browser add-in** — `kkmserver.addin.io` native-messaging manifest is wired via `environment.etc`. The browser add-in itself (`AddIn_Firefox.xpi`) is not bundled yet — add as `programs.firefox.policies` if yclients can't reach kkmserver directly via HTTP.

## Decided non-goals

- Actual physical wiring of the PAX terminal — already done by bank (flashed to INPAS-Integration mode).
- Bank-side integration acceptance testing — handled by the bank onsite.

## Build commands (per AGENTS.md)

```bash
# After changes to this host — dry-build (catches eval + build errors)
nix build .#nixosConfigurations.afterglow-avia.config.system.build.toplevel --dry-run

# All hosts (when shared modules touched)
nix flake check --no-build --keep-going
```

## Gotchas encountered during implementation

- **`nixos = { ... }:` discards module args** (AGENTS.md gotcha). Captured `pkgs` explicitly: `nixos = { config, lib, pkgs, ... }: let atolPkg = pkgs.callPackage ../../../pkgs/atol-fptr10 { }; in { ... }`.
- **Qt5 buildInput triggers `wrapQtAppsHook`** expecting either wrap or `dontWrapQtApps`. Set `dontWrapQtApps = true` in `pkgs/atol-fptr10/default.nix` (Qt5 runtime is patched via autoPatchelf; no runtime Qt wrapper needed).
- **kkmserver world-writable exec files** → nix-daemon rejects `UnitServer.{crt,p12,pem}` at 0777. Fix: chmod normalization in installPhase.
- **`i18n.supportedLocales` needs `/UTF-8` source-charset suffix** — `en_US.UTF-8/UTF-8`, not just `en_US.UTF-8`.

## Wi-Fi flapping incident (2026-07-30)

### Symptom
Wi-Fi (Atheros AR9565, `ath9k` driver, 2.4 GHz only chipset) kept cycling through connect/disconnect. SSH via Tailscale unreachable from the tailnet. On-site human fixed by toggling Wi-Fi off/on.

### Root cause
```
wlp3s0: deauthenticated from 10:7b:ef:5c:04:68 (Reason: 15=4WAY_HANDSHAKE_TIMEOUT)
```

NM associated at radio level but the WPA2 4-way handshake repeatedly timed out. Each cycle:

1. NM starts activation → radio associates
2. Handshake fails → NM logs `link timed out.` + `Activation: failed for connection 'Keenetic-7430'`
3. NM retries immediately → repeat every ~50–60s

This loop ran from ~12:15 to ~13:22 MSK (when human toggled Wi-Fi). The toggle forced a full driver re-init + fresh auth which succeeded cleanly.

### Network environment
- **AP:** Keenetic-7430 (WPA2-PSK, channel 2, 2.4 GHz)
- **Client IP:** 192.168.1.60/24
- **Signal:** 85% (good)
- **Competing APs on 2.4 GHz:** RT-GPON-E549 (ch1), RT-GPON-8785 (ch1) — possible interference driver

### Suspected triggers
| Likelihood | Cause | Rationale |
|:----------:|-------|-----------|
| ⭐⭐⭐ | **AP-side transient** — Keenetic CPU load, channel scan, or beacon glitch | The same chip worked fine all prior day; toggle fixed it permanently. Recurrence pattern will tell. |
| ⭐⭐ | **ath9k HW crypto offload** — known quirk of AR9565 where hardware encryption engine hangs under certain conditions | `4WAY_HANDSHAKE_TIMEOUT` is a classic symptom. Mitigation: `ath9k.noht40=1` or `ath9k.use_sw_crypto=1`. |
| ⭐ | **Router-assist (WMM/802.11e mismatch)** — some Keenetic firmware handles QoS negotiation poorly with old ath9k clients | Log didn't show WMM negotiation failures explicitly. |
| ⭐ | **DFS / radar avoidance** | AR9565 is 2.4-only, irrelevant. |

### Connection config
- `802-11-wireless.powersave: 0 (default)` — powersave already off, not the cause
- `ip_forward = 1` (set by Tailscale — expected)
- `802-11-wireless-security.proto: --` and `pairwise: --` — NM negotiates these at runtime, not pinned. Could pin to `wpa2` + `ccmp` for deterministic behaviour.

### Potential fixes (if it recurs)
1. **Quick (on-box):** `echo "options ath9k use_sw_crypto=1" | sudo tee /etc/modprobe.d/ath9k.conf` → rebuild
2. **Clean (Nix config):** add `boot.kernelParams = [ "ath9k.use_sw_crypto=1" ];` or wrap in `hardware.wifi.ath9k.softwareEncryption`
3. **Band/Channel pin:** lock NM connection to channel 2 or pin BSSID to `10:7B:EF:5C:04:68` to prevent AP roaming to a worse channel
4. **Tailscale note:** when Wi-Fi drops, tailscale goes dark too — `tailscale ping` times out even though status shows `active; relay`