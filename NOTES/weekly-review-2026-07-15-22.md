# Weekly Review: July 15 (Wed) → July 22 (Tue)

## Wed July 15 — The Big Config Day

| What | Status |
|------|--------|
| FalkorDB crash loop fixed — `_graphiti.nix` deployed with persistence fix | ✅ Done |
| 25-turn batching for graphiti sync_turn — cuts OpenRouter API calls 25× | ✅ Committed |
| Custom NixOS fleet-installer ISO built — 1.4GB, SSH + nixos-anywhere baked in | ✅ Done |
| SOUL.md → Gremlin personality | ✅ Done |
| Timezone → Europe/Moscow | ✅ Done |
| OpenRouter fallback chain added (gemma-3-27b-it:free) | ✅ Done |
| Auxiliary models unified to deepseek-v4-flash | ✅ Done |
| Daily ADHD cron job (10am Moscow) | ✅ Done |
| Security.redact_secrets → true | ✅ Done |
| Main model switched to mimo-v2.5 | ✅ Done |
| Exa search set up | ✅ Done |

## Thu July 16 — ISO + Graphiti Digging

| What | Status |
|------|--------|
| PowerEdge ISO booted — logged in as `nixos` user | ✅ Done |
| Graphiti extraction bug diagnosed — root cause: `responses.parse()` API returns lists, Pydantic expects dicts | ✅ Diagnosed |
| Graphiti MCP server logging added | ✅ Done |

## Fri July 17 — PowerEdge Server Setup

| What | Status |
|------|--------|
| homelab01 → poweredge renamed | ✅ Done |
| 8GB swapfile config added to poweredge.nix | ✅ Done |
| Secrets template created (secrets/poweredge/secrets.yaml) | ✅ Done |
| .sops.yaml updated with poweredge creation rule | ✅ Done |
| Tailscale enabled on poweredge (operator=likivik, accept-routes=true) | ✅ Done |
| Nextcloud deployed (placeholder config, admin password in sops) | ✅ Deployed (inactive) |
| Serenity SSH enabled + erebus + traversal keys in authorized_keys | ✅ Config pushed |
| Deploy script rewritten as interactive step-by-step with approve() | ✅ Done |
| hermes@erebus SSH key pair generated + added to poweredge | ✅ Done |
| age-plugin-tpm p256tag/legacy fix documented for SOPS (getsops/sops#2129) | ✅ Documented |
| Fleet multi-host architecture notes (remote-hosts plugin) | ✅ Documented |
| Tailscale SSH ACL gotchas documented | ✅ Saved |
| All 7 facts saved to Graphiti | ✅ Done |

## Mon-Tue July 20-21

| What | Status |
|------|--------|
| OpenCode Go broke — first 401 at Jul 21 22:54 | 🔴 Ongoing |

## Wed July 22 (Today) — OpenCode Crisis + Watchdog Fix

| What | Status |
|------|--------|
| Trojan VPN proxy deployed (V2Ray through Finland) — didn't help, 401 is key-level | ❌ Useless |
| Secrets filter disabled (redact_secrets: false) | ✅ Done |
| Default model switched → openrouter/deepseek-v4-flash | ✅ Done |
| OpenCode Go outage confirmed — GitHub issue #38257, known server-side outage | 🔴 Unfixed |
| OpenCode Zen free API discovered — OPENCODE_ZEN_API_KEY env var added to hermes-agent.nix | ✅ Committed |
| Memory watchdog fixed — podman auto-detection instead of hardcoded Nix store path | ✅ Done |

## 🔴 Still Pending / Unfinished

| What | Blocked by |
|------|------------|
| OpenCode Go subscription still broken (401) | OpenCode upstream, not fixable from here |
| PowerEdge Nextcloud inactive — needs ZFS mirror investigation | `/tank/data` missing, ZFS needs config |
| Serenity rebuild needed — `nh os switch .#serenity` from traversal | User hasn't run it yet |
| Graphiti extraction fix — monkey-patch `_handle_structured_response` | Was discussed, not implemented |
| Hermes restart to pick up new graphiti plugin (25-turn batching) | Not done yet |
| PowerEdge ISO still needs to be flashed from USB | User grabbed it, unclear if deployed |
| ISO auto-login feature requested | Not implemented yet |