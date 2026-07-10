# Hermes Agent VPS

## Quick links (from any tailnet device)

- Dashboard: `http://<vps-tailnet-ip>:9119`
- Gateway API: `http://<vps-tailnet-ip>:8642`
- SSH: `ssh likivik@<vps-tailnet-ip>` (until lock-down; after, only from tailnet)

## Setup

1. **Deploy NixOS**: follow `NOTES/vps-deploy.md` (uses nixos-anywhere)
2. **Secrets**: follow `NOTES/secrets.md` (uses sops-nix with TPM + recovery key)
3. **Tune `hermes-config.yaml`**: edit `modules/hosts/vps/hermes-config.yaml`

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
| SSH | 22 | Public until lockdown, then tailscale0 only |
| Hermes dashboard | 9119 | tailscale0 only (from day 1) |
| Hermes gateway API | 8642 | tailscale0 only (from day 1) |
| Tailscale wire | 41641/udp | tailscale0 only |

## Locking down SSH

After Tailscale is confirmed working, flip the flag and rebuild:
```sh
# edit modules/hosts/vps/vps.nix — set lockSshToTailscale = true;
git add -A && git commit -m "vps: lock SSH to tailscale"
cd /var/lib/spectacle && nh os switch .#vps
```

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
