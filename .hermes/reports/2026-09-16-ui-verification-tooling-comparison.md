# UI-verification tooling — comparison for Achiyon

Scope: research-only, grounded in `/Storage/Git/achiyon/web` and the host
machine (`erebus`, NixOS 26.11, nixpkgs 25.05 via flake). Repo is a
SvelteKit 2 + Svelte 5 + Tailwind 4 SPA (adapter-static), shadcn-svelte
registry, served as Tauri assets.

## 1. Local inventory (read-only)

### Repo (`/Storage/Git/achiyon/web`)

- `package.json` (current state):
  - `svelte ^5.0.0`, `@sveltejs/kit ^2.20.0`, `@sveltejs/vite-plugin-svelte ^5.0.0`, `vite ^6.0.0`
  - `vitest ^5.0.0` + `@vitest/coverage-v8 ^5.0.0`
  - **`@playwright/test ^1.63.0`** — already declared, NOT yet wired (no `playwright.config.*` in repo)
  - `jsdom ^30.0.1` + `@testing-library/svelte ^5.4.2` + `@testing-library/jest-dom ^7.0.1` (the current test stack)
  - `tailwindcss ^4.3.3`, `bits-ui ^2.19.0`, `lucide-svelte`, `marked`, `dompurify`
  - scripts: only `dev / build / preview / test / test:watch` — no `test:e2e`, no `storybook`, no `backstop`
- `vitest.config.js`: jsdom env, `svelteTesting()` plugin (auto-DOM-cleanup), test-setup imports `@testing-library/jest-dom/vitest`. No browser mode enabled.
- `vite.config.js`: tailwind + sveltekit + `/api` proxy to `127.0.0.1:7412`.
- `svelte.config.js`: `adapter-static` with SPA fallback (`index.html`).
- `src/routes/`: just `+layout.svelte`, `+page.svelte`, `chat/+page.{svelte,js}`. One component (`sigil.js`) and one existing test (`sigil.test.js`).
- `node_modules`:
  - `@playwright/test@1.63.0` and `playwright-core@1.63.0` are installed (npm-resolved; browsers NOT downloaded — `node_modules/playwright/.local-browsers` absent).

### Host machine

- `/run/current-system/sw/bin` has **no chromium / chrome / google-chrome / playwright / puppeteer** binaries.
- `which chromium chromium-browser google-chrome chrome` → all missing.
- `nix eval ...#playwright-driver.version` (and `chromium`, `playwright`, `google-chrome` against nixos-25.05) → all returned `"nope"` because flake-input evaluation is unavailable in this non-flake eval path; the **availability is confirmed by the wiki.nixos.org/wiki/Playwright docs** (`pkgs.playwright-driver`, `pkgs.playwright-driver.browsers`, `pkgs.chromium` exist; the friction is the version-pinning dance below).
- `docker` not on PATH → no Docker-based daemon options (BackstopJS Docker container, act-runner in Docker, etc.) on this host. CI runner on Serenity is bare-nix (`runs-on: nix`).
- `.forgejo/workflows/ci.yml` has only `server` (Rust) and `web` (`npm ci` + `npm run test`) jobs. No e2e, no visual regression. CI runs inside `nix develop`, so anything new must work in that shell.

### What the agent already has

- Browser automation via `browser_navigate / browser_click / browser_snapshot / browser_vision / browser_console` (Camofox default; CDP escape hatch via `browser_cdp`).
- A11y-tree snapshots + vision (model-attached) screenshots.
- Background process / dev-server management.
- Vitest 5 + testing-library/svelte (jsdom).
- `compose-ui-screenshot-testing` skill for Android Compose (not web).

## 2. Candidate comparison

