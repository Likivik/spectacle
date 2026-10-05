# Phase 1 — Central Monitoring on poweredge + monitor Graphiti

> **For Hermes:** use subagent-driven-development to implement task-by-task. Each task ≤ ~15 min.

**Goal:** Stand up a minimal Prometheus + Alertmanager(→Telegram) on **poweredge** (central, always-on, 105G free) and use it to monitor the **Graphiti stack on erebus** — the exact service that went silent on Sep 28. No Grafana, no Loki, no Beszel yet.

**Architecture:** poweredge runs the central Prometheus + Alertmanager + a blackbox exporter. erebus runs the exporters (node/systemd/blackbox) and the Graphiti services. poweredge scrapes erebus over the tailnet. One alert rule per Graphiti component → Telegram on probe/unit failure.

**Tech stack:** Prometheus 3.5 LTS, Alertmanager, node/systemd/blackbox exporters, sops secrets, Tailscale.

---

## Verified context (don't re-research)

**Graphiti stack lives on erebus** (from `modules/aspects/server/hermes/_graphiti.nix`):
| Component | Where | How to watch |
|---|---|---|
| `graphiti-mcp` | erebus **user** service, HTTP `127.0.0.1:8000`, `/health` → `{"status":"healthy"}` | blackbox HTTP probe + systemd unit state |
| `podman-falkordb` | erebus system service, `127.0.0.1:6379` | systemd unit state (podman container) |
| litellm (`:4000`) + embedder (`:8081`) | erebus deps of graphiti | optional Phase 1b |

**Hosts:** erebus 7.8G/~4.4G free, disk 20G free. poweredge 7.7G/~4.7G free, disk **105G free**. Both 4 cores, both on tailnet `oryx-galaxy.ts.net`.

