# Prometheus on NixOS — ultra-recent notes (Sep–Oct 2026)

Status-set fact for context: earlier incidents (Sep 28) were OTel version drift in hermes lazy-packages; this note is the monitoring blueprint, not that fix.

---

## 1. Current Prometheus status (2026)

- **Latest stable: v3.5.x — the LTS release** (v3.5.0, 2025-07-14; now standard for 2026). No known breaking changes in the 3.4→3.5 line.
  https://github.com/prometheus/prometheus/releases/tag/v3.5.0
- **Native histograms are now STABLE** (not experimental). The old `--enable-feature=native-histograms` flag is a no-op; you opt in per-target with `scrape_native_histograms: true` / global `always_scrape_classic_histograms`.
  https://github.com/prometheus/prometheus/blob/main/CHANGELOG.md
- **OTLP receiver is native** — Prometheus 3.x ingests OpenTelemetry directly (OTLP→Prometheus, delta temporality, NHCB histogram conversion). No gateway needed.
  https://github.com/prometheus/prometheus/blob/main/CHANGELOG.md
- **Efficiency push is active** (relevant to the earlier VM-vs-Prometheus decision):
  - Uncached-I/O flag (v3.5, Linux): bypasses page cache → **20–50% lower page-cache footprint**.
    https://prometheus.io/blog/2026/03/05/uncached-io/
  - TSDB optimizations: skips clean series during mmap (36–54% faster at 100k series), XOR chunk read fast-path (−22%).
    https://github.com/prometheus/prometheus/pull/18272
  - Mainline roadmap: native composite storage, OpenMetrics 2.0, TSDB Parquet work (with Cortex/Thanos/Mimir).
    https://prometheus.io/blog/2026/02/14/modernizing-prometheus-composite-samples/

**Net:** Prometheus is no longer the "inefficient" option the old VM benchmark rounds claim — it's closing the gap while remaining CNCF-neutral, Apache-2.0, and the skill employers ask for.

---

## 2. Prometheus on NixOS — setup (module maps)

All config is declarative via the NixOS module. **Canonical references:**
- NixOS wiki Prometheus page: https://wiki.nixos.org/wiki/Prometheus
- Module source: `nixos/modules/services/monitoring/prometheus/default.nix`
- Exporters module docs: `nixos/modules/services/monitoring/prometheus/exporters.nix`
- Alertmanager module: `nixos/modules/services/monitoring/prometheus/alertmanager.nix`

**Minimal + full working shape:**
```nix
services.prometheus = {
  enable = true;
  listenAddress = "127.0.0.1";     # don't put port here — separate `port` option
  port = 9090;
  webExternalUrl = "https://erebus.oryx-galaxy.ts.net/prometheus/";
  globalConfig.scrape_interval = "15s";
  retentionTime = "15d";           # shorter for limited disk; size-based also possible
  checkConfig = true;              # set "syntax-only" if using password_file secrets

  exporters = {
    node = { enable = true; port = 9100; };
    systemd = { enable = true; port = 9558; };
    blackbox = { enable = true; port = 9115; };
  };

  scrapeConfigs = [
    { job_name = "node";
      static_configs = [{ targets = ["localhost:${toString config.services.prometheus.exporters.node.port}"]; }]; }
  ];

  alertmanagers = [
    { scheme = "http";
      static_configs = [{ targets = ["localhost:${toString config.services.prometheus.alertmanager.port}"]; }]; }
  ];
};
```

**Best-practice tip:** reference exporter ports via `config.services.prometheus.exporters.*.port` (as above) so renames don't break scrape configs.

### Alertmanager → Telegram (NixOS shape)
```nix
services.prometheus.alertmanager = {
  enable = true;
  configuration = {
    route  = { group_by = ["instance"]; group_wait = "30s"; group_interval = "1m";
               repeat_interval = "8h"; receiver = "telegram"; };
    receivers = [
      { name = "telegram";
        telegram_configs = [{
          send_resolved = true;
          bot_token_file = "/run/secrets/telegram-bot-token";  # never inline the token
          chat_id = 123456;
          parse_mode = "Markdown";
        }]; }
    ];
  };
};
services.prometheus.alertmanager.environmentFile = "/path/to/env"; # optional secret source
```
- Secrets: use `bot_token_file` (or `environmentFile` for `$VAR` interpolation) — **do not** put the token in `configuration` as literal text. On this repo, secrets live in sops (see `_graphiti` pattern / `nixos-secrets-ops` skill).
- **`checkConfig` sandbox gotcha:** `promtool check`/`amtool check-config` run in a Nix sandbox where `*/secret-files*` aren't visible → set `services.prometheus.checkConfig = "syntax-only"` when using `password_file`/`bot_token_file`.
  https://github.com/NixOS/nixpkgs/blob/master/nixos/modules/services/monitoring/prometheus/alertmanager.nix

