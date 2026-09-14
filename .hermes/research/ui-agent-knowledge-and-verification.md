# How the best AI-coding setups give agents UI knowledge and verification

Research compiled for a Claude-class coding agent that builds Svelte/SvelteKit + Tailwind v4 UIs on NixOS. Every claim has at least one URL. Recommendations are ranked by impact-for-effort at the end of each section.

---

## 1. Spec formats agents consume well

### 1.1 W3C DTCG — the canonical design-token format

- The W3C Design Tokens Community Group Format Module (a.k.a. DTCG, formerly `design-tokens.format`) is the cross-tool standard: typed tokens (`color`, `dimension`, `fontFamily`, `duration`, `cubicBezier`, etc.), JSON-based, with `{group.token}` references and `$value` / `$type` / `$description` keys. Reference spec: <https://www.designtokens.org/tr/2025.10/format/> and <https://tr.designtokens.org/format/>.
- Tokens are **machine-checkable** and decoupled from any one UI framework — that's their superpower for agents. A token file is the only "design system" representation an agent can both *read* (semantic intent) and *validate against* (lint).
- Style Dictionary and Token Studio are the most-used engines that consume DTCG and emit Tailwind v3 config, CSS variables, iOS/Android/Compose outputs. <https://styledictionary.com/>, <https://tokens.studio/>.

### 1.2 DESIGN.md (Google Stitch, open-sourced)

- A two-layer format: YAML front-matter with typed tokens (`colors`, `typography`, `rounded`, `spacing`, `components`) + Markdown body with prose rationale (sections must appear in canonical order: Overview → Colors → Typography → Layout → Elevation → Shapes → Components → Do's and Don'ts). Spec + linter + token export commands (`--format css-tailwind` for Tailwind v4 `@theme`, `--format dtcg` for W3C JSON). Repo: <https://github.com/google-labs-code/design.md>; blog post: <https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-design-md/>.
- Why it matters for agents: tokens are *normative* values; prose explains intent ("accent applies to primary button backgrounds, focus rings, link hover color — nowhere else"). The linter ships 9 rules including `contrast-ratio` (WCAG AA), `broken-ref`, `orphaned-tokens`, `section-order`. So a single file gives an agent (a) values, (b) constraints, (c) a self-check it can run.
- Tailwind v4 export is first-class: `npx @google/design.md export --format css-tailwind DESIGN.md` emits a `@theme { … }` block with the right `--color-*`, `--font-*`, `--text-*`, `--leading-*`, `--tracking-*`, `--font-weight-*`, `--radius-*`, `--spacing-*` namespaces. That's exactly the format Tailwind v4 reads from CSS — no `tailwind.config.js` needed.

### 1.3 Cursor rules (`.cursorrules` and `.cursor/rules/*.mdc`)

- Cursor reads `.cursor/rules/*.mdc` (deprecated monolithic `.cursorrules` still works). Each `.mdc` file has YAML frontmatter: `globs`, `excludeGlobs`, `description`, `alwaysApply`. Four application modes: Always, Intelligently (description-matched), Specific files (glob), Manual (`@mention`). Docs: <https://cursor.com/docs/rules>.
- For design systems, the practice is to put visual tokens + behavioral rules into a `design.mdc` with `globs: src/**/*.svelte, src/**/*.css` — every UI file in scope gets the rules. Example patterns: <https://www.matchkit.io/blog/cursor-design-system-setup>.
- Production-grade pattern (SeedFlip): **specific values, never vague adjectives**. Hex codes for every color, font names as in Google Fonts, exact px radii, behavioral rules ("Accent applies to: primary button backgrounds, active nav states, focus rings, link hover color. Nowhere else."). Tell the agent *what not to do* — "NEVER use Tailwind color utilities (bg-blue-500). Use CSS variables." Source: <https://seedflip.co/blog/cursor-rules-design-system> and <https://seedflip.co/blog/cursorrules-design-output>.

### 1.4 AGENTS.md / CLAUDE.md

