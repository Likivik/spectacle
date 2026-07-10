# NixOS Deployment Tools Comparison

**Last updated:** 2026-07-03

## TL;DR

**Best Den integration (bridge approach):** Clan.lol (flake-parts module, shares nixosConfigurations) or colmena-flake (direct nixosConfigurations read). Both allow keeping Den's aspect composition intact.

**Simplest path (no Den changes):** `nixos-rebuild --target-host` works out of the box. colmena-flake adds parallel deploy with no flake modifications. Panix adds full lifecycle with TUI but is beta.

**Most common production pattern:** nixos-anywhere (provision) + sops-nix (secrets) + colmena/nixos-rebuild (deploy). This is what Numtide, Mic92, and most of the ecosystem use.

**For initial provisioning only:** nixos-anywhere (already in flake inputs).

---

## Overview Table

| Tool | Type | Den Compatible | Initial Install | Ongoing Deploy | Secrets | Health Checks | Multi-Host | State | Last Active |
|------|------|----------------|-----------------|----------------|---------|---------------|------------|-------|-------------|
| **Clan.lol** | Full orchestration | ✅ Native flake-parts module | ✅ Yes | ✅ Yes | ✅ Built-in (sops/age) | ❌ No | ✅ Yes | Stateless | 2026-07 (active) |
| **Colmena** | Stateless deploy | ⚠️ Separate output | ❌ No | ✅ Yes | ✅ deployment.keys | ❌ No | ✅ Yes | Stateless | 2026-06 (active) |
| **deploy-rs** | Simple multi-profile | ⚠️ Separate output | ❌ No | ✅ Yes | ❌ No | ❌ No | ✅ Yes | Stateless | 2026-01 (active) |
| **Morph** | Stateless deploy | ❌ Separate network.nix | ❌ No | ✅ Yes | ⚠️ Basic (scp) | ✅ Yes | ✅ Yes | Stateless | 2025-11 (maintenance) |
| **NixOps4** | Resource management | ❌ Separate system | ⚠️ Via providers | ✅ Yes | ❌ No | ❌ No | ✅ Yes | Stateful | 2026-06 (in dev) |
| **nixos-rebuild** | Built-in | ✅ Direct | ❌ No | ✅ Yes | ❌ No | ❌ No | ⚠️ Manual | Stateless | 2026-07 (stable) |
| **nixos-anywhere** | Initial install | ✅ Input exists | ✅ Yes | ❌ No | ❌ No | ❌ No | ✅ Yes | N/A | 2026-06 (active) |
| **nixos-generators** | Image generation | ✅ Input exists | ⚠️ Image only | ❌ No | ❌ No | ❌ No | N/A | N/A | 2025 (deprecated) |
| **nixos-infect** | System conversion | ❌ N/A | ✅ Yes | ❌ No | ❌ No | ❌ No | N/A | N/A | 2025 (maintenance) |
| **nixos-in-place** | In-place install | ❌ N/A | ✅ Yes | ❌ No | ❌ No | ❌ No | N/A | N/A | 2015 (abandoned) |
| **nixos-shell** | VM testing | ❌ N/A | ❌ No | ❌ No | ❌ No | ❌ No | N/A | N/A | 2026 (active) |
| **Panix** | Orchestrator (beta) | ✅ Direct (flake-agnostic) | ✅ Yes | ✅ Yes | ✅ rsync files | ❌ No | ✅ Yes | Stateless | 2026-04 (beta) |
| **Bento** | Pull-based deploy | ❌ Central server required | ❌ No | ✅ Yes | ❌ Outside scope | ✅ Status reports | ✅ Yes | Stateless | 2022-2024 (stable) |
| **Hercules CI Effects** | CI-integrated deploy | ✅ Direct | ❌ No | ✅ Yes | ✅ Agent secrets | ❌ No | ✅ Yes | N/A | 2026 (active) |
| **FlakeHub Deploy** | Commercial deploy | ✅ Direct | ❌ No | ✅ Yes | ✅ FlakeHub Cache | ❌ No | ✅ Yes | N/A | 2026 (active) |

