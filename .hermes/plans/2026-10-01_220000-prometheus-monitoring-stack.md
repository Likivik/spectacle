# Prometheus Monitoring Stack — Implementation Plan (erebus → poweredge)

> **For Hermes:** use subagent-driven-development to implement this plan task-by-task.

**Goal:** Stand up a Prometheus+Grafana monitoring + Alertmanager→Telegram alerting stack, phased, on erebus first then poweredge. Directly catches the *silent service park* failure class that caused the Sep 28 outage.

**Architecture:** Central Prometheus + Alertmanager + Grafana + Loki/promtail on erebus (bind 127.0.0.1, exposed via Tailscale). node_exporter + systemd_exporter + blackbox_exporter + promtail on each host. One probe rule per critical service → Telegram. Phased: Phase 1 = minimal alerting (probe → Telegram, no Grafana); Phase 2 = full observability.

**Tech Stack:** Prometheus 3.5.x (LTS), Alertmanager, Grafana 12.x, node/systemd/blackbox exporters, Loki+promtail, Tailscale serve, sops-managed secrets.

---

## Current context (verified)

- **erebus already runs Beszel** (`modules/aspects/server/beszel/default.nix`): hub :8090 + agent :45876, enabled in `modules/hosts/erebus/erebus.nix:15`. This is the current *only* monitoring — lightweight per-host dashboard, **no alerting, no cross-host aggregation, no blackbox probing**.
- **Aspects** are enabled via `den.aspects.<host>.includes` (see `erebus.nix:6-22`). Create a new `modules/aspects/server/monitoring/` aspect and add it to the host includes list.
- **No `modules/aspects/server/monitoring/` exists yet** (confirmed 0 files).
- **Secrets pattern:** repo uses sops for secrets (see `nixos-secrets-ops` skill / `_graphiti.nix` pattern). Alertmanager Telegram token must come from a secret file, **not** inline.
- **Hosts on tailnet** (`oryx-galaxy.ts.net`): erebus, poweredge (active), serenity, afterglow. poweredge is reachable today.
- **Resources:** erebus 7.8GB RAM (~3GB free), root 63% used/26GB free. Poweredge unknown — measure before Phase 2 ships there.

## Why this stack (from research note `research/prometheus-nixos-ultra-recent-2026.md`)

