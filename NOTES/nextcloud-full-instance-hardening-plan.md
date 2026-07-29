# Nextcloud Security Hardening Plan — Full Instance Behind Cloudflare Tunnel

## Threat Model
- Full Nextcloud instance exposed via Cloudflare Tunnel at `nextcloud.filepath.ru`
- Internal access via Tailscale at `poweredge.oryx-galaxy.ts.net`
- Data stored on ZFS at `/tank/nextcloud`
- Users: admin + personal account
- 2FA enforced globally

---

## Layer 1: Cloudflare Edge (First Line of Defense)

### 1.1 Cloudflare WAF Managed Rules
- Enable **Managed Ruleset** (Free plan includes OWASP Top 10)
- Enable **Bot Fight Mode** (Free plan) — blocks known bad bots
- Custom WAF rules: rate limit 100 req/min per IP on `/login`

### 1.2 Cloudflare SSL/TLS
- SSL/TLS: **Full (Strict)** — Cloudflare validates origin cert
- TLS 1.3 minimum
- Always Use HTTPS: On
- HSTS: max-age=31536000; includeSubDomains; preload

### 1.3 DNS / Network
- DNS record for `nextcloud.filepath.ru` → proxied (orange cloud)
- `poweredge.oryx-galaxy.ts.net` → DNS only (gray cloud) for Tailscale

---

## Layer 2: Nextcloud config.php Hardening

### 2.1 Domain & Proxy Configuration
```php
'trusted_domains' => [
  'poweredge.oryx-galaxy.ts.net',
  'nextcloud.filepath.ru',
],
// Unconditional — all URLs use public domain
'overwritehost' => 'nextcloud.filepath.ru',
'overwriteprotocol' => 'https',
// Both proxies (cloudflared + tailscale-serve) terminate on localhost
'trusted_proxies' => ['127.0.0.1', '::1'],
// CF sets CF_CONNECTING_IP, tailscale-serve sets X_FORWARDED_FOR
'forwarded_for_headers' => ['HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR'],
```

### 2.2 Admin & Authentication
```php
// Admin only from tailnet
'allowed_admin_ranges' => [
  '100.64.0.0/10',
  'fd7a:115c:a1e0::/48',
],
// 2FA already enforced globally via 'twofactor_enforced' => 'true'
// Password policy: set via password_policy app (admin UI), NOT config.php
```

### 2.3 Logging & Monitoring
```php
'loglevel' => 2, // Required for fail2ban
'logfile' => '/tank/nextcloud/data/nextcloud.log',
'logfilemode' => 0640,
'logtimezone' => 'Europe/Moscow',
```

### 2.4 Security Headers & CSP
Headers are set at the nginx level (nextcloud module already sets the critical ones natively).
CSP report-only can be added later if needed.

### 2.5 Data & Config Directories
```php
// Data already on ZFS at /tank/nextcloud/data (outside web root) ✓
// Move config.php out of web root
// Set NEXTCLOUD_CONFIG_DIR=/etc/nextcloud via systemd/environment
```

### 2.6 Preview & Apps
```php
// Limit preview providers to safe ones only
'enable_previews' => true,
'enabledPreviewProviders' => [
  'OC\\Preview\\PNG', 'OC\\Preview\\JPEG', 'OC\\Preview\\GIF',
  'OC\\Preview\\BMP', 'OC\\Preview\\XBitmap', 'OC\\Preview\\MP3',
  'OC\\Preview\\TXT', 'OC\\Preview\\MarkDown',
],
// Disable risky providers (Office, PDF, video, etc.)

// Disable debug
'debug' => false,
```

### 2.7 Brute Force & Security
```php
'auth.bruteforce.protection.enabled' => true,
```

---

## Layer 3: Nginx / Web Server Hardening