---

## Detailed Comparison

### 1. Clan.lol

**Architecture:** Full orchestration framework built on flake-parts. Provides `clan.*` options alongside Den's `den.*` options.

**Key Features:**
- Native flake-parts module (same architectural layer as Den)
- Handles both initial provisioning (`clan machines install`) and ongoing updates (`clan machines update`)
- Built-in secrets management via `clan.vars` (sops backend)
- Declarative service layer (30+ built-in services: wireguard, borgbackup, syncthing, etc.)
- Inventory system for fleet coordination
- Mesh VPN (wireguard/zerotier/yggdrasil)
- Backups (borgbackup)
- Monitoring (prometheus + grafana)
- macOS support via nix-darwin

**Den Compatibility:** ✅ **Best integration**
- Native flake-parts module (`clan-core.flakeModules.default`)
- Shares `nixosConfigurations` namespace (mergeable via `manySubmodule`)
- Can coexist with Den's `den.hosts` without collision
- Path A: Import clan as flakeModule, keep Den owning hosts, use clan for deployment/CLI only
- Path B: Override Den's `instantiate` per-host to use `clan-core.lib.clan`
- Path C: Full migration to clan.machines (requires moving host definitions)

**nixos-anywhere Integration:** ✅ Already integrated (uses disko)

**Maintenance:** Very active (2026-07). Regular changelogs, active development, 881+ stars.

**Use Case:** Full fleet orchestration with secrets, networking, backups. Best for 8+ heterogeneous hosts.

**Links:**
- Docs: https://docs.clan.lol
- Source: https://git.clan.lol/clan/clan-core
- Community: https://clan.lol/community

---

### 2. Colmena

**Architecture:** Stateless deployment tool modeled after NixOps/morph. Uses separate `colmenaHive` output.

**Key Features:**
- Simple, stateless deployment
- Parallel deployment support
- Tag-based host filtering (`--on @tag`)
- Secrets via `deployment.keys` (transferred out-of-band)
- SSH-based deployment
- Works with existing NixOps/morph configs

**Den Compatibility:** ⚠️ **Requires bridge module**
- Uses separate `colmenaHive` output (not `nixosConfigurations`)
- Third-party flake-parts module exists: `juspay/colmena-flake`
- Bridge module maps `nixosConfigurations` to `colmenaHive`
- Less integrated than clan (separate output namespace)

**nixos-anywhere Integration:** ❌ Not integrated (initial install only)

**Maintenance:** Active (2026-06). 1.6k+ stars, regular releases.

**Use Case:** Simple stateless deployment for 4+ hosts. Good if you don't need secrets management or fleet orchestration.

**Limitations:**
- No initial provisioning (only ongoing updates)
- Secrets management is basic (manual key distribution)
- No built-in networking/backups/monitoring
- Requires separate output in flake

**Links:**
- Docs: https://colmena.cli.rs
- Source: https://github.com/zhaofengli/colmena

---

### 3. deploy-rs

**Architecture:** Simple multi-profile Nix-flake deploy tool. Uses separate `deploy` output.

**Key Features:**
- Simple, stateless deployment
- Multi-profile support (deploy different configs to different users)
- Magic rollback (auto-revert on failure)
- SSH-based deployment
- Works with any Nix profile (not just NixOS)
- Lesser-privileged deployments (can deploy to non-root users)

**Den Compatibility:** ⚠️ **Separate output**
- Uses separate `deploy` output (not `nixosConfigurations`)
- No flake-parts module (manual wiring required)
- Less integrated than clan or colmena

**nixos-anywhere Integration:** ❌ Not integrated

**Maintenance:** Active (2026-01). 1.1k+ stars, but slower development than clan/colmena.

**Use Case:** Simple deployment for heterogeneous profiles (NixOS + user configs). Good for lesser-privileged deployments.

**Limitations:**
- No initial provisioning
- No secrets management
- No health checks
- No built-in networking/backups
- Requires separate output in flake
- Incompatible with Nix 2.33+ (fix in progress)

**Links:**
- Source: https://github.com/serokell/deploy-rs

---