| Tool | Install cost (NixOS) | Maintenance cost | What it catches the existing loop does NOT | Verdict |
|---|---|---|---|---|
| **`@playwright/test` (already in deps)** | Add to `web/devShells/default.nix`: `playwright-driver.browsers` + `PLAYWRIGHT_BROWSERS_PATH` + `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS`. **Version-pin dance is required** — nixpkgs-25.05 ships playwright 1.61.x; repo wants 1.63. Either bump npm to 1.61 or pull a newer nixpkgs pin. | Low once pinned. `playwright.config.ts` + 1 CI step. | (a) **Deterministic selectors + accessibility-tree refs** (no flake from vision misreads). (b) **CI-gated regression** — the loop can't tell you "you broke last commit." (c) **Network/console capture with assertions** (`page.on('console')`, route mocking). (d) **Trace + screenshot artifacts** committed on failure. (e) Built-in `toHaveScreenshot()` for pixel diffs without a 3rd tool. | **KEEP — wire it.** Already a dep, friction is known and solvable. |
| **`@playwright/mcp` (microsoft/playwright-mcp)** | `npx @playwright/mcp@latest` — but browsers will 404 the same way npm playwright would (need same env vars + nixpkgs browser bundle). | Medium — extra daemon process; `--port` HTTP transport to detach from agent cgroup is safer than stdio. | Same as playwright test (a/b/c), but with MCP-tool affordances and `--caps=network,vision,pdf` opt-ins. Adds cross-browser (Firefox/WebKit) if ever needed. | **SKIP for now.** Hermes already has browser tools that wrap CDP/Camofox; adding MCP duplicates that surface area without new capability. Revisit if the agent needs cross-browser E2E. |
| **`chrome-devtools-mcp` (Google)** | `npx @playwright/mcp` analog: `npx chrome-devtools-mcp@latest` (or google-chrome from nixpkgs for `chromePath`). Requires a `google-chrome` binary — `pkgs.google-chrome` exists in nixpkgs. | Medium — another daemon; Chrome-only. | **(d) above AND** Lighthouse audits (a11y/SEO), performance traces with Core Web Vitals (LCP/INP/CLS), V8 heap snapshots, CPU/network emulation — none of which the agent's loop can produce today. | **SKIP unless perf work starts.** Pure diagnostic tool; Achiyon is a literary SPA with no perf SLOs documented in `DESIGN.md`. Zero current payoff. |
| **BackstopJS 6.3** | `npm i -D backstopjs`. Browsers via its built-in Puppeteer driver — **same NixOS dynamic-linker trap** unless you point it at nixpkgs chromium. Last release Sep 2024 → dormant. | High — JSON scenarios, no PR gating, manual `backstop approve`, baseline storage you own. | Pure pixel diff only; no a11y/aria snapshot diff. | **SKIP.** Dormant + Chrome-only + JSON config grows into a maintenance surface. |
| **Lost Pixel** | Same NixOS issues as Playwright (it's Playwright-based). | n/a — **archived 22 Apr 2026**, team joined Figma, no migration path. | Was component-level diff (Storybook/Ladle/Histoire native). | **SKIP.** Dead upstream. |
| **reg-suit / reg-CLI** | `npm i -D reg-suit` + S3/GCS bucket for baselines. MIT, framework-agnostic. | Medium — bring-your-own screenshots, plugin assembly. | Pixel diff + PR comment via GitHub. Adds **deterministic, git-gated visual regression** if you already have a Playwright that takes screenshots. | **SKIP as primary; consider as backend if** `toHaveScreenshot()` proves too noisy. |
| **Storybook (10.x) + Svelte CSF addon v5** | `@storybook/svelte-vite` + `@storybook/addon-svelte-csf@^5` + Svelte ≥ 5, Vite ≥ 5. Webpack Svelte storybook dropped in 9.0. Heavier (~50 MB node_modules). | High — addon matrix, MDX docs, Chromatic optional SaaS. | **Component isolation** (the loop only sees full pages), autodocs, controls, addon-a11y, addon-actions, visual regression via addon-chromatic. Svelte 5 caveats: traditional `on:` event handlers are not auto-wired; argTypes inference partially missing. | **SKIP.** Big lift for a repo with ~6 components, mostly inline in routes. No design system to gallery. |
| **Ladle** | `npm i -D @ladle/react` — **React-only**. Maintainer publicly said "not planning to support Svelte" in issue #360. | n/a | None for this repo. | **SKIP — React-only, no Svelte support.** |
| **Histoire v1.0.0-beta.1** | `@histoire/plugin-svelte@1.0.0-beta.1` (peer: `svelte ^4 || ^5`, `histoire ^1.0.0-beta.1`). Vite 8 required by latest plugin. | Medium — still beta, smaller community (~3.5k★), `@histoire/plugin-screenshot` does simple visual diff. | Same as Storybook for Svelte 5, lighter footprint, native Svelte story format (no CSF). | **SKIP — beta + 6 components is over-tooled.** |
| **Vitest Browser Mode (`@vitest/browser-playwright` + `vitest-browser-svelte`)** | `npm i -D @vitest/browser-playwright vitest-browser-svelte` + same NixOS browser env as playwright-test. Requires Vitest 4 — repo has `vitest ^5.0.0` (likely fine since V5 may superset). | Low — same runner, just provider swap. | **(a)** real-browser DOM for tests that need layout/focus/`IntersectionObserver` (the existing `compose-ui-screenshot-testing` skill is the Android analog). Locators auto-retry, fewer `flushSync` calls. Built-in visual regression in Vitest 4 (`expect(locator).toMatchScreenshot()`). | **CONSIDER** as second add — extends the existing jsdom stack, not a new tool. |

## 3. What the existing loop MISSES, mapped to candidates

| Gap in current loop | Closest fix in this list |
|---|---|
| Vision-based "looks right?" is **non-deterministic** and burns tokens per screenshot | Playwright accessibility-tree selectors + `toHaveScreenshot()` |
| No **CI gate** — agent can ship a regression | Add `web` job → `playwright test` in `.forgejo/workflows/ci.yml` |
| No **trace artifacts** when something breaks | Playwright traces + Vitest 4 trace integration |
| Can't catch **a11y regressions** programmatically | Storybook addon-a11y OR chrome-devtools-mcp Lighthouse — both heavy; cheap path = `axe-core/playwright` later |
| Can't catch **performance regressions** | chrome-devtools-mcp `performance_start_trace` — only if perf becomes a stated SLO |
| Component isolation (loop sees full pages, can't pin to one component in isolation) | Storybook / Histoire / Ladle — only worth it once there are >10 components |

## 4. Recommendations — minimal set (≤ 3 additions)

The repo has 6 components, 2 routes, no design-system gallery, no perf SLOs,
and CI is bare-nix on Serenity. Bias = **zero-daemon + low-flake + uses
what's already in `package.json`**.

### Add #1 — **wire `@playwright/test` + a smoke spec** (mandatory)

- `web/playwright.config.ts`: `projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], launchOptions: { executablePath: process.env.PLAYWRIGHT_LAUNCH_OPTIONS_EXECUTABLE_PATH } } }]`. `webServer: 'npm run dev'` (already proxies to API on `:7412`).
- Add `web/tests/smoke.spec.ts`: navigate `/`, navigate `/chat`, click a sigil, assert a11y role presence.
- Nix side: in the `web` devShell, add `pkgs.playwright-driver.browsers` and export `PLAYWRIGHT_BROWSERS_PATH`, `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS`, `PLAYWRIGHT_LAUNCH_OPTIONS_EXECUTABLE_PATH` (per the NixOS wiki recipe). **Version-pin**: nixpkgs-25.05 has playwright 1.61.x; `package.json` has 1.63.0. Either pin npm to `~1.61` or override the nixpkgs input — pick one, never let them drift.
- CI: one extra step in `.forgejo/workflows/ci.yml`'s `web` job: `nix develop -c sh -c 'cd web && npx playwright install-deps || true; npx playwright test'`. Cache `~/.cache/ms-playwright` like the existing `~/.npm` cache.

Catches the agent's loop misses: deterministic selectors, CI-gated regressions,
trace artifacts, console capture, network mocking — and unlocks everything else.

### Add #2 — **`vitest-browser-svelte` for one or two component tests** (cheap)

- `npm i -D @vitest/browser-playwright vitest-browser-svelte` (Vitest 5 is already installed; confirm 4+ provider support first).
- Add one `*.browser.test.js` file that mounts a Svelte 5 component in a real browser and asserts a layout-dependent property the jsdom tests can't catch.
- Reuse the same Nix browser env as #1.

Why: this extends the existing vitest stack instead of introducing a parallel runner. Two-test pilot before going wider.

### Add #3 — **`expect(locator).toMatchScreenshot()` from Vitest 4** (or fall back to `toHaveScreenshot()` from Playwright)

- Built into the tools from #1 and #2 — zero new deps.
- Pin baselines in-repo; first run creates them, subsequent runs gate.
- Keep threshold tight (~0.2%) and use `mask` for the FNV-1a sigil (it's deterministic per-identity, but the random avatars change between identities — masks avoid false positives on the same component).

Skip Storybook/Histoire/Ladle — wrong scale. Skip BackstopJS/Lost Pixel — dead/dormant. Skip chrome-devtools-mcp and playwright-mcp — the agent already has CDP-level browser control; MCP duplicates it without buying a CI gate.

## Friction notes for NixOS + Forgejo CI

1. **Version-pinning is the single biggest foot-gun** on NixOS. `npx playwright install` will silently download the wrong chromium and break with `could not start dynamically linked executable`. Always: `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` + `PLAYWRIGHT_BROWSERS_PATH` pointing into `/nix/store`.
2. **`PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1`** is mandatory on NixOS even with the nixpkgs browser bundle.
3. **CI cache**: cache `~/.cache/ms-playwright` keyed on the playwright npm version. Without it, every cold CI run re-downloads ~150 MB.
4. **Browser binary in `executablePath`**: nixpkgs chromium is a wrapped script, not a binary — Playwright's default resolution will not find it. Set `launchOptions.executablePath` explicitly (see wiki recipe).
5. **API dependency**: `vite.config.js` proxies `/api` to `127.0.0.1:7412` (the Rust server). E2E tests need that server up or mocked. Add `webServer` config or stub `/api` in the test setup.
6. **No Docker on erebus + no `act`**: cannot reproduce Forgejo CI locally without pushing. Treat CI logs as ground truth; pre-deploy checks here are vitest + dry-build only.