### Blackbox probe of hermes-gateway (the actual incident fix)
```nix
services.prometheus.exporters.blackbox = { enable = true; port = 9115; };
# scrape job targets the probe endpoint; rule checks probe_success
```
Rule (catches a service that is *alive but parked* — the silent failure from Sep 28):
```promql
probe_success{instance=~".*hermes.*"} == 0  1:5m
```
Also pair with `systemd_exporter`: `node_systemd_unit_state{name="hermes-gateway.service", state="failed"} == 1`.

### Grafana (dashboards; ~150MB RSS)
```nix
services.grafana = {
  enable = true;
  provision = { enable = true; };
  settings.server = { domain = "grafana.oryx-galaxy.ts.net"; http_addr = "127.0.0.1"; http_port = 3000; };
};
```
Provisioned datasource (backend auto-derives URL from modules):
```nix
/services.grafana.provision.datasources.settings.datasources = [{
  name = "Prometheus"; type = "prometheus";
  url = "http://${config.services.prometheus.listenAddress}:${toString config.services.prometheus.port}";
  isDefault = true; editable = false;
}];
```

---

## 3. Recent best-practice guides (2025–26)

- **Full NixOS + Prometheus + Alertmanager + Grafana + Telegram homelab guide (2025)** — mirrors this exact plan (observe the `bot_token_file` + age secret pattern).
  https://blog.gk.wtf/posts/nixos-monitoring/
- **High-availability Prometheus+Alertmanager on NixOS** (2025) — the 2-of-3 redundant pattern, if you ever want HA; overkill for 1–2 hosts but good thinking for exams/jobs.
  https://cs-syd.eu/posts/2025-07-20-highly-available-monitoring-with-prometheus-and-alertmanager-on-nixos
- **Prometheus exporters best practices (Sysdig, late 2025):** use maintained/curated exporters (start at the official Exporters page), alert on *actionable* conditions only, avoid alert fatigue, use severity labels, plan for scale (Thanos/Cortex only when you need long-term/flederated).
  https://www.sysdig.com/blog/prometheus-exporters-best-practices
  https://prometheus.io/docs/instrumenting/exporters/
- **General best practices (CloudRaft, 2025):** node_exporter for system metrics, blackbox for availability, use relabeling, set **both time- and size-based retention** (e.g. 15d *and* 500GB cap), alert on what needs immediate action, group alerts by service, test rules with `promtool`.
  https://www.cloudraft.io/blog/prometheus-best-practices

---

## 4. Fleet-wide best practices (this repo's de-facto standard)

- **Resource shape:** Prometheus + Grafana + node/systemd/blackbox exporters + Loki+promtail ≈ **400–500 MB RSS**, <512 MB for a few machines. Compliant with erebus (7.8GB, ~3GB free) if retention kept modest (≤30d).
- **Disk:** keep `retentionTime` modest (15–30d) + a size cap; reconcile with `nix-collect-garbage`.
- **Exposure:** bind everything to `127.0.0.1`, expose via Tailscale serve. Known workaround for `tailscale serve --https` TLS (nixpkgs#530174) if you hit it.
- **Alerting cardinality rule:** one probe rule per critical service (hermes-gateway first), `for: 5m` to avoid flap.

---

## 5. Sources (all 2025–2026)

| Topic | URL |
|---|---|
| Prometheus 3.5 LTS release | github.com/prometheus/prometheus/releases/tag/v3.5.0 |
| Changelog (native histograms stable, OTLP) | github.com/prometheus/prometheus/blob/main/CHANGELOG.md |
| Uncached I/O (efficiency) | prometheus.io/blog/2026/03/05/uncached-io |
| TSDB Parquet / composite storage | prometheus.io/blog/2026/02/14/modernizing-prometheus-composite-samples |
| TSDB head-mmap perf | github.com/prometheus/prometheus/pull/18272 |
| NixOS wiki: Prometheus | wiki.nixos.org/wiki/Prometheus |
| NixOS export scrip (module) | github.com/NixOS/nixpkgs/...prometheus/exporters.nix |
| Alertmanager module (checkConfig, environmentFile) | github.com/NixOS/nixpkgs/...prometheus/alertmanager.nix |
| Full NixOS+AM+Grafana+Telegram guide (2025) | blog.gk.wtf/posts/nixos-monitoring |
| HA Prometheus+AM on NixOS (2025) | cs-syd.eu/posts/2025-07-20-... |
| Blackbox exporter | github.com/prometheus/blackbox_exporter |
| Exporters list (official) | prometheus.io/docs/instrumenting/exporters |
| Exporter best practices (Sysdig) | sysdig.com/blog/prometheus-exporters-best-practices |
| Best practices (CloudRaft) | cloudraft.io/blog/prometheus-best-practices |