### 4. Morph (DBCDK/morph)

**Architecture:** Stateless deployment tool. Uses separate `network.nix` file.

**Key Features:**
- Simple, stateless deployment
- Health checks (HTTP and command-based)
- Multi-host support with ordered deployment
- Basic secret management (scp files to remote)
- SSH-based deployment

**Den Compatibility:** ❌ **Separate network.nix**
- Uses separate `network.nix` file (not flake outputs)
- No flake-parts integration
- Least integrated option

**nixos-anywhere Integration:** ❌ Not integrated

**Maintenance:** Maintenance mode (2025-11). 1k+ stars, but slow development. Last release v1.8.0 (2024-10).

**Use Case:** Simple deployment with health checks. Good for 4-10 hosts where you want deployment ordering guarantees.

**Limitations:**
- No initial provisioning
- Basic secrets (manual scp)
- No flake-parts integration
- Separate network.nix file (not in flake)
- Less active development
- No macOS support

**Links:**
- Source: https://github.com/DBCDK/morph
- Wiki: https://wiki.nixos.org/wiki/Morph

---

### 5. NixOps4

**Architecture:** Complete rewrite of NixOps in Rust. Resource management with OpenTofu integration.

**Key Features:**
- Resource management (cloud providers, VMs, etc.)
- OpenTofu integration for infrastructure-as-code
- Module system for composable resources
- Stateful deployment (tracks resource state)
- Rust-based (faster than NixOps 2)

**Den Compatibility:** ❌ **Separate system**
- Completely different architecture from Den
- No flake-parts integration
- Resource-oriented, not host-oriented
- Would require significant refactoring to integrate

**nixos-anywhere Integration:** ⚠️ Via providers (can use nixos-anywhere as a provider)

**Maintenance:** In development (2026-06). 881+ stars, active development but pre-release.

**Use Case:** Cloud infrastructure management with resource provisioning. Good for managing AWS/GCP/Azure resources alongside NixOS configs.

**Limitations:**
- Pre-release software (not production-ready)
- Stateful (requires state management)
- Complex setup (OpenTofu + NixOps4)
- No flake-parts integration
- Overkill for simple deployments

**Links:**
- Docs: https://nixops.dev
- Source: https://github.com/nixops4/nixops4

---

### 6. nixos-rebuild

**Architecture:** Built-in NixOS command. Directly uses `nixosConfigurations`.

**Key Features:**
- Built into NixOS (no extra dependencies)
- Direct `nixosConfigurations` support
- Remote deployment via `--target-host`
- Remote building via `--build-host`
- Atomic upgrades (rollback on failure)
- VM testing via `build-vm`

**Den Compatibility:** ✅ **Direct integration**
- Uses `nixosConfigurations` directly (same as Den)
- No extra configuration needed
- Works with Den's `den.hosts` out of the box

**nixos-anywhere Integration:** ✅ Complementary (nixos-anywhere for initial, nixos-rebuild for ongoing)

**Maintenance:** Stable (2026-07). Part of NixOS core.

**Use Case:** Simple deployment for 1-3 hosts. Good for manual deployments or small fleets.

**Limitations:**
- No initial provisioning (only ongoing updates)
- Manual multi-host management (no parallel deployment)
- No secrets management
- No health checks
- No built-in networking/backups
- Doesn't scale well beyond 3-5 hosts

**Links:**
- Wiki: https://wiki.nixos.org/wiki/Nixos-rebuild

---

### 7. nixos-anywhere

**Architecture:** Initial installation tool. Uses disko for disk partitioning.

**Key Features:**
- Initial NixOS installation on remote hosts
- Declarative disk partitioning (via disko)
- SSH-based installation
- Automatic hardware config generation
- Works with cloud providers (Hetzner, DigitalOcean, etc.)
- Unattended installation

**Den Compatibility:** ✅ **Input exists**
- Already in flake inputs
- Complementary to deployment tools (initial install only)
- Works with any deployment tool for ongoing updates

**nixos-anywhere Integration:** ✅ **This is nixos-anywhere**

