# Forgejo on Serenity — Implementation Plan

> **Status:** PLAN ONLY. Nothing executed yet.
> **Decisions locked** (2026-09-11): tailnet HTTPS via `tailscale serve` · sqlite3 · **split storage SSD/HDD** · git-over-SSH on the existing sshd :22.

**Goal:** Self-hosted Forgejo git server on `serenity`, declared as a den aspect, reachable at `https://serenity.oryx-galaxy.ts.net` over the tailnet, with the DB on SSD and repos/LFS on the 1 TB ZFS pool.

**Architecture:** Thin den aspect wrapping nixpkgs' built-in `services.forgejo` (verified present on our pin). Forgejo binds HTTP to `127.0.0.1:3000`; `tailscale serve` terminates TLS and exposes it to the tailnet only. SQLite DB + secrets stay on the ext4 root SSD; repositories + LFS land on the ZFS pool. Git over SSH rides serenity's existing sshd on :22 — no second daemon.

**Tech stack:** NixOS `services.forgejo` (package `forgejo-lts`), sqlite3, `tailscale serve`, sops-nix (only if secrets get wired).

---

## Decisions locked

| Question | Answer | Consequence |
|---|---|---|
| Exposure | **tailnet HTTPS via `tailscale serve`** | ROOT_URL `https://serenity.oryx-galaxy.ts.net/`, HTTP bound to `127.0.0.1`, no firewall port needed, no ACME |
| Database | **sqlite3** | module default; no postgres service |
| Storage | **split** | DB+secrets on SSD root, repos+LFS on ZFS HDD |
| Git over SSH | **existing sshd :22** | `ssh://forgejo@serenity.oryx-galaxy.ts.net/…`, module manages `$stateDir/.ssh/authorized_keys` |

### Why split storage (the SSD/HDD question)

- **SQLite DB is latency-bound, not capacity-bound.** Every push, page load and background job writes through `fsync`; on spinning rust that latency is exposed directly to the user. It is also tiny (MBs). → **SSD**.
- **Repos + LFS are throughput-bound and capacity-bound.** Packfile reads stream sequentially; 501 G free on HDD beats 114 G on SSD. → **ZFS HDD**.
- Both are first-class module options, so this costs nothing:
  - `database.path` → default, stays on SSD
  - `customDir` (secrets, `app.ini`) → default, stays on SSD
  - `repositoryRoot` → overridden to the HDD
  - `lfs.contentDir` → overridden to the HDD
- **Consequence for backups:** the DB is on the SSD, the repos are on ZFS. A ZFS snapshot therefore covers repos/LFS but **not the database** — so `forgejo dump` is mandatory, not a nice-to-have (Task 7).

---

## Verified facts (checked against our pinned nixpkgs)

Module source: `/nix/store/3p306srz83h9z9v0ma9xcxb8y8cdxkxj-source/nixos/modules/services/misc/forgejo.nix`

| Option | Default | Notes |
|---|---|---|
| `package` | `forgejo-lts` | keep LTS |
| `useWizard` | `false` | declarative `app.ini`; keep false |
| `stateDir` | `/var/lib/forgejo` | on SSD root (default) |
| `customDir` | `${stateDir}/custom` | secrets + generated `app.ini` |
| `database.type` | `sqlite3` | |
| `database.path` | `${stateDir}/data/forgejo.db` | on SSD |
| `repositoryRoot` | `${stateDir}/repositories` | **override → HDD** |
| `lfs.contentDir` | `${stateDir}/data/lfs` | **override → HDD**; module writes `[lfs] PATH` |
| `dump.{enable,interval,backupDir}` | off / daily 04:31 | |
| `secrets.<SECTION>.<KEY>` | `{}` | `LoadCredential` → `FORGEJO__<S>__<K>__FILE` → `environment-to-ini`. Module itself routes `security.SECRET_KEY`, `INTERNAL_TOKEN`, `oauth2.JWT_SECRET` (and `server.LFS_JWT_SECRET` when LFS is on) to `${customDir}/conf/*` |
| `settings.server.DISABLE_SSH` / `SSH_PORT` | — | `SSH_PORT` only affects the displayed clone URL |