### 3.1 Security Headers
The nixpkgs nextcloud module already sets critical headers natively in its nginx vhost:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-Robots-Tag: noindex, nofollow`
- `X-Permitted-Cross-Domain-Policies: none`
- `Referrer-Policy: no-referrer`
- `Strict-Transport-Security` (when `https = true`)
No additional nginx header config needed.

### 3.2 Disable Unnecessary Methods
```nginx
if ($request_method !~ ^(GET|POST|HEAD|OPTIONS|PROPFIND|REPORT|MKCOL|PUT|DELETE)$) {
    return 405;
}
```

---

## Layer 4: Fail2ban (Poweredge — Internal + Cloudflare Fallback)

### 4.1 Fail2ban Filter (`/etc/fail2ban/filter.d/nextcloud.conf`)
Use official filter from hardening guide.

### 4.2 Fail2ban Jail (`/etc/fail2ban/jail.d/nextcloud.local`)
```ini
[nextcloud]
backend = auto
enabled = true
port = 80,443
protocol = tcp
filter = nextcloud
maxretry = 5
bantime = 86400
findtime = 43200
logpath = /tank/nextcloud/data/nextcloud.log
```

### 4.3 Note
Cloudflare handles public-side brute force via WAF/rate limiting. Fail2ban protects tailnet/internal access and catches anything Cloudflare misses.

---

## Layer 5: System Hardening (Poweredge NixOS)

### 5.1 Kernel / Boot
```nix
boot.kernelParams = [
  "slab_nomerge"
  "slub_debug=FZP"
  "page_poison=1"
  "vsyscall=none"
  "module.sig_enforce=1"
  "lockdown=confidentiality"
];
security.secureBoot.enable = false; # unless hardware supports it
```

### 5.2 Systemd Hardening (Nextcloud services)
```nix
systemd.services.nextcloud-phpfpm.serviceConfig = {
  ProtectSystem = "strict";
  ProtectHome = true;
  PrivateTmp = true;
  PrivateDevices = true;
  ProtectKernelTunables = true;
  ProtectKernelModules = true;
  ProtectControlGroups = true;
  NoNewPrivileges = true;
  LockPersonality = true;
  ReadWritePaths = [ "/tank/nextcloud" "/var/lib/nextcloud" ];
};
# Notes:
# - ProtectSystem=strict needs ReadWritePaths for data + install dirs
# - Skip MemoryDenyWriteExecute — may break opcache JIT
# - RestrictAddressFamilies, RestrictNamespaces, CapabilityBoundingSet — test incrementally
```

### 5.3 File Permissions
- `/tank/nextcloud/data`: 750, user:nextcloud, group:nextcloud
- `/tank/nextcloud/config`: 750, user:nextcloud, group:nextcloud
- `/etc/nextcloud`: 750, user:nextcloud, group:nextcloud

---

## Layer 6: Network Segmentation

### 6.1 Tailscale ACL
```json
{
  "action": "accept",
  "src": ["tag:proxy"],
  "dst": ["tag:nextcloud:443"]
}
```
Only the proxy (or Cloudflare Tunnel node) can reach Nextcloud on port 443.

### 6.2 Firewall (NixOS)
```nix
networking.firewall = {
  enable = true;
  allowedTCPPorts = [ 22 ]; # SSH only
  allowedUDPPorts = [ 41641 ]; # Tailscale
  # No public ports — Cloudflare Tunnel is outbound
};
```

---

## Layer 7: Monitoring & Alerting

- **Cloudflare Analytics** — WAF blocks, bot traffic, rate limits
- **Nextcloud Logs** — `nextcloud.log` level 2 → fail2ban
- **Systemd journal** — `cloudflared` service health
- **ZFS scrub** — weekly auto-scrub on `tank`
- **Healthcheck** — `/status.php` endpoint monitored

---

## Layer 8: Backup & Recovery

- **ZFS snapshots** — hourly for 24h, daily for 30d, monthly for 1yr
- **Config backup** — `config.php` + `config/` dir via sops/git
- **Database backup** — daily pg_dump via cron
- **Test restore** — quarterly drill

---

## Implementation Checklist

### Phase A ✅ (Implemented)
| Item | Status |
|------|--------|
| `allowed_admin_ranges` = tailnet | ✅ |
| `forwarded_for_headers` | ✅ |
| `loglevel` = 2, `logfile`, `logfilemode`, `logtimezone` | ✅ |
| Preview providers limited (safe subset) | ✅ |
| `auth.bruteforce.protection.enabled` | ✅ |
| Fail2ban with nextcloud filter (maxretry=5) | ✅ |
| Systemd hardening for nextcloud-phpfpm | ✅ |
| Firewall lock down (SSH + tailscale only) | ✅ |

### Phase B 📋 (Cloudflare Tunnel — In Progress)
| Item | Status |
|------|--------|
| DNS propagation (filepath.ru → Cloudflare) | ⏳ In progress |
| Create tunnel in Cloudflare dashboard | ⬜ |
| Add tunnel credentials to sops | ⬜ |
| cloudflared service (poweredge.nix) | ⬜ |
| Path-filtered nginx on :8081 (nextcloud module) | ⬜ |
| `overwritehost` = nextcloud.filepath.ru | ⬜ |
| `trusted_domains` + nextcloud.filepath.ru | ⬜ |
| `forwarded_for_headers` + HTTP_CF_CONNECTING_IP | ⬜ |
| Cloudflare WAF + SSL/TLS config | ⬜ |

### Phase C 📋 (Done)
| Item | Status |
|------|--------|
| NEXTCLOUD_CONFIG_DIR outside webroot | ✅ (already handled by NixOS) |
| ZFS auto-snapshots (hourly=36, daily=30, weekly=4, monthly=3) | ✅ |
| PostgreSQL dumps to /tank/backups/postgresql (daily 04:00) | ✅ |
| Disable snapshots on tank/backups/* | ✅ |

---

## Open Items

1. **Fail2ban ban time** — 1 day (86400s) reasonable?
2. **ZFS replication to off-site machine** — Tier 2 backup (future)
3. **Monitoring/alerting** — Prometheus/Grafana or cron+journalctl (future)

---

## Status

### ✅ Done
- Cloudflare Tunnel running (`nextcloud.filepath.ru` → poweredge)
- Nextcloud 2FA + admin tailnet-only + brute force protection
- Fail2ban (5 → 24h ban) + WAF (DDoS, TLS, HSTS)
- Systemd hardening for php-fpm
- ZFS auto-snapshots (hourly=36, daily=30, weekly=4, monthly=3)
- PostgreSQL dumps to `/tank/backups/postgresql` (daily 04:00)
- No inbound ports (tunnel is outbound)

### 📋 Future
1. **ZFS replication to off-site machine** — Tier 2 backup (syncoid)
2. **Monitoring/alerting** — Prometheus/Grafana or cron+journalctl
3. **Tier 3 file-level backup** — Borg/Restic to Backblaze B2 or similar