- Plain Markdown at repo root, read by Claude Code, Cursor, Codex, Windsurf, Amp, Lovable (and GitHub Copilot's `.github/copilot-instructions.md`). No frontmatter, no extension requirement.
- Best used for **process rules** (build commands, file layout, "don't touch generated files", what to do when a check fails) — not for visual design tokens, which belong in a machine-readable token file.
- Lovable explicitly says root-level `AGENTS.md` is read on every conversation regardless of session length: <https://docs.lovable.dev/features/knowledge>.

### 1.5 shadcn `registry.json` — the "golden component" format for agents

- A typed JSON catalog (`registry-item.json`): `name`, `title`, `description`, `type` (one of `registry:ui | :block | :component | :hook | :page | :file | :theme | :style | :item | :base | :font`), `files` with paths, `dependencies`, `registryDependencies`, `tailwind`, `cssVars`, `meta`, `categories`. Schema lives in the shadcn repo: <https://github.com/shadcn-ui/ui/blob/main/packages/shadcn/src/registry/schema.ts>. Docs: <https://ui.shadcn.com/docs/registry/getting-started>, <https://ui.shadcn.com/docs/registry/registry-json>.
- Namespaces (`@acme/button`) let agents pull from multiple registries: `shadcn add @v0/chart`. Resources are validated against the Zod schema before installation — JSON-parsed, no code executed. Source: <https://ui.shadcn.com/docs/registry/namespace>.
- This is the closest thing to a portable "AI-installable component contract" — every registry item ships a description field that agents consume, and `meta` / `categories` give agents semantic metadata.

### 1.6 v0 — system prompt for UI generation

- v0's outputs are shadcn/ui components built on **Radix UI primitives**, which carry Radix's accessibility contracts (correct ARIA, focus management, keyboard handling) by default. So v0 solves the "div soup" problem architecturally rather than by prompt. Background: <https://master.dev/blog/ai-generated-ui-is-inaccessible-by-default/>.

### 1.7 Lovable — Knowledge + Design Systems

- Two-tier knowledge model: **Workspace Knowledge** (shared across projects in a workspace, ≤10,000 chars, always-in-context) and **Project Knowledge** (≤10,000 chars, always-in-context, project-specific). Skills load on demand. Docs: <https://docs.lovable.dev/features/knowledge>.
- **Design Systems** feature: a dedicated project holds components + a generated `.lovable/` folder:
  - `design-system.json` — canonical schema (tokens, component catalog with variants/props/examples, stack constraints).
  - `rules/components.md` — component catalog (rendered).
  - `rules/design-tokens.md` — token reference (rendered).
  - `rules/library-guidelines.md` — stack rules (rendered).
  - `system.md` — hand-authored design philosophy, preserved across releases.
  - Lovable reads these on every generation in any connected project. Source: <https://docs.lovable.dev/features/design-systems>.
- Lovable's prompting playbook explicitly tells the agent to *plan before prompting* (4 questions: product/audience/value/key action), **map the user journey**, build by component (not full page), use real content (no "Feature 1"), use buzzword vocabulary ("minimal", "cinematic", "editorial") to dial aesthetic, and treat design language as a *foundation* — not polish. Source: <https://docs.lovable.dev/prompting/prompting-one>.

### 1.8 Bolt.new — system prompt and prompting playbook

- Bolt runs in a WebContainer (browser-side Node runtime), so prompts must include stack and runtime constraints ("Runs in Bolt's WebContainer; prefer pure-JS dependencies and avoid anything that needs native binaries"). Source: <https://bolt.new/blog/prompting-guide>.
- The single highest-leverage rule: **describe the job, not the app**. "I need to know which customers owe me money" beats "build me a CRM" — the first lets the agent pick the shortest path; the second drags in 95 unwanted features.
- "Clustered prompting": bundle the details of one workflow into a single prompt instead of drip-feeding across five. Each prompt pays a re-read tax; one big prompt reads the project once.
- "Enhance prompt" feature in the chatbox lets the user answer clarifying questions before generation — an in-product forcing function for the "plan before prompting" pattern.

### 1.9 Claude Artifacts — system prompt for one-shot UI

- The leaked Claude Artifacts system prompt reveals the constraints baked into Anthropic's own UI generation: *"Use Tailwind classes for styling. DO NOT USE ARBITRARY VALUES (e.g. h-[600px])."* So even Anthropic tells the model to use Tailwind's scale instead of invented pixel values. Available libraries are enumerated: `react`, `lucide-react@0.263.1`, `recharts`, `shadcn/ui` (after import — model must offer to help install). Source: <https://github.com/jujumilk3/leaked-system-prompts/blob/main/claude-artifacts_20240620.md> and <https://zerotwo.ai/prompts/system-prompts/anthropic/claude-artifacts>.
- Artifacts are React components with no required props (or defaults for all) — they are *standalone*. The prompt forbids `// rest of the code remains the same…` truncation. Always emits full source.

### 1.10 Component inventory and "golden examples"

- Storybook is the canonical component gallery for humans *and* agents. Storybook 10 ships an MCP server at `http://localhost:6006/mcp` that exposes `docs-list`, `docs-show`, `get-storybook-story-instructions`, `test-run`. The Storybook system prompt for agents includes the rule: *"Never hallucinate component properties — always use the MCP tools to check if a property is documented."* Source: <https://storybook.js.org/docs/ai>, <https://storybook.js.org/docs/ai/best-practices.md>.
- Storybook generates machine-readable manifests (JSON) of every component, story, doc, and MDX page. JSDoc on component exports and `Meta` summaries on MDX pages become agent context. `react-docgen-typescript` is the recommended prop extractor (richer than default `react-docgen`).
- For Svelte/Vue: Histoire is the Vite-native Storybook-equivalent with first-class Svelte support. <https://github.com/histoire-dev/histoire>. For React-only speed: Ladle. <https://github.com/tajo/ladle>.
- Chromatic (made by Storybook team) turns every story into a visual test automatically. Cross-browser, cross-viewport, cross-theme modes. <https://www.chromatic.com/storybook>.

### 1.11 llms.txt — the docs-for-LLMs convention

- Proposed by Jeremy Howard (Answer.AI), Sep 2024. Spec: <https://llmstxt.org/> and <https://github.com/AnswerDotAI/llms-txt>. File lives at `/llms.txt` (or scoped subpath). Required: H1 with project name. Optional: blockquote summary, H2 sections of Markdown links. Links follow `[Name](absolute-url): short description.` Optional section has special meaning — its links may be skipped for short context.
- Companion file `/llms-full.txt` is the same links but with full text concatenated — for tools that fetch consolidated context. Tools exist to expand it: `llms_txt2ctx` (Python/CLI), `vitepress-plugin-llms`, `docusaurus-plugin-llms`.
- **Svelte** ships a complete set: `/llms.txt`, `/llms-full.txt`, `/llms-medium.txt`, `/llms-small.txt`, plus package-level `/docs/svelte/llms.txt`, `/docs/kit/llms.txt`, `/docs/cli/llms.txt`. Source: <https://svelte.dev/docs/llms> and <https://learn.svelte.dev/docs/llms>.
- **Tailwind v4 does not ship llms.txt**. Adam Wathan publicly refused (May 2026 thread on tailwindlabs/tailwindcss.com PR #2388), citing the 40% drop in docs traffic since early 2023 and the layoff of 75% of his team — adding an `llms.txt` would accelerate the trend. Practical workarounds: fetch via `https://context7.com/websites/tailwindcss`, use Lombiq's `Tailwind-Agent-Skills` (snapshot only after explicit license accept), or scrape MDX via `prompt-tower`. Source: <https://github.com/tailwindlabs/tailwindcss.com/pull/2388>, <https://github.com/tailwindlabs/tailwindcss/discussions/18256>, <https://github.com/tailwindlabs/tailwindcss/discussions/14677>.
- DaisyUI (Tailwind plugin) does publish `/llms.txt`. Next.js, Better-Auth, Zod, MCP project all do.
- **For agent workflows**: cache `llms.txt` locally on first request, fetch individual pages on demand by URL. Do *not* load `llms-full.txt` into the system prompt — it bloats context and the agent rarely needs everything at once.

### 1.12 Impact-for-effort ranking (Section 1)

1. **DESIGN.md** in the repo root + `npx @google/design.md export --format css-tailwind` to emit Tailwind v4 `@theme`. Combines tokens + prose + linter in one file. Highest leverage.
2. **Cursor/Claude rules** for process rules (build, file layout, "don't touch generated", what to do when a check fails) — keep separate from visual tokens.
3. **shadcn `registry.json`** if you're building a component library other agents (or `shadcn add`) will consume.
4. **Storybook MCP server** if you have a real component library — agents stop hallucinating props.
5. **Svelte llms-full.txt** as a cached local context file when working with SvelteKit.
6. Tailwind v4 llms.txt is *not* available officially — use `context7.com/websites/tailwindcss` or a curated agent skill (Lombiq).

---

## 2. Verification loops

### 2.1 Screenshot-driven development (SDD)

- The pattern (Yureki's harness, Aug 2026): agent renders → screenshots → reads image → reports what it sees → iterates. The loop *closes* on visual failure modes that DOM assertions can't see: a button 400px off-screen, a flex row that became a column, a modal stacked behind the page. Source: <https://dev.to/yureki_lab/how-i-gave-my-ai-coding-agent-eyes-a-screenshot-feedback-loop-for-ui-work-jce>.
- Three required pieces: (a) render harness that boots the app and captures at multiple viewports, (b) structured report with console errors + failed network requests + layout metrics, (c) prompt contract that **forbids the agent from claiming completion without a capture**.
- Coder000's "Screenshot Loop" (Sep 2026): same pattern, with three viewports per surface (375 phone, 768 tablet, 1280 board), seed real state ("the shots have life in them"), login as a real user for protected pages. <https://www.coder000.com/post/screenshot-loop-ai-design>.
- ProofShot (Sep 2026): bundles screenshots + video + console + dev-server logs + PR-comment upload. <https://github.com/AmElmo/proofshot>.
- `one-shot-ui`: deterministic pixel + structural diffing — extracts tokens from a reference screenshot, diffs the implementation, returns concrete CSS fixes (`width: 616px`, `gap: 176px`) instead of "make it look more like this". <https://github.com/tn0123/one-shot-ui>.
- **Where SDD breaks**: tasks that aren't visual (data shape correctness, edge cases in business logic), and tasks where the agent *agrees with itself* across rounds. The Yureki article flags this honestly.

### 2.2 Playwright MCP — accessibility-snapshot-based agentic browser

- `npx @playwright/mcp@latest` — Microsoft-maintained MCP server. Operates on the **accessibility tree, not pixels**: every interactive element gets a stable ref like `e5`, the LLM calls `browser_click e5` deterministically. ~200–400 tokens per snapshot vs thousands for a DOM/screenshot. Works with VS Code, Cursor, Windsurf, Claude Code, Claude Desktop. Source: <https://playwright.dev/mcp/introduction>, <https://playwright.dev/docs/getting-started-mcp>, <https://github.com/microsoft/playwright-mcp>.
- Tools: `browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`, `browser_take_screenshot`, `browser_evaluate`, `browser_run_code_unsafe` (RCE-equivalent — only enable for trusted clients), network mocking, tab management.
- Microsoft now ships a parallel `playwright-cli` (CLI + SKILLs) — preferred over MCP for high-throughput coding agents because CLI invocations are more token-efficient (no big tool schemas loaded). MCP wins for exploratory/self-healing loops where persistent browser context outweighs token cost.
- **Responsive testing pattern**: Playwright supports `page.setViewportSize`, the context-level `viewport`, and `playwright.devices` (for user agent + DPR + touch). Use a Playwright **project per device class** so widths live in config and tests stay focused on behavior. Test at breakpoint and breakpoint±1 to catch off-by-one bugs in `min-width`/`max-width`. Source: <https://scrolltest.com/playwright-responsive-breakpoint-testing/>, <https://frontendtester.com/how-to-test-responsive-breakpoints-in-playwright-without-hardcoding-every-device/>.

### 2.3 Chrome DevTools MCP server

- Google's first-party `chrome-devtools-mcp` (public preview Sep 2025) — built on Puppeteer + CDP, integrates with Gemini CLI, Claude Code, Cursor, GitHub Copilot. Tools: `navigate_page`, `click`, `fill`, `drag`, `hover`, `list_console_messages`, `evaluate_script`, `list_network_requests`, `performance_start_trace`, `performance_analyze_insight`, plus screenshot/element snapshot. Source: <https://developer.chrome.com/blog/chrome-devtools-mcp>, <https://github.com/ChromeDevTools/chrome-devtools-mcp>, <https://developer.chrome.com/docs/devtools/agents/get-started>.
- Connect via `--browser-url=http://127.0.0.1:9222` to an already-running Chrome with `--remote-debugging-port`, or `--autoConnect` for Chrome 144+ to grab the user's own browser (share manual + agent state).
- **Warning**: exposes your browser content to the agent. Same warning applies to Playwright MCP.

### 2.4 axe-core via MCP — accessibility auditing

- Multiple MCP servers wrap axe-core: `priyankark/a11y-mcp`, `JustasMonkev/mcp-accessibility-scanner`, `aditya-ariosity/wcag-accessibility-mcp`, `ronantakizawa/a11ymcp`, `suryast/a11y-mcp`. Tools: `audit_url`, `audit_html`, `get_rules`, `check_contrast`, `check_aria_attributes`. Filter by WCAG tag (`wcag2aa`, `wcag21aa`, `wcag22aa`, `best-practice`).
- `@axe-core/playwright` plugs axe into Playwright tests for CI.
- **Caveat**: automated coverage is 70–85% of real accessibility issues. Meaningful labels, focus logic, live region timing, reading order, cognitive load still need manual review with real assistive tech.

### 2.5 Storybook MCP — visual test feedback

- Storybook 10 ships an MCP server at `http://localhost:6006/mcp` with `docs-list`, `docs-show`, `test-run`. Storybook Test runs interaction tests + accessibility tests + visual snapshots in a real browser, against every story, on every change. Test output is fed back to the agent so it iterates until failures are resolved. Source: <https://storybook.js.org/docs/ai>, <https://storybook.js.org/ai>.
- Chromatic (Storybook's parent product) makes every story a visual test automatically, cross-browser, cross-viewport, cross-theme. PRs get a UI Tests check; baselines sync across branches.

### 2.6 Visual regression: pixel diff vs ARIA diff

- **Pixel diff** tools — compare screenshots:
  - `toHaveScreenshot()` is built into Playwright Test. Uses pixelmatch under the hood (YIQ color space, perceptual distance, threshold 0.2 default, `maxDiffPixels` and `maxDiffPixelRatio` budgets). First run creates baselines; subsequent runs compare. Always mask volatile content (timestamps, avatars, A/B variants) and disable animations (`animations: 'disabled'`) globally. Source: <https://playwright.dev/docs/test-snapshots>, <https://playwright.aims-ai.com/blog/playwright-visual-regression-testing>.
  - BackstopJS (Puppeteer + Playwright, Resemble.js pixel diff, HTML report with before/after scrubber, MIT, self-hosted). The OSS default if you want zero vendor. Chrome-only in practice (cross-browser via WebDriver has been open for years). Source: <https://cloudzy.com/blog/argos-vs-lost-pixel-vs-backstopjs-compared/>, <https://bugbug.io/blog/test-automation-tools/visual-regression-testing-tools/>.
  - reg-suit: lean OSS comparison layer that posts the diff on the GitHub PR; baseline storage in S3/GCS.
  - Lost Pixel: **archived April 22, 2026**, when the team joined Figma. **Do not adopt for new work.** Migrate to BackstopJS (self-host) or Chromatic (managed).
  - Argos: best workflow (PR review, ARIA-snapshot diffing since late 2025) but managed SaaS in practice — no self-host support. Source: <https://argos-ci.com/visual-testing>.
- **ARIA-snapshot diff** — compare accessibility trees instead of pixels:
  - Playwright's `expect(page).toMatchAriaSnapshot(…)` compares the YAML accessibility tree against a baseline. Order-sensitive, case-sensitive, whitespace-collapsed. Partial matches via `/children`. Source: <https://playwright.dev/docs/aria-snapshots>.
  - Argos Playwright SDK: `argosScreenshot(page, name, { ariaSnapshot: true })` captures both screenshots and ARIA trees; `argosAriaSnapshot()` is ARIA-only. Catches semantic regressions that pixel diffs miss (lost landmarks, removed headings, role flips). Source: <https://argos-ci.com/docs/reference/playwright>, <https://argos-ci.com/changelog/2025-11-04-aria-snapshots>.
- **Why both**: pixel diff catches "the button moved 2px" and "the shadow disappeared"; ARIA diff catches "the toggle lost its `aria-expanded` and screen reader users can't tell it's open". Run both.

### 2.7 Verification loop architectures compared

| Loop | Strength | Weakness | Best for |
|---|---|---|---|
| Screenshot-only (SDD) | Catches visual regressions, no baseline needed | Doesn't catch semantic regressions, expensive token-wise | New UI under active dev |
| Playwright MCP | Deterministic, cheap (accessibility-tree-based), persistent state | Doesn't see pixels | Click-throughs, form fills, exploration |
| Chrome DevTools MCP | Full DevTools power — perf traces, network, console | Same as Playwright MCP + browser exposure risk | Debug, perf audits |
| Playwright `toHaveScreenshot` | Built-in, zero infra, per-breakpoint baselines | Brittle to font/timing variance, masks needed for volatile content | Regression CI |
| BackstopJS | Self-hostable, mature, great HTML report | Chrome-only in practice, manual baseline mgmt | Self-hosted regression CI |
| Chromatic | Zero-config story → test, cross-browser, PR UI Tests badge | SaaS dependency, costs at scale | Teams with a Storybook |
| Argos ARIA snapshot | Catches semantic regressions | Same SaaS dependency as visual Argos | a11y regression CI |
| axe-core MCP | Direct WCAG violation reports | 70-85% of real issues automated | Per-change a11y check |
| Storybook MCP | Component-property-grounded, runs test-run after every change | Requires Storybook | Component-library projects |

### 2.8 Impact-for-effort ranking (Section 2)

1. **Playwright MCP server** in the agent's MCP config — accessibility-snapshot-based clicks, screenshots on demand, network/console introspection. Cheap, deterministic, works with any browser tool the agent already runs.
2. **Playwright `toHaveScreenshot()`** in CI for visual regression on stable surfaces (use `animations: 'disabled'`, mask volatile regions, accept baselines in code review — never blindly `--update-snapshots`).
3. **axe-core via MCP** (e.g. `a11y-mcp`) for per-change a11y audits; `@axe-core/playwright` in CI for enforcement.
4. **Storybook MCP + Chromatic** if you have a component library — agents stop hallucinating props *and* get visual regression for free on every story.
5. **Screenshot-loop harness** for new-UI work without baselines — the agent must screenshot, read, iterate. Make it a prompt-level contract, not a suggestion.
6. Chrome DevTools MCP is redundant with Playwright MCP unless you need performance traces.
7. ARIA-snapshot diffing (Argos) is the most informative *new* signal — add when budget allows.

---

## 3. Known failure modes of AI-built UIs and which artifacts prevent them

### 3.1 Failure inventory (from empirical studies)

- **Accessibility tree is empty** — `master.dev`'s dissection of a sidebar across general-purpose tools (Claude Code, Codex, Cursor, Copilot, ChatGPT) found 10 distinct failures in 29 lines: outer `<div>` instead of `<nav>`, styled `<div>` instead of `<h2>`, items not in `<ul>/<li>`, Account toggle is a `<div>` with `role="generic"` and no `tabIndex`, no `aria-expanded`, no `aria-controls`, no keyboard handling, SVG icon lacks both `aria-hidden` and an accessible name, Profile/Security are `<span onClick>` not `<a>`. Source: <https://master.dev/blog/ai-generated-ui-is-inaccessible-by-default/>.
- **Contrast fails** — Master.dev/uxskill and a peer-reviewed study of 6 LLM-generated sites found 308 errors (47% WCAG 2.2, 53% cognitive); the highest-volume WCAG bucket is **1.4.3 minimum contrast** (n=42 violations). Source: <https://doi.org/10.1145/3663547.3759755>, <https://uxskill.laithjunaidy.com/blog/ai-generated-ui-accessibility.html>.
- **Icon-only buttons with no name** — the same pattern across every model: glyph carries meaning visually, screen reader hears silence. The fix is `aria-label` or visually-hidden text. Source: <https://uxskill.laithjunaidy.com/blog/ai-generated-ui-accessibility.html>.
- **Clickable `<div>` / `<span>` instead of `<button>`** — "Aesthetic Mirage": component looks correct visually, so the developer assumes the structure is sound. A real product team banned AI-generated UI after a 14% conversion drop tied to a custom dropdown made of stacked `<div>` tags with no `role="combobox"`, `aria-expanded`, `tabIndex`, or `role="option"`. Power users tabbed past it; screen readers said nothing; iOS Safari zoomed on focus inside the popover. Source: <https://xqa.io/blog/banned-ai-generated-ui-components>.
- **`outline: none` with no replacement focus ring** — the default ring looks untidy in a static frame, so it gets removed and the agent never replaces it. <https://uxskill.laithjunaidy.com/blog/ai-generated-ui-accessibility.html>.
- **Placeholder used as label** — the field has no real `<label>`, just `placeholder` text. Looks cleaner; breaks for screen readers and breaks on autofill. Same source.
- **Missing loading/error/empty states** — Nielsen Norman 2025 analysis of 50 AI-generated dashboards: 92% had no empty state, 78% had no error state, 100% had a generic spinner (not a skeleton). Human-built equivalents had thoughtful states in 70% of cases. Source: <https://blog.vibecoder.me/empty-states-loading-states-error-states>.
- **Raw error.message to users** — `ECONNREFUSED`, `23505: duplicate key value…` show up directly in the UI; non-technical users panic, technical users lose trust. Source: same.
- **Desktop-first layouts that collapse to unreadable slivers on mobile** — fixed `w-[400px]`, three-column grids that don't reflow, hover-only interactions, undersized touch targets (32px instead of 44px). iOS Safari zooms on inputs smaller than 16px. Sources: <https://nosemicolons.com/posts/ai-generated-react-components-mobile-responsive-design-problems/>, <https://0xminds.com/blog/guides/ai-mobile-responsive-prompts-tutorial>, <https://8080ai.hashnode.dev/prompting-responsive-ui-ai-app-builders>.
- **Missing mobile nav** — agents assume a desktop top-nav exists and never emit a hamburger / drawer / bottom-nav. Source: <https://analoghq.ai/ui-sh/skills/ui-sh-make-responsive>.
- **Inconsistent spacing and colors** — every prompt picks "the model default" (purple gradient, rounded-2xl, Inter at every weight) because there's no shared token to bind to. Source: <https://seedflip.co/blog/cursor-rules-design-system>.

### 3.2 What demonstrably prevents each failure

| Failure mode | Preventive artifact | Source |
|---|---|---|
| Div soup / missing ARIA | **Accessible component library** (Radix UI, Headless UI, React Aria, Bits UI for Svelte) — accessibility is structural, not prompt-driven | <https://master.dev/blog/ai-generated-ui-is-inaccessible-by-default/> |
| Same | **Layer 1 prompt rules** in `.cursorrules` / `AGENTS.md`: "Use `<button>` for actions. Never `<div onClick>`. Add `aria-expanded` to toggles. Use `<dialog>` for modals." | Same |
| Same | **Layer 2 `eslint-plugin-jsx-a11y`** set to `error` in CI | Same |
| Same | **Layer 3 `@axe-core/playwright`** runtime tests | Same |
| Same | **Layer 4 CI gate** — PRs cannot merge with axe violations | Same |
| Contrast failures | **DESIGN.md linter `contrast-ratio` rule** (catches WCAG AA at token-definition time) | <https://github.com/google-labs-code/design.md> |
| Same | **Color tokens** with explicit OKLCH/sRGB and lint rule that warns on `<4.5:1` body text | <https://uxskill.laithjunaidy.com/blog/ai-generated-ui-accessibility.html> |
| Inconsistent spacing/colors | **Tailwind v4 `@theme` block** generated from DESIGN.md or DTCG tokens — agent has no choice but to use the scale | <https://github.com/google-labs-code/design.md>, <https://designtoken.md/frameworks/svelte> |
| Same | **Cursor rules** with explicit hex/radius/font values + "NEVER use Tailwind color utilities" | <https://seedflip.co/blog/cursor-rules-design-system> |
| Missing loading/empty/error states | **Agent skill / reviewer** (e.g. `add-empty-error-states`, `ux-states-audit`) — runs after data fetches are wired, fills the gaps using existing primitives | <https://github.com/agentsystemlabs/core/blob/main/plugins/agentsystem-core/skills/add-empty-error-states/SKILL.md>, <https://eliteai.tools/agent-skills/ux-states-audit> |
| Same | **State checklist** baked into the repo's `.cursorrules` / `AGENTS.md`: "Every fetch has loading + empty + error states. Error states must include Retry. Never render `error.message` raw." | <https://github.com/ravnhq/ai-toolkit/blob/main/skills/frontend/platform-frontend/rules/data-loading-states.md> |
| Same | **Storybook story** per component covering loading/empty/error/happy — agent reads the manifest and reuses the pattern | <https://storybook.js.org/docs/ai/best-practices.md> |
| Desktop-only layouts | **Agent skill `make-responsive` / `doesntbreak`** — enforces mobile-first, `min(100%, Npx)` instead of fixed widths, `min-h` not fixed `h`, 16px input font, 44px touch targets, `dvh/svh/lvh` for mobile viewport, `overflow-x: auto` for wide tables | <https://github.com/Kyaa-A/doesntbreak>, <https://analoghq.ai/ui-sh/skills/ui-sh-make-responsive> |
| Same | **Playwright responsive matrix** in CI: viewport project per device class, breakpoint±1 boundary tests, `scrollWidth` guard against horizontal overflow | <https://scrolltest.com/playwright-responsive-breakpoint-testing/> |
| Same | **Prompt rule**: "Mobile-first. Stack on mobile, expand to 2 cols on `md`, 3 cols on `lg`. No hover-only interactions. 44px touch targets. 16px input font." | <https://8080ai.hashnode.dev/prompting-responsive-ui-ai-app-builders> |
| Component-level regressions | **Storybook MCP server + Chromatic** — every story becomes a visual + interaction test, results stream back to the agent | <https://storybook.js.org/docs/ai> |
| Semantic regressions missed by pixel diffs | **Argos ARIA-snapshot diff** alongside `toHaveScreenshot()` | <https://argos-ci.com/changelog/2025-11-04-aria-snapshots> |

### 3.3 The five-layer enforcement model (master.dev)

This is the cleanest articulation of what to do about accessibility specifically:

1. **Prompt constraints** — bake HTML-semantics + a11y + keyboard rules into `.cursorrules` / `AGENTS.md` so they're applied to every generation.
2. **Static analysis** — `eslint-plugin-jsx-a11y` at `error` severity in CI.
3. **Runtime testing** — `@axe-core/playwright` against rendered pages.
4. **CI integration** — PRs cannot merge with violations.
5. **Accessible component abstractions** — Headless UI / Radix / React Aria / Bits UI for Svelte. This is the highest-leverage layer because it works regardless of which AI tool generated the code.

The two interventions the author flags as most leveraged: **`eslint-plugin-jsx-a11y` at error severity** and **the architectural decision to use accessible component primitives**. Source: <https://master.dev/blog/ai-generated-ui-is-inaccessible-by-default/>.

### 3.4 Impact-for-effort ranking (Section 3)

1. **Use accessible component primitives** (Radix/Headless UI/React Aria for React, Bits UI for Svelte). Architectural — works for every future prompt automatically.
2. **DESIGN.md with token linter** — prevents contrast failures, inconsistent colors/spacing at definition time.
3. **Tailwind v4 `@theme` block** generated from tokens — prevents "model-default" UI drift.
4. **Layered a11y enforcement** (`.cursorrules` rules + `eslint-plugin-jsx-a11y` error + axe-core in CI) — catches what primitives miss.
5. **`make-responsive` / `doesntbreak` agent skill** — prevents the desktop-only output pattern; specifically handles iOS zoom, missing mobile nav, 44px targets.
6. **`add-empty-error-states` agent skill** (or its equivalent) — runs after data-fetch wiring; forces all three states.
7. **Storybook stories covering loading/empty/error/happy** — agent reads the manifest, reuses the pattern.
8. **Playwright responsive matrix** in CI — keeps honest.

---

## 4. llms.txt / llms-full.txt conventions

### 4.1 Format spec

- File at `/llms.txt` (or scoped subpath). Required: H1 with project name. Optional: blockquote summary, paragraphs of preamble, H2 sections containing Markdown lists of `[Name](absolute-url): short description.` links.
- The `Optional` section has special meaning — its links can be skipped if context is short.
- Plain Markdown, UTF-8, no nested bullets, no HTML.
- Companion file at `/llms-full.txt`: the full text of all linked pages concatenated — for tools that want consolidated context.
- `rel="describedby"` declaration helps AI crawlers that respect it.

### 4.2 Who publishes llms.txt (frontend-relevant, as of Sep 2026)

| Project | llms.txt | llms-full.txt | Notes |
|---|---|---|---|
| Svelte / SvelteKit / CLI | ✅ | ✅ + medium/small variants | <https://svelte.dev/docs/llms>, <https://learn.svelte.dev/docs/llms> |
| Tailwind CSS v4 | ❌ | ❌ | Maintained by Adam Wathan, who refused PR #2388 citing traffic loss. Workaround: <https://context7.com/websites/tailwindcss> or Lombiq's `Tailwind-Agent-Skills` |
| DaisyUI | ✅ | — | Tailwind plugin; explicitly cited as a positive example |
| Next.js | ✅ | ✅ | Pattern cited as positive |
| Better-Auth | ✅ | ✅ | |
| Zod | ✅ | ✅ | |
| shadcn/ui | ✅ (docs.llms.txt) | ✅ | <https://ui.shadcn.com/llms.txt> |
| FastHTML / nbdev projects | ✅ | ✅ (llms-ctx.txt, llms-ctx-full.txt) | Originator convention; Jeremy Howard |
| VitePress docs (many libs) | ✅ | via `vitepress-plugin-llms` | |
| Docusaurus sites | ✅ | via `docusaurus-plugin-llms` | |
| MCP project | ✅ | ✅ | <https://modelcontextprotocol.io/llms.txt>, <https://modelcontextprotocol.io/llms-full.txt> |

### 4.3 How agents should use llms.txt

- **Don't preload** `llms-full.txt` into the system prompt — bloats context. Use `llms.txt` as an index.
- **Cache the index locally** on first fetch — fetch individual pages by URL on demand.
- **Prefer `llms-small.txt` / `llms-medium.txt`** when the project publishes them (Svelte does).
- **For Tailwind v4 specifically**: there's no official `llms.txt`. The community has settled on either `context7.com` (a hosted indexer) or building a local snapshot from the public MDX (`tailwindcss.com/docs/...`) using `prompt-tower` or `docs2llms`. Both are clearly inferior to an official file — the upstream author is actively hostile to it.

### 4.4 Impact-for-effort ranking (Section 4)

1. **Cache `https://svelte.dev/llms.txt`** locally and use it to fetch Svelte docs on demand. Works today, costs nothing.
2. **Skip Tailwind** official llms.txt route — use `context7.com/websites/tailwindcss` or Lombiq's skill. Don't waste time waiting for an official file.
3. **If you build your own docs site**, ship `llms.txt` + `llms-full.txt` from day one — VitePress and Docusaurus plugins make it free. You will be cited more by agent tools.

---

## 5. Putting it together — what a maximally-correct agent loop looks like

**Knowledge the agent carries at all times (always in context):**
- `AGENTS.md` / `CLAUDE.md` at repo root — process rules, file layout, "don't touch generated", build commands, "don't claim done without running the verification harness".
- `.cursor/rules/design.mdc` (if Cursor) or equivalent — visual token block with explicit hex/font/radius values + behavioral rules + "NEVER use Tailwind color utilities" + "NEVER use arbitrary values" + "NEVER omit loading/empty/error states".
- `DESIGN.md` — typed tokens + prose rationale, linted at write time.
- A short accessibility rules block: use `<button>` not `<div onClick>`, focus-visible on every interactive, Radix/Headless/Bits UI for primitives, 44px touch targets, 16px input font.

**Knowledge the agent fetches on demand:**
- `https://svelte.dev/llms.txt` for the docs index (cached locally).
- Storybook MCP (`http://localhost:6006/mcp`) for component props and stories.
- shadcn registry MCP if a registry is configured in `components.json`.

**Verification harness the agent must run before claiming "done":**
1. TypeScript / svelte-check passes.
2. ESLint with `eslint-plugin-jsx-a11y` at `error` passes.
3. `npm run dev` boots; agent navigates each route at 375px, 768px, 1280px via Playwright MCP; takes screenshots.
4. Agent reads each screenshot and confirms: no overflow, nav present at every viewport, no hover-only interaction without touch fallback, primary action visible.
5. `npx playwright test` runs; `toHaveScreenshot()` baselines still match.
6. axe-core MCP audit at WCAG 2.2 AA on the same routes; critical/serious violations fixed before claiming done.

**MCP servers to wire:**
- `playwright` MCP (default — `@playwright/mcp@latest`) for browser control.
- `chrome-devtools-mcp` if you need performance traces or to attach to the user's running Chrome.
- `a11y-mcp` (or `@axe-core/playwright` invoked via a custom MCP) for axe audits.
- `storybook` MCP at `http://localhost:6006/mcp` if you have Storybook.
- Custom shadcn registry MCP if publishing.

**Tool selection:**
- New UI under active dev → screenshot-driven loop (SDD), no baseline.
- Stable surfaces → Playwright `toHaveScreenshot()` in CI, per-breakpoint baselines.
- Component library → Storybook + Chromatic; CI runs every story on every PR.
- Semantic regressions → Argos ARIA-snapshot diff or Playwright `toMatchAriaSnapshot()` in CI.

---

## Source index (every URL cited, by section)

**Section 1 (spec formats):**
- W3C DTCG: <https://www.designtokens.org/tr/2025.10/format/>, <https://tr.designtokens.org/format/>
- Style Dictionary: <https://styledictionary.com/>
- Token Studio: <https://tokens.studio/>
- DESIGN.md (Google Stitch, open-sourced): <https://github.com/google-labs-code/design.md>, <https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-design-md/>, <https://raw.githubusercontent.com/google-labs-code/design.md/master/docs/spec.md>
- designtoken.md Svelte framework: <https://designtoken.md/frameworks/svelte>
- Cursor rules: <https://cursor.com/docs/rules>, <https://www.matchkit.io/blog/cursor-design-system-setup>, <https://seedflip.co/blog/cursor-rules-design-system>, <https://seedflip.co/blog/cursorrules-design-output>
- shadcn registry.json: <https://github.com/shadcn-ui/ui/blob/main/packages/shadcn/src/registry/schema.ts>, <https://ui.shadcn.com/docs/registry/registry-json>, <https://ui.shadcn.com/docs/registry/getting-started>, <https://ui.shadcn.com/docs/registry/namespace>, <https://ui.shadcn.com/docs/registry/api-reference>
- Lovable prompting + knowledge + design systems: <https://docs.lovable.dev/prompting/prompting-one.md>, <https://docs.lovable.dev/features/design-systems>, <https://docs.lovable.dev/features/knowledge>, <https://docs.lovable.dev/features/projects/chat>
- Bolt.new prompting: <https://bolt.new/blog/prompting-guide>, <https://support.bolt.new/best-practices/prompting-effectively>, <https://sureprompts.com/blog/bolt-new-prompting-guide>
- Claude Artifacts system prompt: <https://github.com/jujumilk3/leaked-system-prompts/blob/main/claude-artifacts_20240620.md>, <https://zerotwo.ai/prompts/system-prompts/anthropic/claude-artifacts>, <https://www.inkeybit.com/blog/claude-artifacts-complete-guide>
- Storybook AI: <https://storybook.js.org/docs/ai>, <https://storybook.js.org/ai>, <https://storybook.js.org/docs/ai/best-practices.md>, <https://storybook.js.org/docs/10.4/writing-tests/visual-testing.md>
- Chromatic: <https://www.chromatic.com/storybook>
- Ladle / Histoire alternatives: <https://www.github.com/tajo/ladle>, <https://ladle.dev/blog/introducing-ladle/>, <https://github.com/histoire-dev/histoire/>, <https://digitalthriveai.com/en-gb/resources/web-development/alternatives-to-react-storybook/>
- llms.txt spec and projects: <https://llmstxt.org/>, <https://github.com/AnswerDotAI/llms-txt>, <https://svelte.dev/docs/llms>, <https://learn.svelte.dev/docs/llms>, <https://llmtxt.info/llms-txt-format/>, <https://github.com/tailwindlabs/tailwindcss.com/pull/2388>, <https://github.com/tailwindlabs/tailwindcss/discussions/18256>, <https://github.com/tailwindlabs/tailwindcss/discussions/14677>, <https://github.com/tailwindlabs/tailwindcss.com/pull/2423>
- v0 architecture (Radix-based): <https://master.dev/blog/ai-generated-ui-is-inaccessible-by-default/>
- Svelte 5 + Tailwind v4 `@theme` examples: <https://github.com/lugassawan/panen/blob/main/docs/design-system.md>, <https://github.com/emdzej/ui-kit>, <https://github.com/OliveiraCleidson/svelte-fast-ui>, <https://github.com/gstohl/liquidcn>

**Section 2 (verification loops):**
- Screenshot-driven development: <https://dev.to/yureki_lab/how-i-gave-my-ai-coding-agent-eyes-a-screenshot-feedback-loop-for-ui-work-jce>, <https://www.coder000.com/post/screenshot-loop-ai-design>, <https://github.com/AmElmo/proofshot>, <https://github.com/tn0123/one-shot-ui>, <https://www.mindstudio.ai/blog/ai-agent-verification-self-checking-workflows>
- Playwright MCP: <https://playwright.dev/mcp/introduction>, <https://playwright.dev/docs/getting-started-mcp>, <https://github.com/microsoft/playwright-mcp>, <https://www.shiplight.ai/blog/playwright-mcp>
- Chrome DevTools MCP: <https://github.com/ChromeDevTools/chrome-devtools-mcp>, <https://developer.chrome.com/docs/devtools/agents/get-started>, <https://developer.chrome.com/blog/chrome-devtools-mcp>, <https://www.marktechpost.com/2025/09/23/google-ai-introduces-the-public-preview-of-chrome-devtools-mcp-making-your-coding-agent-control-and-inspect-a-live-chrome-browser/>, <https://codelabs.developers.google.com/agentic-ui-testing>
- axe-core MCP servers: <https://github.com/priyankark/a11y-mcp/>, <https://github.com/aditya-ariosity/wcag-accessibility-mcp>, <https://github.com/suryast/a11y-mcp>, <https://github.com/ronantakizawa/accessibilitymcp>, <https://github.com/JustasMonkev/mcp-accessibility-scanner>
- Storybook MCP + Chromatic: <https://storybook.js.org/docs/ai>, <https://storybook.js.org/ai>, <https://storybook.js.org/docs/10.4/writing-tests/visual-testing.md>, <https://www.chromatic.com/storybook>
- Visual regression tools: <https://playwright.dev/docs/test-snapshots>, <https://web-automations.com/debugging-and-test-observability/visual-regression-testing/>, <https://playwright.aims-ai.com/blog/playwright-visual-regression-testing>, <https://scrolltest.com/visual-regression-testing-playwright-production-guide/>, <https://github.com/currents-dev/playwright-best-practices-skill/blob/HEAD/playwright-best-practices/testing-patterns/visual-regression.md>, <https://cloudzy.com/blog/argos-vs-lost-pixel-vs-backstopjs-compared/>, <https://ai-testing-in-qa.hashnode.dev/visual-regression-testing-tools>, <https://bugbug.io/blog/test-automation-tools/visual-regression-testing-tools/>, <https://lastest.cloud/blog/best-open-source-visual-regression-testing-playwright>
- ARIA snapshots: <https://playwright.dev/docs/aria-snapshots>, <https://argos-ci.com/docs/reference/playwright>, <https://argos-ci.com/changelog/2025-11-04-aria-snapshots>, <https://argos-ci.com/visual-testing>
- Responsive Playwright: <https://scrolltest.com/playwright-responsive-breakpoint-testing/>, <https://executeautomation.github.io/mcp-playwright/docs/playwright-web/Resize-Prompts-Guide>, <https://frontendtester.com/how-to-test-responsive-breakpoints-in-playwright-without-hardcoding-every-device/>

**Section 3 (failure modes):**
- Accessibility / div soup: <https://master.dev/blog/ai-generated-ui-is-inaccessible-by-default/>, <https://blog.master.dev/ai-generated-ui-is-inaccessible-by-default/>, <https://uxskill.laithjunaidy.com/blog/ai-generated-ui-accessibility.html>, <https://xqa.io/blog/banned-ai-generated-ui-components>, <https://iris.polito.it/retrieve/handle/11583/3008330/983056>, <https://doi.org/10.1145/3663547.3759755>
- Loading / empty / error states: <https://blog.vibecoder.me/empty-states-loading-states-error-states>, <https://github.com/agentsystemlabs/core/blob/main/plugins/agentsystem-core/skills/add-empty-error-states/SKILL.md>, <https://eliteai.tools/agent-skills/ux-states-audit>, <https://github.com/ravnhq/ai-toolkit/blob/main/skills/frontend/platform-frontend/rules/data-loading-states.md>, <https://tessl.io/registry/tessl-labs/frontend-error-handling/0.2.1>
- Responsive failures: <https://nosemicolons.com/posts/ai-generated-react-components-mobile-responsive-design-problems/>, <https://0xminds.com/blog/guides/ai-mobile-responsive-prompts-tutorial>, <https://8080ai.hashnode.dev/prompting-responsive-ui-ai-app-builders>, <https://analoghq.ai/ui-sh/skills/ui-sh-make-responsive>, <https://github.com/Kyaa-A/doesntbreak>
- Visual / spacing drift: <https://seedflip.co/blog/cursor-rules-design-system>, <https://www.matchkit.io/blog/cursor-design-system-setup>

**Section 4 (llms.txt):**
See section 1 sources plus <https://github.com/tailwindlabs/tailwindcss.com/pull/2423>, <https://llmtxt.info/llms-txt-format/>.

---

*Research date: 2026-09-16. Cited claims reflect the public state of these tools on that date. Where tool status could change (e.g., "Lost Pixel archived" — Apr 2026), the date is in-line.*