SSH integration is automatic: the module sets `services.openssh.settings.AcceptEnv = "GIT_PROTOCOL"` when `START_SSH_SERVER` is false, and creates `${stateDir}/.ssh` (0700, owned by `cfg.user`). The `forgejo` user's home is `stateDir`, so sshd's default `~/.ssh/authorized_keys` resolves to the file Forgejo maintains. **No port conflict with serenity's openssh.**

---

## Current context (measured on serenity, 2026-09-11)

- ZFS `serenity_onetb_zpool/Storage` → `/Storage` (HDD): **501 G available**
- Root ext4 `/dev/sdc2` (SSD): 430 G, **114 G free**
- `/boot`: **49 M free (91%)** — add nothing here
- Ports listening: 8081, 8082, 8084, 631, 6566, and **443 held by `tailscaled`** on `100.108.207.39` — which is precisely why `tailscale serve` is the low-friction choice
- serenity `includes` (`modules/hosts/serenity/serenity.nix:6-22`): core, desktop.*, dev, cprocsp, firefox, server.nc-rag / olmocr-vision / surya-server / monkey-server. **No sops, no nginx.**
- serenity egress currently routes via the erebus tailscale exit node (`148.253.214.185`)

---

## Target layout

| What | Where | Device |
|---|---|---|
| `app.ini`, secrets, sessions, indexers | `/var/lib/forgejo` (+ `/custom`) | SSD |
| SQLite DB | `/var/lib/forgejo/data/forgejo.db` | SSD |
| Git repositories | `/Storage/forgejo/repositories` | ZFS HDD |
| LFS objects | `/Storage/forgejo/lfs` | ZFS HDD |
| Dumps | `/var/backup/forgejo` | SSD (different device from repos) |

Dumps deliberately go to the **SSD**, so a single disk failure does not take out repos *and* backups together.

---

## Tasks

### Task 1 — Write the aspect

**Files:**
- Create: `modules/aspects/server/forgejo/forgejo.nix`
- Modify: `modules/hosts/serenity/serenity.nix:6-22` (add `den.aspects.server.forgejo`)

```nix
{ den, inputs, ... }:
{
  den.aspects.server.forgejo = {
    nixos = { config, lib, pkgs, ... }: {
      services.forgejo = {
        enable = true;

        # stateDir / database.path / customDir stay on the SSD root (defaults)
        repositoryRoot = "/Storage/forgejo/repositories";
        lfs = {
          enable = true;
          contentDir = "/Storage/forgejo/lfs";
        };

        settings = {
          server = {
            DOMAIN = "serenity.oryx-galaxy.ts.net";
            ROOT_URL = "https://serenity.oryx-galaxy.ts.net/";
            HTTP_ADDR = "127.0.0.1";
            HTTP_PORT = 3000;
            SSH_PORT = 22;
            DISABLE_SSH = false;
          };
          service.DISABLE_REGISTRATION = true;
        };
      };

      # Directories on the ZFS pool must exist and be owned by the service user.
      systemd.tmpfiles.rules = [
        "d /Storage/forgejo 0750 forgejo forgejo -"
        "d /Storage/forgejo/repositories 0750 forgejo forgejo -"
        "d /Storage/forgejo/lfs 0750 forgejo forgejo -"
        "d /var/backup/forgejo 0700 forgejo forgejo -"
      ];
    };
  };
}
```

No firewall port for 3000: HTTP is loopback-only and `tailscale serve` fronts it.

**Verify:** `nix eval .#nixosConfigurations.serenity.config.services.forgejo.repositoryRoot`
Expected: `"/Storage/forgejo/repositories"`

---

### Task 2 — Register the aspect with jj

`import-tree` reads the **git tree**, not the jj working copy. A new folder is invisible until it lands in a committed change.