**Maintenance:** Active (2026-06). 1.2k+ stars, regular updates.

**Use Case:** Initial provisioning of NixOS on remote hosts. Use with a deployment tool (clan/colmena/deploy-rs) for ongoing updates.

**Limitations:**
- Initial install only (not for ongoing updates)
- Requires SSH access to target
- Requires kexec support (or boot from installer)
- No secrets management
- No health checks

**Links:**
- Docs: https://nix-community.github.io/nixos-anywhere
- Source: https://github.com/nix-community/nixos-anywhere

---

### 8. nixos-generators

**Architecture:** Image generation tool. Now upstreamed to nixpkgs (deprecated).

**Key Features:**
- Generate various image formats (ISO, qcow2, AMI, etc.)
- Declarative image configuration
- Supports cloud providers (DigitalOcean, AWS, GCP, etc.)
- VM image generation

**Den Compatibility:** ✅ **Input exists**
- Can be used to generate images for Den-managed hosts
- Complementary to deployment tools

**nixos-anywhere Integration:** ❌ Not integrated (image generation only)

**Maintenance:** Deprecated (2025). Upstreamed to nixpkgs. Use `nixos-rebuild build-image` instead.

**Use Case:** Generate installation images for cloud providers or VMs. Use with nixos-anywhere for initial install.

**Limitations:**
- Deprecated (use `nixos-rebuild build-image`)
- Image generation only (not deployment)
- No ongoing updates

**Links:**
- Source: https://github.com/nix-community/nixos-generators

---

### 9. nixos-infect

**Architecture:** System conversion script. Installs NixOS on non-NixOS hosts.

**Key Features:**
- Convert non-NixOS hosts to NixOS
- Works with 20+ cloud providers
- One-time conversion (not ongoing deployment)
- SSH-based installation

**Den Compatibility:** ❌ **Not applicable**
- One-time conversion tool
- Not for ongoing deployment

**nixos-anywhere Integration:** ❌ Alternative to nixos-anywhere (different approach)

**Maintenance:** Maintenance mode (2025). 1.5k+ stars, but infrequent updates.

**Use Case:** Convert existing non-NixOS hosts to NixOS. Use when nixos-anywhere doesn't work (no kexec support).

**Limitations:**
- One-time conversion only
- Destructive (wipes root filesystem)
- No ongoing deployment
- No secrets management

**Links:**
- Source: https://github.com/elitak/nixos-infect

---

### 10. nixos-in-place

**Architecture:** In-place installation script. Installs NixOS without rebooting.

**Key Features:**
- Install NixOS on top of existing Linux
- No reboot required during installation
- Works with DigitalOcean, Hetzner, etc.
- One-time conversion

**Den Compatibility:** ❌ **Not applicable**
- One-time conversion tool
- Not for ongoing deployment

**nixos-anywhere Integration:** ❌ Alternative to nixos-anywhere (different approach)

**Maintenance:** Abandoned (2015). 500+ stars, but no updates in 10+ years.

**Use Case:** Install NixOS on existing hosts without rebooting. Use when other methods don't work.

**Limitations:**
- Abandoned (no updates since 2015)
- One-time conversion only
- Destructive (wipes root filesystem)
- No ongoing deployment
- No secrets management

**Links:**
- Source: https://github.com/jeaye/nixos-in-place

---

### 11. nixos-shell

**Architecture:** VM testing harness. Spawns lightweight QEMU VMs.

**Key Features:**
- Spawn QEMU VMs from NixOS configs
- Mount host directories into VM
- Console access in terminal
- Cross-architecture support
- Flake integration

**Den Compatibility:** ❌ **Not applicable**
- VM testing tool (not deployment)
- Complementary to deployment tools

**nixos-anywhere Integration:** ❌ Not integrated (testing only)

**Maintenance:** Active (2026). 400+ stars, regular updates.

**Use Case:** Test NixOS configurations in VMs before deploying. Good for CI/CD pipelines.

**Limitations:**
- VM testing only (not deployment)
- No ongoing deployment
- No secrets management

**Links:**
- Source: https://github.com/mic92/nixos-shell

---