**Existing conventions (mirror these, don't invent):**
- Aspects: `den.aspects.<host>.includes = [ ... ]`; hosts at `modules/hosts/<host>/<host>.nix`.
- Secrets: `sops.secrets."<name>" = { sopsFile = ../../../secrets/<host>/secrets.yaml; owner; group; mode; }`. poweredge secrets file: `secrets/poweredge/secrets.yaml`.
- erebus tailscale exposure: `networking.firewall.interfaces.tailscale0.allowedTCPPorts` (currently `[22 9119 8642 3443 8001 8003 8880 8090]`, `erebus.nix:104`).
- poweredge tailscale exposure: `allowedTCPPorts = lib.mkForce [22 6333 6334 8000]` (`poweredge.nix:238`). **Firewall uses mkForce — any port add must edit this exact list or it's wiped.**
- poweredge has a `systemd.services.tailscale-serve` oneshot that sets up `tailscale serve --bg --https=<port>` (`poweredge.nix:172`).
- Deploy: poweredge is remote → `nixos-rebuild switch --flake .#poweredge --build-host likivik@poweredge --target-host likivik@poweredge --elevate=sudo`. erebus is local → the detached `systemd-run` path in AGENTS.md.
- Ports: avoid collisions (graphiti 8000, falkordb 6379, nextcloud 80/443, immich 3001, qdrant 6333/6334).

---

## Design decisions (locked)

1. **blackbox exporter runs on erebus**, not poweredge — because graphiti binds `127.0.0.1:8000` on erebus and is not reachable off-host. Prometheus (poweredge) scrapes erebus's blackbox exporter over the tailnet; the probe then hits graphiti's local `/health`.
2. **New port allocations:** erebus blackbox `9115`, erebus node_exporter `9100`, erebus systemd_exporter `9558`. Poweredge Prometheus `9090`, Alertmanager `9093`, blackbox `9115`.
3. **Alerting = probe + systemd unit state**, both → the same Telegram receiver.
4. **`checkConfig = "syntax-only"`** wherever a secret file is referenced (else the Nix sandbox fails the dry-build falsely).

---

## Tasks

### Task 1 — Monitoring aspect skeleton on poweredge
**Files:** create `modules/aspects/server/monitoring/default.nix`.
- Define `den.aspects.server.monitoring` with a `nixos` block; parameterise later. For now enable Prometheus + Alertmanager bound to `127.0.0.1`.
- `services.prometheus.enable = true; listenAddress = "127.0.0.1"; port = 9090; retentionTime = "15d"; checkConfig = "syntax-only";`
- **Verify:** `nix build .#nixosConfigurations.poweredge.config.system.build.toplevel --dry-run` evaluates with the aspect imported but not yet enabled.

### Task 2 — Telegram secret (sops)
**Files:** `secrets/poweredge/secrets.yaml` (add key `monitoring/telegram-bot-token`), `modules/hosts/poweredge/poweredge.nix` (declare `sops.secrets."monitoring/telegram-bot-token"`).
- `sops -e` workflow per `nixos-secrets-ops` skill. owner `alertmanager`, mode `0400`.
- **Open:** need bot token + chat_id from user (see below).

### Task 3 — Prometheus + Alertmanager on poweredge
**Files:** `modules/aspects/server/monitoring/default.nix`.
- Alertmanager: `configuration.route` → `telegram` receiver, `group_by=["instance"]`, `group_wait="30s"`, `repeat_interval="8h"`; `telegram_configs = [{ send_resolved = true; bot_token_file = config.sops.secrets."monitoring/telegram-bot-token".path; chat_id = <TODO>; parse_mode = "Markdown"; }]`.
- Add `services.prometheus.alertmanagers = [{ scheme="http"; static_configs=[{targets=["127.0.0.1:9093"];}]; }]`.
- **Verify:** dry-build; after switch, `curl 127.0.0.1:9093/-/healthy`.

### Task 4 — erebus exporters + tailnet exposure
**Files:** create `modules/aspects/server/monitoring-exporters/` (or add to erebus.nix); edit `modules/hosts/erebus/erebus.nix` firewall.
- Enable on erebus: `exporters.node` (`port=9100`, collectors `systemd`,`processes`), `exporters.systemd` (`port=9558`, unit include `(graphiti|falkordb|litellm|podman).+`), `exporters.blackbox` (`port=9115`).
- Add `9100 9558 9115` to erebus `interfaces.tailscale0.allowedTCPPorts` list.
- **Verify:** dry-build; after switch `curl 127.0.0.1:9100/metrics | head`.

### Task 5 — Scrape + Graphiti alert rules
**Files:** `modules/aspects/server/monitoring/default.nix`, `modules/aspects/server/monitoring/rules/graphiti.yml`.
- poweredge Prometheus scrape jobs:
  - node_exporter @ `erebus.oryx-galaxy.ts.net:9100`
  - systemd_exporter @ `erebus.oryx-galaxy.ts.net:9558`
  - blackbox @ `erebus.oryx-galaxy.ts.net:9115` (multi-target via relabel; targets = graphiti `/health`)
- Rules:
  ```promql
  - alert: GraphitiMcpDown
    expr: probe_success{job="blackbox-graphiti"} == 0
    for: 2m
  - alert: GraphitiUnitFailed
    expr: node_systemd_unit_state{name=~"graphiti-mcp.service|podman-falkordb.service", state="failed"} == 1
    for: 1m
  ```
- **Verify:** `promtool check rules rules/graphiti.yml`.

### Task 6 — Wire aspects into hosts + deploy
**Files:** `modules/hosts/poweredge/poweredge.nix` (+`server.monitoring`), `modules/hosts/erebus/erebus.nix` (+ exporters aspect).
- `jj new`; dry-build both hosts; push; deploy erebus (local, systemd-run) then poweredge (remote).
- **Acceptance test (THE point of Phase 1):** `systemctl --user stop graphiti-mcp` on erebus → Telegram `GraphitiUnitFailed` fires within ~1-2 min → restart → resolved fires. Also `podman stop falkordb` variant.

---

## Files likely to change

| Path | Change |
|---|---|
| `modules/aspects/server/monitoring/default.nix` | **create** |
| `modules/aspects/server/monitoring/rules/graphiti.yml` | **create** |
| `modules/aspects/server/monitoring-exporters/default.nix` | **create** (erebus side) |
| `modules/hosts/poweredge/poweredge.nix` | add aspect + sops secret + tailscale-serve for UI |
| `modules/hosts/erebus/erebus.nix` | add exporters aspect + firewall ports |
| `secrets/poweredge/secrets.yaml` | add `monitoring/telegram-bot-token` |

## Validation
- Both hosts dry-build clean (time-box: state estimate before starting; nix evals 5-15 min).
- `promtool check config` / `check rules` pass.
- Acceptance test (Task 6) fires + resolves a Telegram alert for graphiti.
- `up{job=~"node_erebus|systemd_erebus|blackbox-graphiti"} == 1` in Prometheus.

## Risks / open questions
- **Firewall mkForce footgun** (`poweredge.nix:238`, `erebus.nix:104`): must edit the exact list or the port vanishes / lockout. The `erebus.nix:228` comment records a real lockout incident — respect it.
- **Telegram token + chat_id needed** before Task 2/3. Which chat? Dedicated channel recommended.
- **Prometheus UI reachability:** Phase 1 doesn't need a UI (alerts go to Telegram), but for debugging you'd add a `tailscale serve --https=<free-port>` for :9090. Defer unless wanted.
- **Beszel decision:** leave beszel running for now (it's your only dashboard); retire it only after Phase 2 Grafana. Or remove now if you don't value it — but that's a separate change.
- **Scope creep guard:** Phase 1 = graphiti only. Don't add other services' rules until the pattern is proven (that's the "start small" the user asked for).

## Open questions before implementing
1. **Telegram destination** — which chat/channel, and do we have a bot token?
2. **Prometheus UI** wanted in Phase 1 (tailscale serve) or Telegram-only?
3. **Keep or drop Beszel** now?

---

## Time estimate
- Task 1-5 (config authoring + dry-builds): ~1.5-2h.
- Task 6 (dual deploy, evals 5-15 min each + switch): ~30-45 min.
- **Total: ~2.5-3h**, contingent on the Telegram secret being available. State estimate before each `nix build` per AGENTS.md.