1. `jj st` → expect `A modules/aspects/server/forgejo/forgejo.nix`
2. `jj describe -m "feat(serenity): forgejo as den aspect"`
3. `jj bookmark set dev -r @ && jj git push --all`
4. `nix eval .#nixosConfigurations.serenity.config.services.forgejo.enable` → `true`

A failure reading `attribute 'forgejo' missing` means the aspect isn't in the git tree yet.

---

### Task 3 — Declarative `tailscale serve`

`tailscale serve` is imperative; make it a oneshot so it survives reboots and rebuilds.

```nix
systemd.services.tailscale-serve-forgejo = {
  description = "Expose Forgejo on the tailnet over HTTPS";
  after = [ "tailscaled.service" "forgejo.service" ];
  wants = [ "tailscaled.service" ];
  wantedBy = [ "multi-user.target" ];
  serviceConfig = { Type = "oneshot"; RemainAfterExit = true; };
  script = ''
    ${pkgs.tailscale}/bin/tailscale serve --bg --https=443 http://127.0.0.1:3000
  '';
};
```

**Verify:** `tailscale serve status` shows `https://serenity.oryx-galaxy.ts.net → http://127.0.0.1:3000`, and `curl -sI https://serenity.oryx-galaxy.ts.net/` → `200`.

Prerequisite: HTTPS certificates enabled for the tailnet (needed once, in the admin console).

---

### Task 4 — Deploy (build ON serenity)

Skill pitfall 0a: **build locally on serenity**; do not build serenity's closure on erebus (erebus has ~6.6 G free).

1. `ssh likivik@serenity 'cd /Storage/Git/spectacle && git pull --ff-only origin dev'`
2. Dry-build first (AGENTS.md §3 is mandatory):
   `ssh likivik@serenity 'cd /Storage/Git/spectacle && nix build .#nixosConfigurations.serenity.config.system.build.toplevel --dry-run'`
3. `ssh likivik@serenity 'cd /Storage/Git/spectacle && sudo nixos-rebuild switch --flake .#serenity'`
4. Verify:
   ```bash
   ssh likivik@serenity 'systemctl is-active forgejo; curl -sI http://127.0.0.1:3000/ | head -1'
   ```
   Expected: `active`, `HTTP/1.1 200 OK`

**⏱ Time-box: 20–40 min** (eval 5–15 min + build + activation). Report elapsed vs estimate.

---

### Task 5 — First admin, lock registration

```bash
ssh likivik@serenity 'systemctl cat forgejo | grep ExecStart'   # confirm the binary path first
ssh likivik@serenity 'sudo -u forgejo <forgejo-bin> admin user create \
  --username likivik --email <addr> --admin --must-change-password'
```
Then confirm registration is disabled and create the first repo.

---

### Task 6 — Verify git-over-SSH + LFS

```bash
ssh likivik@serenity 'wc -l </Storage/forgejo/.ssh/authorized_keys; sshd -T | grep -i acceptenv'
```
Add a key in the UI, then:
```bash
ssh -T forgejo@serenity.oryx-galaxy.ts.net          # expect a Forgejo greeting
git clone ssh://forgejo@serenity.oryx-galaxy.ts.net:22/likivik/test.git
```
LFS: push a >1 MB file, confirm the object lands under `/Storage/forgejo/lfs` (proves the HDD override took effect, not the default).

serenity's sshd already has `PasswordAuthentication = false` — keys only, which is what Forgejo uses.

---

### Task 7 — Backups + restore rehearsal

Because the DB is on SSD and repos are on ZFS, **neither alone is a backup.**

```nix
dump = {
  enable = true;
  interval = "*-*-* 04:31:00";
  backupDir = "/var/backup/forgejo";
};
```
Plus a ZFS snapshot policy for `/Storage`. Then **restore into a throwaway directory** and confirm repos + DB come back. A backup that has never been restored is not a backup.