### 12. Panix

**Architecture:** Deployment orchestrator (beta). Phase-oriented pipeline: Inspect → Bootstrap → Build → Transfer → Secrets → Activate.

**Key Features:**
- 6-phase pipeline: Inspect → Bootstrap → Build → Transfer → Secrets → Activate
- Real-time TUI (per-machine, per-phase visibility. Press `r` to retry failed phases)
- Handles full lifecycle: bare metal → running NixOS
- Flake-agnostic (uses `panix.yml`, no flake modifications needed)
- Tag-based filtering (`--tags production`)
- Secret management (rsync files with ownership, never in Nix store)
- Scope-aware deduplication (same config → one build)
- Multi-flake deployments (span multiple repos)
- Dry-run modes (`--dry-run`, `--dry-run-with-inspect`)
- Snapshot & replay (capture workflow state to JSON)

**Den Compatibility:** ✅ **Direct — no bridge needed**
- Reads `nixosConfigurations` from flake via `nix build`
- No flake modification required
- Works with any Den-produced nixosConfigurations

**nixos-anywhere Integration:** ✅ Built-in (Bootstrap phase uses disko + nixos-install)

**Maintenance:** Beta (2026-04). 32 stars, single maintainer (mihakrumpestar). Breaking changes expected.

**Use Case:** Full lifecycle management (install + deploy) with real-time TUI. Best for teams that want a single orchestrated pipeline.

**Limitations:**
- Beta quality — breaking changes expected
- Small community (32 stars, single maintainer)
- Requires separate `panix.yml` config file
- Go binary (another dependency)

**Links:**
- Source: https://github.com/mihakrumpestar/panix
- Docs: https://panix.xyz

---

### 13. Bento

**Architecture:** Pull-based deployment tool. Clients poll a central SSH/SFTP server for config updates.

**Key Features:**
- Pull-based model — clients poll a central SFTP server
- Privacy-focused (SSH-authenticated SFTP chroots)
- Robust behind NAT/firewalls (Tor, VPN, I2P support)
- Status reporting (track update state across fleet)
- Timer-based or manual update triggers via systemd service or TCP socket
- Push mode available via `TARGET_IP` env var

**Den Compatibility:** ❌ **Wrong architecture for Den fleets**
- Requires central SFTP server
- Not compatible with push-style deployment workflows
- No flake output integration

**nixos-anywhere Integration:** ❌ Not integrated

**Maintenance:** Stable but low activity (2022-2024). By Solène (rapenne-s). 200+ stars.

**Use Case:** Fleets behind NAT/firewalls where push-based deployment is impossible. Privacy-sensitive deployments.

**Limitations:**
- Pull model adds latency (wait for timer)
- Requires central SSH/SFTP server
- Complex setup (chroot, fleet.nix configuration)
- No initial provisioning
- Push model is an afterthought
- No flake integration

**Links:**
- Source: https://github.com/rapenne-s/bento
- Blog: https://dataswamp.org/~solene/2022-09-04-managing-a-fleet-of-nixos-part3.html

---

### 14. Hercules CI Effects

**Architecture:** CI/CD-integrated deployment system. Deployments run as "effects" after builds succeed.

**Key Features:**
- CI-integrated: deploy on merge, PR, or manual trigger
- Supports all popular tools via effect functions: `runNixOS`, `runNixOps`, `runArion`
- Secrets managed on agent machines (never in CI pipeline)
- Pre-built closures (build in CI, deploy from cache)
- State files API for NixOps state management
- Hermetic environment (like build sandbox, but with network access)

**Den Compatibility:** ✅ **Works with any nixosConfigurations**
- `runNixOS` accepts `self.nixosConfigurations.hostname` directly
- No flake modification needed
- Same as nixos-rebuild under the hood

**nixos-anywhere Integration:** ❌ Not integrated (deployment only)

**Maintenance:** Active (2026). By Hercules CI team.

**Use Case:** Enterprise CI/CD pipelines with automated deployment. Best for teams already using Hercules CI.

**Links:**
- Docs: https://docs.hercules-ci.com/hercules-ci-effects