- The outage was a service that went **degraded→parked silently**. node_exporter won't catch that; a **blackbox `probe_success` rule** (or systemd unit-state rule) does.
- Prometheus 3.5 LTS is the skill portability choice (CNCF-neutral, Apache-2.0, employers' default). VM is lighter but not what jobs ask for.
- Beszel stays for quick per-host glance; Prometheus becomes the alerting/aggregation/learning layer.

---

# Phase 1 — Minimal alerting (the incident fix). Do this first, ship it.

**Goal:** Alertmanager → Telegram with a `probe_success` rule on hermes-gateway (the exact failure class from Sep 28). No Grafana, no Loki yet. ~1 day.

#### Task 1: Create monitoring aspect skeleton
- Create `modules/aspects/server/monitoring/default.nix` defining `den.aspects.server.monitoring` with a `nixos` block. Initially only `alertmanager` + `blackbox` exporter enabled (no prometheus server yet → rules standalone won't fire without a server, so also enable a minimal `services.prometheus` for self-scrape + rules).

#### Task 2: Secret for Telegram bot token
- Add sops secret `monitoring/telegram-bot-token` (follow existing `_graphiti.nix`/`nixos-secrets-ops` pattern).
- Reference via `bot_token_file = <secret path>` in alertmanager config. Never inline the token.

#### Task 3: Enable Prometheus (minimal) + Alertmanager → Telegram
- `services.prometheus.enable = true` bound to `127.0.0.1:9090`, `retentionTime = "15d"`, `checkConfig = "syntax-only"` (secret-files gotcha).
- `services.prometheus.alertmanager.enable = true` with Telegram receiver (route → `telegram`, `group_by=["instance"]`, `repeat_interval="8h"`).
- Self-scrape job (node exporter placeholder) + `alertmanagers` target.

#### Task 4: Blackbox exporter + hermes-gateway probe rule
- `services.prometheus.exporters.blackbox.enable = true` (:9115).
- Add blackbox scrape job targeting hermes-gateway HTTP endpoint.
- Rules file:
  ```promql
  probe_success{instance=~".*hermes.*"} == 0  [for: 5m]
  node_systemd_unit_state{name="hermes-gateway.service", state="failed"} == 1
  ```

#### Task 5: Wire aspect into erebus host + dry build + deploy
- Add `den.aspects.server.monitoring` to `modules/hosts/erebus/erebus.nix` includes.
- `jj new` a change; `nix build .#nixosConfigurations.erebus.config.system.build.toplevel --dry-run` → push → switch (local, per AGENTS.md systemd-run path).
- **Verify:** trigger a probe failure (stop hermes-gateway briefly) → Telegram fires. Restore → "resolved" fires.

---

# Phase 2 — Full observability (erebus) + poweredge

**Goal:** Grafana dashboards, node/systemd exporters both hosts, Loki logs. ~1 week.

#### Task 6: node_exporter + systemd_exporter on erebus
- `exporters.node` (add `systemd`, `processes` collectors, unit-include `(hermes|den|podman|grafana|prometheus|alertmanager|loki|promtail|node_exporter).+`), `exporters.systemd`.
- Wire scrape jobs using `config.services.prometheus.exporters.*.port` references.

#### Task 7: Grafana on erebus
- `services.grafana` with provisioned datasource (Prometheus), dashboards dir `modules/aspects/server/monitoring/dashboards/` via `environment.etc."grafana/dashboards"`.
- Use standard dashboard JSON (Node Exporter Full, Blackbox, Systemd).

#### Task 8: Expose via Tailscale serve
- `services.tailscale.serve` for `prometheus.oryx-galaxy.ts.net` + `grafana.oryx-galaxy.ts.net` (127.0.0.1 front). Handle `tailscale serve --https` TLS workaround if hit.

#### Task 9: Poweredge — node/systemd/blackbox exporters + promtail (remote)
- Add exporters to `modules/hosts/poweredge/poweredge.nix`; central erebus Prometheus scrapes poweredge over tailnet.
- Add `den.aspects.server.monitoring` (exporters-only profile) to poweredge includes.
- Deploy remote (`--build-host likivik@poweredge --target-host likivik@poweredge --elevate=sudo`).

#### Task 10: Loki + promtail (logs, both hosts)
- `services.loki` on erebus, `services.promtail` both hosts, journal + docker reads.
- Grafana log datasource.

#### Task 11: Alert rules hardening + dead-man's switch
- More rules: `InstanceDown`, `HostOutOfDiskSpace` (<10% free), `HostOutOfMemory`, `HostSystemdServiceCrashed`.
- Add a "dead man's switch" (absent last scrape → Telegram) so Prometheus/platform failures also alert.

---

# Phase 3 — scale to 3+ hosts / future

- Single Prometheus on erebus fine at 2 hosts. At 3+: `vmagent` per host scraping locally + central VictoriaMetrics single-node on erebus (drop-in, ~3-5x less disk/RAM) — only if RAM/disk pressure demands it.
- Revisit retention + `nix-collect-garbage` as series grow.

---

## Files likely to change

| Path | Change |
|---|---|
| `modules/aspects/server/monitoring/default.nix` | **create** — prometheus+alertmanager+exporters+grafana+loki wiring |
| `modules/aspects/server/monitoring/rules/*.yml` | **create** — alert rules |
| `modules/aspects/server/monitoring/dashboards/*.json` | **create** (Phase 2) |
| `modules/hosts/erebus/erebus.nix` | add `den.aspects.server.monitoring` to includes |
| `modules/hosts/poweredge/poweredge.nix` | add monitoring aspect (exporters) |
| sops secrets | add `monitoring/telegram-bot-token` |

## Tests / validation

- **Task 5 (critical):** probe-failure → Telegram alert; restore → resolved. This is the acceptance test for the whole incident fix.
- `promtool check config` passes (with `"syntax-only"` where secrets involved).
- After Phase 2: Grafana shows erebus+poweredge metrics; Loki tails logs; `up` on all targets = 1.
- Deploys: dry-build before push/switch per AGENTS.md (time-box: state estimate).

## Risks / tradeoffs / open questions

- **Disk 63% used:** keep retention 15-30d + size cap; budget `<10GB`. Poweredge disk unknown → measure before Phase 2.
- **RAM ~3GB free:** Prom+Grafana+Loki+exporters ≈ 400-500MB at this scale — fits, but monitor; consider dropping Loki if tight (logs are non-essential vs telemetry).
- **`checkConfig` sandbox:** must use `"syntax-only"` for alertmanager/prometheus when secret files referenced (else dry-build fails falsely).
- **Secrets:** need the actual Telegram bot token + chat_id. **Open question for user: which chat should alerts land in (this group / home channel / a bot-created channel)?** and do we already have a monitoring bot + token, or create one?
- **Beszel overlap:** keep both; Beszel = glance dashboard, Prometheus = alerting + aggregation. Document the split in the aspect so it's not seen as duplicate.
- **Tailscale serve HTTPS:** known nixpkgs#530174 limitation — expect a config workaround.

---

## Open questions before implementing

1. **Telegram destination for alerts** — same group as this, home channel, or a dedicated channel? 
2. **Do we have a bot token already**, or create a new one (and its chat_id)?
3. **Poweredge spec** — RAM/disk, and confirm it's safe to run exporters (it's already on tailnet).
4. **Phase 1 scope** — deploy to erebus only first (recommended), or push both hosts from the start?