# Hermes Agent VPS

## Quick links (from any tailnet device)

- Dashboard: `http://<vps-tailnet-ip>:9119`
- Gateway API: `http://<vps-tailnet-ip>:8642`
- SSH: `ssh likivik@<vps-tailnet-ip>` (until lock-down; after, only from tailnet)

## Deploy steps

1. **Provision VPS** (Hetzner CX22 / DO basic droplet — anything `nixos-25.11`-capable, ~$5/mo)
   Install NixOS using `nixos-infect`-style ISO or the upstream installer.

2. **Clone this repo on the vps**:
   ```sh
   sudo git clone <repo-url> /var/lib/spectacle
   sudo chown -R likivik:likivik /var/lib/spectacle
   sudo chmod -R g+rwX /var/lib/spectacle
   ```

3. **Tailscale auth**: pre-create a reusable auth key in your tailnet admin,
   OR run `sudo tailscale up` interactively.

4. **API keys**:
   ```sh
   sudo install -m 0600 -o hermes /dev/stdin /var/lib/hermes/.hermes/.env
   # paste: OPENROUTER_API_KEY=sk-or-...
   ```

5. **Tune `hermes-config.yaml`** at `/var/lib/spectacle/modules/hosts/vps/hermes-config.yaml`.

6. **First rebuild**:
   ```sh
   cd /var/lib/spectacle && nh os switch .#vps
   ```

7. **Lock down SSH** after `tailscale status` shows the vps:
   - Edit `/var/lib/spectacle/modules/hosts/vps/vps.nix`
   - Set `lockSshToTailscale = true;`
   - Commit + push. Rebuild from a tailnet device.

## Git workflow

```
┌──────────────────────┐          git push/pull          ┌────────────────────────┐
│  Your local repo     │  ────────────────────────────▶  │  vps clone at          │
│  /Storage/Git/       │  ◀────────────────────────────  │  /var/lib/spectacle/   │
│  spectacle/          │          user pulls back        │                        │
│                      │                                 │  auto-commits daily    │
│  hermes-config.yaml  │                                 │  hermes-config.yaml    │
│  (you edit here)     │                                 │  (agent edits here)    │
└──────────────────────┘                                 └────────────────────────┘
```

- Agent edits take effect immediately (systemd path unit restarts hermes-agent).
- Daily timer auto-commits agent edits to vps's local clone.
- **No automatic push** — review agent commits before pushing back to origin.

## Security model

| Service | Port | Access |
|---------|------|--------|
| SSH | 22 | Public until lock-down, then tailscale0 only |
| Hermes dashboard | 9119 | tailscale0 only (from day 1) |
| Hermes gateway API | 8642 | tailscale0 only (from day 1) |
| Tailscale wire | 41641/udp | tailscale0 only |

## Locking down SSH

```sh
tailscale status  # confirm vps is on the tailnet
# edit /var/lib/spectacle/modules/hosts/vps/vps.nix
# set lockSshToTailscale = true;
git add -A && git commit -m "vps: lock SSH to tailscale"
cd /var/lib/spectacle && nh os switch .#vps
```

After lockdown, only tailnet devices can SSH. To reverse: flip the flag back and rebuild.

## Updating the config

**User edits the YAML locally** → `git push` → vps pulls → systemd path
unit detects change → restarts `hermes-agent`. Effect is live in seconds.

**Agent edits the YAML at runtime** → file changes → same path unit
restarts the service → daily auto-commit.

## Future add-ons

- `den.aspects.server.kokoro` — Kokoro TTS server. Hermes can already
  call out to a TTS endpoint via its `tts-premium` extra deps and
  `edge-tts` provider. This would be the actual TTS server aspect.
- `den.aspects.server.sillytavern` — SillyTavern LLM frontend (port
  :8000). Still uncertain.

Both would follow the same pattern: new aspect files in
`modules/aspects/server/`, added to the vps host's `includes`.