---

### 15. FlakeHub Deploy (Determinate Systems)

**Architecture:** Commercial deployment platform. Build → push to FlakeHub Cache → `fh apply nixos` on target.

**Key Features:**
- Pre-evaluated closures (no build on target)
- FlakeHub Cache integration
- Terraform integration for AWS/GCP
- IAM role authentication
- SOC 2 compliance
- Commercial product (paid)

**Den Compatibility:** ✅ **Works with any nixosConfigurations**
- `fh apply nixos "flake#nixosConfigurations.hostname"`
- No flake modification needed

**nixos-anywhere Integration:** ❌ Not integrated

**Maintenance:** Active (2026). By Determinate Systems.

**Use Case:** Enterprise deployments with compliance requirements. Best for teams using FlakeHub.

**Links:**
- Docs: https://docs.determinate.systems/flakehub/cli

---

## What Serious Nix Users Use

Research into what major Nix ecosystem players actually use for deployment.

### Determinate Systems (FlakeHub, Determinate Nix)
- **Own tool:** `fh apply nixos` — FlakeHub's deployment command
- **Pattern:** Build closure → push to FlakeHub Cache → `fh apply nixos` pulls + activates
- **Under the hood:** Pre-evaluated closures, SSH-based activation
- **Also:** Terraform integration for AWS

### Numtide (Colmena authors)
- **Colmena** — their own tool, used in production
- **nix-fleet** — newer async/pull-based fleet management (NLnet-funded)
- Dogfood their own tools

### Serokell (deploy-rs authors)
- **deploy-rs** — their own tool
- Multi-profile deployments with magic rollback
- Used by many enterprise Nix users

### Hercules CI
- **Hercules CI Effects** — CI/CD + deployment in one system
- `runNixOS`, `runNixOps` effect functions
- Supports all popular tools as effects

### Zhaofeng Li (Colmena author)
- **Colmena** — dogfoods his own tool

### Mic92 (nixos-anywhere, sops-nix maintainer)
- **Clan contributor** — uses clan for personal infra
- **nixos-anywhere** for provisioning
- **nixos-rebuild** as fallback

### nix-community
- Maintains **colmena**, **nixos-anywhere**, **nixos-generators**
- No single recommended tool — uses what fits

### The common patterns:

| Team/Person | Deploy | Secrets | Provision | Notes |
|-------------|--------|---------|-----------|-------|
| Determinate Systems | `fh apply nixos` | FlakeHub | Terraform | Commercial, compliance-focused |
| Numtide | Colmena | sops-nix | nixos-anywhere | Dogfood their own tool |
| Serokell | deploy-rs | sops-nix | nixos-anywhere | Multi-profile deployments |
| Hercules CI | Hercules CI Effects | Agent secrets | Terraform | CI-integrated enterprise |
| Mic92 | Clan + nixos-rebuild | Clan vars / sops-nix | nixos-anywhere | Maintains many tools |
| General community | nixos-rebuild | sops-nix | nixos-anywhere | Most common combo |

### Key takeaway:
**There is no single consensus tool.** The most common pattern among serious users is **colmena + nixos-anywhere + sops-nix** for production fleets. Some use deploy-rs (Serokell ecosystem). Clan is newer but gaining traction (Mic92, startup-backed). Determinate Systems uses their own commercial tool. Everyone falls back to `nixos-rebuild --target-host`.

---

## Den Compatibility Analysis

### Best Integration: Clan.lol

**Why Clan is best for Den:**
1. **Native flake-parts module** — Same architectural layer as Den's dendritic modules
2. **Shares `nixosConfigurations`** — Den's `manySubmodule` type merges both cleanly
3. **No collision** — Can coexist with `den.hosts` without conflicts
4. **Comprehensive** — Handles initial install + ongoing updates + secrets + networking + backups
5. **Active development** — Regular updates, active community

**Integration paths:**
- **Path A (recommended):** Import clan as flakeModule, keep Den owning hosts, use clan for deployment/CLI only
- **Path B:** Override Den's `instantiate` per-host to use `clan-core.lib.clan`
- **Path C:** Full migration to `clan.machines` (requires moving host definitions)

