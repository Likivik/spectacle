# Cloudflare Tunnel — public share links only on Nextcloud

## Goal
- Nextcloud accessible via Tailscale for full access (tailnet only)
- Public share links (`/s/<token>`) accessible via Cloudflare Tunnel
- Zero public ports on poweredge
- Zero exposed Nextcloud login/admin page

## Architecture

```
Tailnet users → poweredge.oryx-galaxy.ts.net → Tailscale Serve :443 → nginx :80 → full access
Public users  → share.filepath.ru → Cloudflare Edge → cloudflared tunnel → nginx :8081 → path-filtered → Nextcloud :80
```

## Prerequisites

- Domain on Cloudflare DNS (filepath.ru — NS changed from Timeweb to Cloudflare)
- cloudflared package on poweredge (available in nixpkgs)

## Manual steps (Cloudflare dashboard)

1. **Add domain** — `filepath.ru` as new site on Free plan
2. **Change NS** — replace Timeweb NS with Cloudflare's, wait for Active
3. **Create tunnel** — Zero Trust → Networks → Tunnels → Create tunnel named `nextcloud-share`
4. **Download credentials JSON** — tunnel page provides this after creation
5. **Add public hostname** in tunnel config:
   ```
   Hostname: share.filepath.ru
   Service:  http://localhost:8081
   ```
6. **Add credentials to sops** — `secrets/poweredge/secrets.yaml` key: `cloudflare/tunnel-credentials`

## NixOS changes

### `modules/hosts/poweredge/poweredge.nix`
- sops secret: `cloudflare/tunnel-credentials`
  ```
  sops.secrets."cloudflare/tunnel-credentials" = {
    sopsFile = ../../../secrets/poweredge/secrets.yaml;
    owner = "nextcloud";
    group = "nextcloud";
    mode = "0400";
  };
  ```
- systemd service for cloudflared
  ```
  systemd.services.cloudflared = {
    description = "Cloudflare Tunnel for Nextcloud share links";
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig.Type = "simple";
    serviceConfig.Restart = "always";
    serviceConfig.RestartSec = 5;
    serviceConfig.User = "nextcloud";
    script = ''
      ${pkgs.cloudflared}/bin/cloudflared tunnel \
        --config /run/secrets/cloudflare-tunnel-config.yml run
    '';
  };
  ```
- Set the config file path to the secret path

### `modules/aspects/server/nextcloud/default.nix`
- Add second nginx server block on `127.0.0.1:8081` with path allowlist:
  - `/s/*` — share pages + downloads
  - `/public.php*` — public endpoints
  - `/dist/*` — JS/CSS bundles
  - `/core/*` — core assets
  - `/apps/files_sharing/*` — sharing app assets
  - `/remote.php/dav/public-files/*` — WebDAV public files
  - `/index.php/apps/files_sharing/*` — sharing controller
  - Everything else → 403
- Add `overwritehost = "share.filepath.ru"` to settings
- Add Cloudflare IP ranges to `trusted_proxies`
- Add `HTTP_CF_CONNECTING_IP` to `forwarded_for_headers`

### `nextcloud/default.nix` — nginx config snippet (conceptual)
```
services.nginx.virtualHosts."127.0.0.1:8081" = {
  root = "/dev/null";
  locations."/s/" = { proxyPass = "http://127.0.0.1:80/s/"; };
  locations."/public.php" = { proxyPass = "http://127.0.0.1:80/public.php"; };
  locations."/dist/" = { proxyPass = "http://127.0.0.1:80/dist/"; };
  locations."/core/" = { proxyPass = "http://127.0.0.1:80/core/"; };
  locations."/apps/files_sharing/" = { proxyPass = "http://127.0.0.1:80/apps/files_sharing/"; };
  locations."/remote.php/dav/public-files/" = { proxyPass = "http://127.0.0.1:80/remote.php/dav/public-files/"; };
  locations."/index.php/apps/files_sharing/" = { proxyPass = "http://127.0.0.1:80/index.php/apps/files_sharing/"; };
  locations."/status.php" = { proxyPass = "http://127.0.0.1:80/status.php"; };
  extraConfig = ''
    location / {
      return 403;
    }
  '';
};
```

## Deploy

```bash
nixos-rebuild switch --flake .#poweredge \
  --target-host likivik@poweredge \
  --build-host likivik@poweredge \
  --elevate sudo
```

## Verification

- `curl -s -o /dev/null -w "%{http_code}" http://share.filepath.ru/s/` → 200 or 302
- `curl -s -o /dev/null -w "%{http_code}" http://share.filepath.ru/` → 403
- `curl -s -o /dev/null -w "%{http_code}" http://share.filepath.ru/login` → 403
- Via tailscale: full Nextcloud at `poweredge.oryx-galaxy.ts.net`