Known gap to record: dumps land on the SSD, repos on the HDD — a fire/theft/loss of the whole machine loses everything. Off-host replication is a follow-up, not v1.

---

### Task 8 — Secrets (only if a mailer / metrics / OAuth are wanted)

Use the module's credential path, never plaintext in `settings`:

```nix
services.forgejo.secrets.mailer.PASSWD = config.sops.secrets."forgejo/mailer-password".path;
```

That declares a sops option, so the aspect must include the sops aspect (serenity otherwise has no sops module):
```nix
den.aspects.server.forgejo = {
  includes = [ den.aspects.server.sops ];
  ...
};
```
The secret lives in `secrets/serenity/secrets.yaml`. Either erebus's age key must be in that host's `creation_rules` group, or the `sops --set` must run **on serenity** (TPM identity).

---

### Task 9 (deferred) — Actions, public exposure, off-host backup

YAGNI until there's a CI need. Public access would mean cloudflared + a `filepath.ru` subdomain (mirrors poweredge) and adds a public attack surface.

---

## Files likely to change

| Path | Change |
|---|---|
| `modules/aspects/server/forgejo/forgejo.nix` | **create** |
| `modules/hosts/serenity/serenity.nix` | modify `includes` |
| `secrets/serenity/secrets.yaml` | only if Task 8 in scope |
| `secrets/.sops.yaml` | only if a new secret path needs `creation_rules` |

## Validation summary

| Check | Command | Pass |
|---|---|---|
| aspect resolves | `nix eval …services.forgejo.enable` | `true` |
| storage split | `nix eval …services.forgejo.repositoryRoot` | `/Storage/forgejo/repositories` |
| dry-build | `nix build …toplevel --dry-run` | exit 0 |
| service | `systemctl is-active forgejo` | `active` |
| HTTP | `curl -sI 127.0.0.1:3000/` | `200` |
| tailnet HTTPS | `curl -sI https://serenity.oryx-galaxy.ts.net/` | `200` |
| not publicly bound | `ss -tlnp \| grep 3000` | `127.0.0.1:3000` only |
| SSH clone | `git clone ssh://forgejo@…:22/…` | succeeds |
| LFS path | push >1 MB | file under `/Storage/forgejo/lfs` |
| backup | dump runs + restore rehearsal | repo + DB recovered |

## Risks & tradeoffs

1. **`tailscale serve` is imperative state.** Mitigated by the Task 3 oneshot; verify after every rebuild.
2. **Desktop uptime.** Forgejo is up only while serenity is up. Fine for a personal forge, wrong for a team.
3. **sqlite on a desktop SSD.** Correct choice here; Postgres is the escape hatch if write contention ever appears.
4. **`ROOT_URL` must match reality** or every clone URL and web link renders wrong. If exposure changes later, this changes with it.
5. **Split storage = split failure domains.** ZFS snapshots do not contain the DB; the dump does not contain repo history. Task 7 must cover both, and off-host remains a gap.
6. **Egress via the erebus exit node** — outbound mail leaves from erebus's public IP, which can trip spam heuristics.
7. **First-deploy ownership.** `/Storage/forgejo/*` must be `forgejo:forgejo` before the service starts; hence the tmpfiles rules in Task 1.
8. **No migration path.** This plan assumes an empty forge; importing existing repos/mirrors is separate work.

## Still open (answer before Task 1)

1. **First admin:** username + email to create? (I'll assume `likivik` + a mail address you give me.)
2. **Confirm the URL:** `https://serenity.oryx-galaxy.ts.net/` as `ROOT_URL` — OK, or do you want a `filepath.ru` name resolved to the tailnet IP instead?
3. **Tailnet HTTPS certs** already enabled in the admin console? If not, that's a one-click prerequisite for Task 3.

## Estimate

Tasks 1–5 (working, reachable, logged-in forge): **~1–2 h** wall clock, of which 20–40 min is the deploy.
Tasks 6–8 (SSH/LFS verification, backups + restore rehearsal, secrets): **~1 h**.
