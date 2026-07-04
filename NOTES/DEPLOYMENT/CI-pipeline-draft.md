# CI Pipeline Draft

## Two approaches

### Option A: GitHub Actions + Cachix (free, simple)

```yaml
# .github/workflows/build.yaml
name: Build all hosts
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "0 6 * * *"  # daily rebuild

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cachix/install-nix-action@v30
        with:
          nix_path: nixpkgs=channel:nixos-unstable
      - uses: cachix/cachix-action@v15
        with:
          name: spectacle
          authToken: "${{ secrets.CACHIX_AUTH_TOKEN }}"

      - name: Build all NixOS configurations
        run: |
          nix build .#nixosConfigurations.traversal.config.system.build.toplevel
          nix build .#nixosConfigurations.spectacle.config.system.build.toplevel
          nix build .#nixosConfigurations.serenity.config.system.build.toplevel
          # ... all hosts
```

**Result:** All closures pre-built and cached. Each host's `nixos-rebuild switch` pulls from cache — seconds, not hours.

### Option B: Determinate Systems stack (if using FlakeHub)

```yaml
# .github/workflows/build.yaml
name: Build all hosts
on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: DeterminateSystems/determinate-nix-action@v3
      - uses: DeterminateSystems/flakehub-cache-action@main

      - name: Build all configurations
        run: |
          nix build .#nixosConfigurations.traversal.config.system.build.toplevel
          nix build .#nixosConfigurations.spectacle.config.system.build.toplevel
          nix build .#nixosConfigurations.serenity.config.system.build.toplevel
          # ... all hosts
```

(Determinate input already exists in flake — this would use that.)

### Host configuration change

Each host needs to trust the cache:

```nix
# In nix aspect (modules/aspects/core/nix.nix)
nix.settings.extra-substituters = [
  "https://nix-community.cachix.org"
  "https://spectacle.cachix.org"  # <-- add this
];
nix.settings.trusted-public-keys = [
  "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
  "spectacle.cachix.org-1:..."  # <-- from Cachix dashboard
];
```

### Deploy workflow (manual or CI)

**Manual (recommended to start):**
```bash
# Closures already in cache from CI
nixos-rebuild switch --flake .#vps --target-host root@vps
# Pulls from cache → near-instant
```

**Automated (future):**
```yaml
# .github/workflows/deploy.yaml
on:
  workflow_run:
    workflows: ["Build all hosts"]
    types: [completed]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to VPS
        run: |
          nixos-rebuild switch --flake .#vps \
            --target-host root@vps \
            --build-host localhost
```

### Build modes

| Mode | Build location | Deploy | Use when |
|------|---------------|--------|----------|
| **CI build + cache** | GitHub Actions | Host pulls from cache | Production (fastest) |
| **Local build** | traversal | `--target-host vps` | Testing, VPN offline |
| **Remote build** | VPS itself | `--build-host vps` | VPS has more RAM/cores |

All three work with `nixos-rebuild`. No deploy tool needed.

### What you'd need to set up:

**Cachix approach:**
1. Create account at cachix.org
2. Create cache named `spectacle`
3. Add `CACHIX_AUTH_TOKEN` to GitHub secrets
4. Add cache to host config as substituter
5. Create `.github/workflows/build.yaml`

**FlakeHub approach:**
1. FlakeHub account (already has `determinate` input)
2. FlakeHub Cache is auto-enabled
3. Create `.github/workflows/build.yaml`

---

## Bottom line

CI pipeline = GitHub Actions + binary cache. The build happens in CI, closures go to cache, hosts pull from cache on deploy. No deploy tool, no framework, no agent. Just Nix's built-in substituter mechanism.