### Good Integration: Colmena, deploy-rs

**Why they work:**
- Can be added alongside Den without conflicts
- Use separate outputs (`colmenaHive`, `deploy`)
- Require manual wiring but don't collide

**Limitations:**
- Separate output namespaces (not as clean as clan)
- No built-in secrets/networking/backups
- Less integrated with Den's architecture

### Poor Integration: Morph, NixOps4

**Why they don't work well:**
- Morph uses separate `network.nix` (not in flake)
- NixOps4 is a completely different system (resource-oriented)
- No flake-parts integration
- Would require significant refactoring

### Direct Integration: nixos-rebuild

**Why it works:**
- Uses `nixosConfigurations` directly (same as Den)
- No extra configuration needed
- Works out of the box

**Limitations:**
- Doesn't scale beyond 3-5 hosts
- No fleet management features

---

## Recommendations

### For Your 8-Host Fleet

**Recommended: Clan.lol (Path A)**

**Why:**
- Best Den integration (native flake-parts module)
- Handles both initial install and ongoing updates
- Built-in secrets management (sops backend)
- Fleet orchestration (inventory, services, networking)
- Active development, good documentation

**Implementation:**
1. Add `clan-core` to flake inputs
2. Import `clan-core.flakeModules.default` in `modules/defaults/inputs.nix`
3. Set `clan.meta.name` and `clan.meta.domain`
4. Add `clan.core.networking.targetHost` to each host
5. Use `clan machines install` for initial provisioning
6. Use `clan machines update` for ongoing updates

**Alternative: Colmena**

**Why:**
- Simpler than clan (less abstraction)
- Good for 4+ hosts
- Stateless deployment

**When to use:**
- You don't need secrets management
- You don't need fleet orchestration
- You prefer simpler tooling

**Implementation:**
1. Add `colmena` to flake inputs
2. Add `colmenaHive` output (or use `colmena-flake` bridge)
3. Define hosts in `colmenaHive`
4. Use `colmena apply` for deployment

### For Initial Provisioning

**Use: nixos-anywhere (already in inputs)**

**Why:**
- Declarative disk partitioning (via disko)
- SSH-based installation
- Works with cloud providers
- Complements any deployment tool

**Implementation:**
1. Configure disko in host config
2. Run `nixos-anywhere --flake .#hostname --target-host root@host`
3. Use deployment tool (clan/colmena) for ongoing updates

### For Small Fleets (1-3 hosts)

**Use: nixos-rebuild**

**Why:**
- Built into NixOS
- No extra dependencies
- Direct `nixosConfigurations` support

**Implementation:**
1. Configure hosts in `den.hosts`
2. Run `nixos-rebuild switch --flake .#hostname --target-host root@host`

---

## Migration Path

### Current State
- Den framework with 8 hosts
- nixos-anywhere in inputs (for initial install)
- No deployment tool for ongoing updates
- Manual `nh os switch` or `nixos-rebuild`

### Target State
- Den framework with 8 hosts
- Clan.lol for deployment (Path A)
- nixos-anywhere for initial provisioning
- Clan secrets/vars for API keys
- Clan services for networking/backups

### Steps
1. Add `clan-core` to flake inputs
2. Import `clan-core.flakeModules.default`
3. Set `clan.meta.name` and `clan.meta.domain`
4. Add `clan.core.networking.targetHost` to each host
5. Test with one host: `clan machines update hostname`
6. Migrate remaining hosts
7. Add clan services (wireguard, borgbackup, etc.)
8. Migrate secrets to clan.vars

---

## References

- Clan docs: https://docs.clan.lol
- Colmena docs: https://colmena.cli.rs
- deploy-rs: https://github.com/serokell/deploy-rs
- Morph: https://github.com/DBCDK/morph
- NixOps4: https://nixops.dev
- nixos-anywhere: https://nix-community.github.io/nixos-anywhere
- nixos-rebuild: https://wiki.nixos.org/wiki/Nixos-rebuild
- Den docs: https://den.denful.dev
