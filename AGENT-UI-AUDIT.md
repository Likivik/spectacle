# Achiyon web UI — knowledge-pack audit

> Audit of the existing UI knowledge base (`web/DESIGN.md`, `web/src/app.css`,
> the two live routes, the mockups, and the agent rules) plus an outline for
> the missing `web/AGENT-UI.md`. The next agent will use that file before
> building auth pages, so it has to encode the conventions, the state matrix,
> and the gotchas that the live code already paid for in bugs.

Repo paths cited as `file:line` are against `/Storage/Git/achiyon`. Note that
the canonical docs live in `development-docs/archive/THESIS.md` and
`development-docs/archive/mockups/onboarding-v2/` — there is no `docs/THESIS.md`
or `docs/mockups/` in the tree today.

---

## 1. Inventory of what exists

### 1.1 Design tokens — `web/src/app.css`

118 lines, single source of truth for tokens. Two naming systems coexist,
neither bridged to the other.

| Concern | Lines | What |
|---|---|---|
| Tailwind v4 base | 1–4 | `@import "tailwindcss"` + `tailwindcss-animate` + `@custom-variant dark` |
| `:root` token block | 7–38 | shadcn-svelte style names: `--background`, `--foreground`, `--card`, `--surface`, `--card-foreground`, `--popover`, `--primary`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--muted`, `--bg-active`, `--muted-foreground`, `--text-dim`, `--text-faint`, `--accent`, `--accent-deep`, `--accent-bright`, `--accent-foreground`, `--destructive`, `--destructive-foreground`, `--border`, `--border-strong`, `--input`, `--ring`, `--radius`, `--touch`, `--serif` |
| `.dark` block (duplicates `:root`) | 41–68 | Same values — the comment notes "dark-only, so apply directly" |
| Global `* { border-color: var(--border) }` | 71–73 | Default border is the token, not a raw grey |
| `body` base | 79–85 | `font-family: var(--serif)` (Georgia/Times), antialiased, `background-color: var(--background)`, `color: var(--foreground)` |
| `@theme inline` | 87–118 | Re-exports each token under Tailwind's `--color-*` namespace so `bg-primary`, `text-text-dim`, etc. work in class attributes |

### 1.2 Design system contract — `web/DESIGN.md`

84 lines. Declared as the source of truth (line 1–5). Tokens table (line 13–33),
typography (line 40–45), spacing/shape (line 47–51), motion (line 53–56),
component inventory (line 58–68), state-pattern mandate (line 70–74),
mobile-first invariants (line 76–80), anti-cliché list (line 82–84).

### 1.3 Product soul — `development-docs/archive/THESIS.md`

62 lines. The thesis (line 9–10), three pillars (line 21–25), the
adventure→memory→home loop (line 27–31), competitive position (line 33–38),
why-we-win list (line 40–50). This is the **product voice** anchor — the
UI's tone ("a soft-spoken listener who notices everything", "the quill
moves…") comes from here.

### 1.4 Live routes

| File | LoC | Purpose |
|---|---|---|
| `web/src/routes/+layout.svelte` | 9 | Imports `app.css`, force-adds `.dark` to `<html>` |
| `web/src/routes/+page.js` | 3 | SPA hash router, `ssr=false` |
| `web/src/routes/+page.svelte` | 769 | Home + onboarding wizard (4 steps: name/pronouns → companion choice → spark → soul reveal; plus post-onboarding stages) |
| `web/src/routes/chat/+page.svelte` | 521 | Chat: header (back, char tag, think toggle, kept drawer), message stream, character card panel, kept-memories panel, world-event chips, composer |

### 1.5 shadcn-svelte component primitives — `web/src/lib/components/ui/`

- **button** (`button.svelte`): `tailwind-variants` with 6 variants (`default`, `outline`, `secondary`, `ghost`, `destructive`, `link`) × 7 sizes (`default`, `xs`, `sm`, `lg`, `icon`, `icon-xs`, `icon-sm`, `icon-lg`). Token-aware (uses `bg-primary`, `text-primary-foreground`, `border-ring` etc.). Has `aria-invalid` and `focus-visible:ring` baked in.
- **input** (`input.svelte`): one shadcn class string; `h-8 rounded-lg border-input focus-visible:ring-ring/50 aria-invalid:ring-destructive/20`. Used in wizard step 1 and 3b.
- **textarea** (`textarea.svelte`): one shadcn class string; `flex field-sizing-content min-h-16`. Used in wizard step 4 (soul reveal) AND chat composer? No — chat composer hand-rolls its own `<textarea class="composer">` (chat/+page.svelte:309–317).
- **label** (`label.svelte`): thin wrapper over `bits-ui` `Label.Root`; **not currently used anywhere in the two routes**.
- **radio-group** (`radio-group.svelte` + `radio-group-item.svelte`): bits-ui wrapper; **not used in the two routes** — the wizard hand-rolls a `role="radiogroup"` button group (lines 233–240).

### 1.6 Sigil helper — `web/src/lib/sigil.js`

20 lines. `sigilStyle(seed)` returns a CSS string with `background: radial-gradient(...)`, `border`, `color`, `transform: rotate(Ndeg)`, `animation: sigil-pulse Ns ease-in-out infinite`. Deterministic via FNV-1a over the seed string. Tested (`sigil.test.js`, 5 cases, all green).

### 1.7 Token-name reality (in code today)

The live routes use **both** token systems and several raw hexes:

**Tokens used directly** (via `var(--…)`):
- Chat: `--muted-foreground` (line 325), `--text-dim` (line 338, 378, 473), `--foreground` (line 344, 351, 450), `--input` (line 349), `--border-strong` (line 350, 497), `--surface` (line 364, 382, 436, 482), `--border` (line 365, 382, 412, 437, 483), `--muted-foreground` (line 401), `--secondary` (line 429), `--background` (line 381), `--text-dim` (line 473)
- Home: `--background`, `--foreground`, `--accent`, `--accent-bright`, `--accent-deep`, `--primary-foreground`, `--bg-active`, `--border-strong`, `--border`, `--surface`, `--secondary`, `--muted-foreground`, `--text-dim`, `--text-faint`, `--destructive`

**Tokens used via Tailwind classes** (from `@theme inline`):
- `text-base`, `text-text-dim`, `text-sm`, `text-xs` (chat + home)
- `max-w-[44rem]` (chat), `max-w-28rem` (no — actually inline `max-width: 28rem;`, home:369)
- `border-[#262626]` (chat:229, 308) — **raw hex**

**Raw hex in markup (rule violation per AGENTS.md)**:
- `#262626` — chat:229, 308, 397 (border-bottom + kept-row separator)
- `#3a3f4b` — chat:446 (user message left border)
- `#b5b5b5` — chat:413 (chip text)
- `#4a3a57`, `#c0a8b8`, `#3a5747`, `#a8c0b4` — chat:416–422 (relationship/new-entity chip variants — not in any token table)
- `#616161` — chat:465 (think span color)
- `#235` etc. inside `sigil.js:14–17` are generated `hsla(...)`, not violations

### 1.8 Class-pattern idioms

Both pages re-implement the same handful of classes locally instead of
sharing a component. Same idioms appear twice:

| Pattern | Home page | Chat page |
|---|---|---|
| Stage layout (centered column, flex 1, justify-center) | `.stage` (393–401) | n/a (chat is column-flow) |
| Page max-width + centered main | inline `main { max-width: 28rem; margin: 0 auto }` (368–370) | `mx-auto max-w-[44rem]` (228) |
| Header band, h1 + tagline | inline `header` + `h1` (377–390) | `.tag` inside `header` (229–244) |
| Ghost button | `.ghost` (441–451) | `.ghost` (335–345) |
| Solid button (panel input "save") | uses shadcn `Button` (247) | `.solid` (348–360) |
| Primary action (full-width, accent) | `.creator .primary` (625–648) + `.primary` (430–440) | n/a (chat sends via `.solid`) |
| Hint text (italic, dim) | `.hint` (423–429) | `.hint` (400–405) |
| Panel surface | n/a (no panel in home — uses `.stub` instead, 452–462) | `.panel` (363–389) |
| Sigil avatar | inline `.sigil` + `.sigil.big` + `.sigil.you` (506–523) | inline `.sigil-tiny` (501–510) |
| Fade-in animation | `.fade-in` appears **twice** with two keyframes (`qfade` 493–499, `fadein` 527–536) | n/a |
| `prefers-reduced-motion` guard | appears **twice** (490–492 empty, 500–502 for `.fade-in`, 534–536 also for `.fade-in`) | absent |

### 1.9 Component idioms (state, fetch, async)

The two pages independently rediscovered the same patterns. A future
`AGENT-UI.md` should codify these so the third page doesn't re-litigate
them:

- **Fetch guard.** Every `fetch` lives inside a `try/catch` that logs
  (`console.error(..., e)`) AND surfaces a visible `chatError`/`saveError`/
  `soulError` string. See chat:53–57, 94–97, 117, 135–138, 158–166, 172–175;
  home:67–71, 90–94, 109–114, 134–139, 153–155, 199–202.
- **Async flag in `finally`.** `streaming`, `nameBusy`, `soulWriting`, `loading`
  all reset in `finally`, not just happy path. (AGENTS-LESSONS.md L12.)
- **`if (!r.ok) throw new Error(`…${r.status}`)`** before reading the body.
  Chat:158, 130–131; home:66, 86, 105, 130, 150, 171, 197.
- **`chatId` gate.** Chat send is disabled when `!chatId || streaming` —
  no fetch fires until the chat exists (chat:144, 314, 318). Home's
  `goChat` does the chat-create-then-character-save sequence inline.
- **State shape.** Multi-step wizard uses one big `$state` bag per step,
  not a store. Single source of truth is local `$state`.

### 1.10 Message voice (error + hint copy)

Voice is **inconsistent across pages**. Same event, different words:

| Event | Home voice | Chat voice |
|---|---|---|
| Server unreachable on persona save | "could not save — tap again" | — |
| Server unreachable on soulspark | "the quill slipped — check connection, tap again" | — |
| Server unreachable on goChat | "could not open the conversation — check connection, then try again" | — |
| Server unreachable on resume | — | "could not reach the server — retry from home" |
| Server unreachable on send | — | "⚠ could not reach the narrator — tap ↻ or resend" |
| Stream interrupted mid-message | — | " ⚠ stream lost" (appended to bubble) |
| Card save failed | — | "card not saved — check connection and retry" |
| Pin/unpin failed | — | "could not pin — retry" / "could not unpin — retry" |

Hints use lowercase, italic, dim, often poetic ("a name and a spark —
that's all we need" / "the quill moves…" / "hover a message → 📌 keep").
This voice comes from THESIS.md and the mockup README — but it's not
captured in DESIGN.md or AGENTS.md.

---

## 2. Disagreements and gaps

### 2.1 DESIGN.md vs `app.css` token names

DESIGN.md uses semantic, descriptive names: `--bg`, `--bg-inset`,
`--bg-raised`, `--bg-active`, `--border`, `--border-strong`, `--text`,
`--text-bright`, `--text-dim`, `--text-faint`, `--text-meta`, `--accent`,
`--accent-bright`, `--accent-deep`, `--accent-deepest`, `--accent-pale`.

`app.css` uses shadcn-svelte's names: `--background`, `--card`, `--surface`,
`--secondary`, `--muted`, `--bg-active`, `--muted-foreground`, `--text-dim`,
`--text-faint`, `--primary`, `--primary-foreground`, `--accent`,
`--accent-deep`, `--accent-bright`, `--accent-foreground`, `--destructive`,
`--destructive-foreground`, `--border`, `--border-strong`, `--input`,
`--ring`, `--foreground`, `--popover`, `--popover-foreground`.

- **Missing in `app.css`:** `--bg`, `--bg-inset`, `--bg-raised`, `--text`,
  `--text-bright`, `--text-meta`, `--accent-deepest`, `--accent-pale`,
  `--sigil-user`, `--sigil-companion`.
- **Missing in DESIGN.md:** `--primary`, `--primary-foreground`,
  `--card-foreground`, `--secondary`, `--secondary-foreground`,
  `--popover`, `--popover-foreground`, `--muted`, `--muted-foreground`,
  `--destructive-foreground`, `--input`, `--ring`, `--accent-foreground`,
  `--radius`, `--touch`, `--serif`, and the entire `@theme inline` mapping.
- **Both list:** `--bg-active` (DESIGN.md line 19 / app.css line 20, 54),
  `--border`, `--border-strong`, `--text-dim`, `--text-faint`,
  `--accent`, `--accent-deep`, `--accent-bright`. No mention that two
  systems exist.

The mockup `palette.html` introduced a **third** palette with raw hex only
(accent-deepest `#291d35`, accent-deep `#3d2853`, accent `#9e69d3` — note
the mockup's `#9e69d3` differs from app.css's `#7c3aed`/`#a78bfa`). This
file is a reference, not loaded; the live code uses the app.css values
but the mockup diverges.

### 2.2 DESIGN.md vs live markup

- **Page max-width.** DESIGN.md says `28rem` (line 48). Home uses 28rem
  (line 369). Chat uses `max-w-[44rem]` (line 228). Disagreement.
- **Radii.** DESIGN.md says `8px` (line 49). Chat uses `6px` on inputs
  and `.solid` (line 353, 385, 486), `8px` on panels (line 366), `999px`
  on chips (line 411), `50%` on sigils (line 507). Home uses `8px`
  on stubs and panels, `12px` on chips and primaries, `16px` on
  choice cards. No single radius.
- **Touch targets.** DESIGN.md says `≥ 52px` (line 50). Some chat
  ghost buttons violate this: `.ghost { padding: 0.1rem 0.3rem }`
  (line 341) — height ≈ 24px. The `.pin` button on hover is `0.72rem`
  text (line 456) — far below 52px.
- **No hover-only affordances.** DESIGN.md line 78. Chat `.msg:hover .pin
  { opacity: 1 }` (line 459–461) is exactly that — tap-only devices
  can't trigger `hover`. Mobile users lose pin.
- **No emoji-as-icons.** DESIGN.md line 83. Chat uses ✎ 📌 ← ⚠ ▍ ✶
  as icons (lines 230, 238–239, 247, 301, 305, 318, etc.). Home uses
  ✦ ⚙ ←. The mockup README and THESIS.md both endorse glyph-only
  minimalism, so this is an internal contradiction.
- **"Every animation needs prefers-reduced-motion"** (DESIGN.md line 55).
  Home has empty `@media (prefers-reduced-motion: reduce) {}` block
  (line 490–492) and duplicates (line 500–502, 534–536). Chat has none.
  Sigil pulse animation (`web/src/lib/sigil.js:18`) — no override.
  Cursor blink (chat:472) — no override.
- **Stale inventory.** DESIGN.md component table (line 58–68) lists
  "Likert scale" and "Quiz card" — neither exists in code anymore
  (the onboarding wizard replaced the quiz, see home:21–48).
- **Sigil variants.** DESIGN.md line 62 says `.tiny/.mid/.big`. Code has
  `.sigil-tiny` (chat:501), `.sigil.big` (home:514), `.sigil.you`
  (home:519). Three names, two scales; `.mid` not used.
- **"No raw hex in markup"** (AGENTS.md §UI). Violated as listed in §1.7.

### 2.3 Home vs chat disagreements

- **Sigil placement in header.** Home has no sigil in header; chat has
  `.sigil-tiny` for the current character (line 232). Home shows the
  sigil in the body stage instead (line 342, 350).
- **Pronoun chip pattern.** Home uses `.creator .chip` with a
  `chip-check` dot (line 663–700), role=radio, aria-checked. Chat has
  no equivalent. Mockup uses `aria-pressed` (mockup line 55). Three
  patterns for the same concept across the codebase.
- **Button defaults.** Home uses shadcn `Button` (line 247). Chat uses
  `.solid` and `.ghost` (line 335, 348). Same button, two implementations.
- **Input field.** Home uses shadcn `Input` (line 228). Chat uses bare
  `<input class="panel-input">` (line 251). Two implementations.
- **Loading state.** Home: `loading` → `…` ellipsis (line 217). Chat:
  no loading state at all — `resumeChat` (line 65) renders an empty
  chat until messages arrive.
- **Empty state.** Home: empty stage when no companion (line 339–346),
  shows "Create companion" CTA. Chat: no empty state — empty message
  array renders nothing visible inside `.chat`.
- **Error display.** Home: `.err` (line 649–653, destructive color)
  for `saveError`; `.hint` (default muted) for `soulError` (line 322).
  Chat: `.hint` for `chatError` (line 246). Two error styles in home
  alone.
- **Back navigation.** Home step 3+: explicit ← back button with
  `aria-label="back"` (line 253, 280, 325). Chat: text anchor `←`
  (line 230) — no aria-label, no `btn` semantics. Home step 1 has no
  back button at all.
- **Fade-in animation duplication.** Home has `.fade-in` declared twice
  (line 493, 527) with separate keyframes (`qfade` vs `fadein`). Chat
  has none.
- **Focus-visible style.** Home: inherited from shadcn Button
  (line 7 — `focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50`).
  Chat composer: `:focus { outline: none; border-color: var(--border-strong) }`
  (line 495–498) — kills native outline, adds no replacement visible
  to all users.
- **Wizard step key.** Home uses `{#key 1}` on the step-1 heading
  (line 223) to retrigger the fade-in animation. Step transitions
  elsewhere don't use `{#key}` (line 255, 281, 325) — inconsistent.

### 2.4 What's missing entirely from the knowledge base

- **Spacing scale.** No documented scale. Both pages use literal `0.5rem`,
  `0.75rem`, `1rem` values ad-hoc.
- **State matrix.** DESIGN.md mentions the loading+empty+error triple
  (line 70–74) but no per-surface enumeration (wizard step states,
  message list states, header states, panel states, etc.).
- **SSE/streaming UX rules.** No documented behavior for: streaming
  cursor placement, interrupted-stream recovery, regenerate-last-turn,
  empty-bubble placeholder during the first token, scroll anchoring.
- **Form UX rules.** No documented behavior for: validation timing
  (on-blur vs on-submit), inline vs banner errors, disabled-CTA-until-valid
  vs always-enabled, maxlength feedback, multi-step draft persistence.
- **Accessibility rules.** No documented keyboard map, focus order,
  ARIA pattern for the radio-chip group, reduced-motion policy,
  screen-reader announcements for state transitions.
- **Responsive breakpoints.** No documented breakpoints. Both pages
  hard-code `28rem` / `44rem` max-widths. No tablet / desktop rules.
- **Icon strategy.** Emoji-as-icons is used everywhere but not blessed.
  No `lucide-svelte` policy (the package is installed at
  `web/package.json` line 17, but no route imports it).
- **Animation library.** Two ad-hoc `@keyframes` per page, two
  `.fade-in` declarations on home. No shared motion constants
  (durations, easings, offsets).
- **Component selection rule.** Home uses shadcn `Button`; chat uses
  hand-rolled `.solid`/`.ghost`. No rule about when to extend the
  primitive vs hand-roll.
- **Voice/tone guide.** The literary voice exists in copy but not in a
  reference doc.

---

## 3. Outline for `web/AGENT-UI.md`

This file should be **read before touching any UI** (companion to
DESIGN.md, which lists tokens; this file lists *decisions and patterns*).
Each section: what it covers, who it points at, why an agent needs it.

```
web/AGENT-UI.md — Achiyon UI knowledge pack for agents
=====================================================

0. How to use this file
   - Read before any UI work. Pair with DESIGN.md (tokens) and
     AGENTS.md §UI (rules).
   - Two-namespace reality: app.css is shadcn-svelte style, DESIGN.md
     uses semantic names — both are live. The token table in §1 is
     the bridge; never invent a third name.
   - "Zero raw hex in markup" is binding (AGENTS.md §UI). New color →
     new token in DESIGN.md first.

1. Token reference (from app.css)
   - Full table: every token in :root + .dark, every @theme inline
     re-export, the Tailwind class it maps to, the DESIGN.md alias if
     any, and the use case.
   - Call out the duplicates between app.css :root and .dark — the
     duplication is intentional (dark-only), not a bug.
   - The --bg / --bg-inset / --bg-raised / --text-bright / --text-meta
     / --accent-deepest / --accent-pale names from the mockup ARE NOT
     in app.css — if you see them, they're from palette.html and you
     should map them onto the closest live token (or add new).
   - --sigil-user / --sigil-companion declared in DESIGN.md but not
     implemented; sigils currently use FNV-1a hue rotation
     (web/src/lib/sigil.js).

2. Layout primitives
   - Page shell: <main class="mx-auto … h-[100dvh] flex flex-col p-4">
     (chat:228) vs inline max-width: 28rem (home:369). Pick one per
     page; the rule is "mobile-first ≤ 28rem, chat goes wider because
     messages need it".
   - Safe-area: padding `env(safe-area-inset-*)` on bottom rows
     (home:468). iOS notch + Android gesture bar.
   - Stage pattern: flex:1 + justify-content:center for empty/single-
     content pages (home:392–401). Column flow for chat (chat:228).
   - Header: border-bottom 1px solid var(--border) with `flex items-center
     gap-2.5 pb-2`. Or inline h1 + tagline (home:377–390). Pick per page.
   - Panel surface: var(--surface) bg + 1px var(--border) + 8px radius
     + 1rem padding (chat:363–372).
   - Spacing scale (to be ratified): 0.5rem tight · 0.75rem · 1rem ·
     1.75rem · 2rem · 3rem. Never invent a new step.
   - Touch target: min 52px (DESIGN.md). Ghost icon buttons (chat
     header ✎ 📌 ←) violate this — fix when touching them.

3. State matrix (mandatory triple per surface)
   For each surface: loading, empty, error, success, idle. Cells:
     - what to show (text/glyph)
     - what controls remain enabled
     - what fetch (if any) is in flight
     - what the next-action copy is
   Surfaces to enumerate:
   - Wizard step 1 (name + pronouns): loading N/A; empty = blank input
     + disabled Continue; error = saveError visible (.err color)
   - Wizard step 3 (companion choice): empty = two choice cards
   - Wizard step 3b (spark): loading = name suggestName spinner;
     error = soulError hint
   - Wizard step 4 (soul reveal): loading = "the quill moves…" + ✶
     pulse; empty N/A (just-written); error = soulError
   - Home stage 1 (you, no companion): empty → Create companion CTA
   - Home stage 2 (home with companion): idle with Talk + Another
   - Chat header: loading N/A (chatId gates everything); error =
     chatError in header
   - Chat message stream: loading = "the world is responding…"
     placeholder (chat:311); empty = nothing visible (gap); error =
     ⚠ appended to last bubble (chat:162, 174); streaming = cursor ▍
     (chat:298, 305)
   - Character card panel: empty = blank fields, no validation;
     error = chatError in panel header
   - Kept panel: empty = "hover a message → 📌 keep. kept memories
     never decay." (chat:267)
   - World chip strip: empty = strip hidden (chat:278 guard)
   - Composer: loading N/A; disabled while streaming; error = chatError

4. Form UX rules
   - Multi-step wizard: each step's input lives in its own $state; no
     shared bag across steps. Clear on real save (AGENTS-LESSONS.md L14),
     not on cancel.
   - Draft persistence: localStorage autosave for multi-step input;
     clear ONLY after server confirms (home:131–134). Merge-POST
     failure → fall back to empty draft, never hang the wizard
     (AGENTS-LESSONS.md L14).
   - Disabled CTA: Continue button is `disabled` until the field it
     gates on is valid (home:247, 319). Don't gray out with a "why?";
     the visible error or hint explains.
   - Validation timing: validate on submit for cross-field; on blur
     for individual fields (no rule yet — ratify when first password
     field lands).
   - maxlength: 30 for names (home:228, 242, 254, 305), 120 for
     seed lines (home:297). Set maxlength on the input, don't rely
     on backend alone.
   - Single-select chip group: role="radiogroup" + role="radio" +
     aria-checked (home:233–240). NOT aria-pressed (mockup pattern
     was wrong for single-select).
   - Multi-select chip group: role="group" aria-label="…", each chip
     aria-pressed=true|false, block further selects at the max (mockup
     line 211).
   - Field label: uppercase letter-spacing 0.08em, color var(--text-faint)
     (home:605–611).
   - Submit-on-Enter: only if !shiftKey; textarea grows to fit (chat:316,
     481–494).
   - Error voice: short, second-person, suggests a next action. See §8.

5. Accessibility rules
   - Focus: shadcn Button/Input already provide focus-visible ring.
     Hand-rolled inputs must either inherit OR explicitly set
     :focus-visible { outline: 2px solid var(--ring); outline-offset: 2px }
     (chat composer's :focus only sets border-color — needs fix).
   - Keyboard map: Tab through interactive elements top→bottom; ←/→
     for chip groups; Enter on chip selects; Esc on overlay closes.
   - ARIA: every icon-only button has aria-label (home:253, 280, 325;
     chat:230 ← link has none — fix). Every dynamic region has
     aria-live="polite" for non-critical updates (chat error, soul
     reveal). aria-busy on streaming bubble region.
   - Reduced motion: every @keyframes gets a paired
     @media (prefers-reduced-motion: reduce) { animation: none }.
     Sigil pulse (sigil.js:18), cursor blink (chat:472), wizard
     fade-in (home:493, 527) all need it.
   - Color contrast: text on bg ≥ 4.5:1, large text ≥ 3:1. The dim
     grey `#969696` on `#0d0d0d` is ~6.8:1 (pass); `#757575` on `#0d0d0d`
     is ~4.7:1 (passes AA for body text, not for fine UI labels).
   - Tap target: 52×52 minimum. Smaller only with adjacent text label.

6. SSE / streaming UI states
   - Initial state: empty assistant bubble (chat:147).
   - During streaming: bubble grows per token; blinking cursor ▍ at
     end of bubble (chat:298) AND a tail cursor at the bottom of the
     list (chat:305).
   - Scroll: stream auto-scrolls to bottom on each token (chat:211)
     unless user has scrolled up — preserve scroll position then.
   - Interrupted: stream failure appends " ⚠ stream lost" to bubble
     content (chat:174) + shows chatError hint. Bubble stays rendered.
   - Regenerate: AGENT will need this for future — currently absent.
     Spec it here: button only on completed assistant bubbles, hides
     during streaming, sends the user message again, replaces the
     bubble, scroll preserved. (Cite AGENTS-LESSONS.md L12 for the
     streaming-flag-leak bug to avoid.)
   - Cancel during stream: not implemented; spec it: cancel = stop
     reader (chat:167), keep partial content, set streaming=false,
     show ↻ regenerate button.
   - First-token latency: don't blank the composer; placeholder
     "the world is responding…" (chat:311) — the input stays
     disabled (chat:314) but visible.

7. What NOT to do (drawn from AGENTS.md §UI + AGENTS-LESSONS.md)
   - No raw hex in markup; no new color outside the token table.
     (AGENTS.md §UI; violated in chat at lines 229, 308, 397, 413,
     416–422, 446, 465.)
   - No emoji-as-icons in design surfaces — DESIGN.md anti-cliché
     line 83. Exception: glyphs in hint copy ("📌 keep") and inline
     markers (← ✎ ⚠ ▍) are voice, not UI affordances. Clarify.
   - No hover-only affordances. Wrap in @media (hover: hover) and
     provide a touch equivalent. (DESIGN.md line 78; chat .pin is
     exactly this violation.)
   - No native focus outline suppression without a replacement.
     (chat composer :focus { outline: none } without ring.)
   - No undeclared state vars. (AGENTS-LESSONS.md L10.)
   - No bare fetch without try/catch + .catch() + console.error +
     user-visible message. (AGENTS-LESSONS.md L11.)
   - No streaming flag without finally reset. (AGENTS-LESSONS.md L12.)
   - No on:submit in Svelte 5 — use onsubmit={fn}. (AGENTS-LESSONS.md
     L13.)
   - No :global(@keyframes) inside scoped <style> — declares at page
     scope. (AGENTS-LESSONS.md L13.)
   - No grouped h1, h2 selector — use one. (AGENTS-LESSONS.md L13.)
   - No new top-level doc outside development-docs/{current,research,
     archive}/. (AGENTS.md §8.)
   - No component duplication. Extend shadcn Button/Input/Textarea
     before hand-rolling. (DESIGN.md "extend, don't duplicate".)

8. Voice & tone (drawn from THESIS.md + mockup README)
   - The companion is literary and intimate — lowercase italic hints
     ("the quill moves…", "hover a message → 📌 keep. kept memories
     never decay.", "a name and a spark — that's all we need to
     start."). Adopt this voice for hints, empty states, error
     recovery messages.
   - Error messages: short, second-person, name the failure, name the
     next action. Examples to copy:
     "could not save — tap again"  (home:69, 137)
     "the quill slipped — check connection, tap again"  (home:111)
     "could not reach the server — retry from home"  (chat:55)
     "card not saved — check connection and retry"  (chat:96)
     "could not pin — retry"  (chat:137)
     "⚠ could not reach the narrator — tap ↻ or resend"  (chat:162)
   - Voice rules to enforce:
     - No "Sorry, something went wrong" — say what went wrong.
     - No "Please try again later" — say what to do now.
     - No exclamation marks in error copy. Whisper, not shout.
     - Errors render in .err (var(--destructive)) for blocking,
       .hint (var(--muted-foreground)) for soft.
   - Stage / display copy is normal case. Hints and errors are
     lowercase. Buttons are sentence case ("Continue", "Write their
     soul", "Meet them").

9. Golden examples
   Point at the existing files a future agent should read as canonical:
   - web/src/routes/+page.svelte — full wizard, all 4 steps, sigil
     placement, primary CTA, choice cards, error banners. The most
     recent UI work; closest to current design intent.
   - web/src/routes/chat/+page.svelte — chat layout, streaming UX,
     message typography, kept panel, world chips, ghost buttons.
     Read for: SSE handling, scroll anchoring, pin/keep UX.
   - web/src/lib/sigil.js + web/src/lib/sigil.test.js — FNV-1a
     avatar helper. Read for: deterministic avatar pattern + tests
     that prove determinism.
   - web/src/lib/components/ui/button/button.svelte — shadcn-svelte
     variants reference. Read for: tailwind-variants API + variant
     naming.
   - web/DESIGN.md — token reference. Read first; AGENT-UI.md pairs
     with it.
   - web/src/app.css — actual token block. Read second; trust this
     over DESIGN.md when they disagree.
   - development-docs/archive/mockups/onboarding-v2/onboarding.html —
     the click-through prototype. Read for: intended flow, copy,
     screen transition style; not for the accent color (#9e69d3 in
     the mockup ≠ #7c3aed in app.css).
   - development-docs/archive/THESIS.md — product soul. Read for:
     voice, three pillars, "the loop".
   - AGENTS.md §UI + AGENTS-LESSONS.md §Frontend — read both.
```

---

## 4. Five highest-value things to write FIRST if we can only do part now

If only part of the file can land before the auth-page agent starts,
these five sections buy the most consistency per line written:

1. **§7 What NOT to do** (~30 lines, list of prohibitions). Highest
   leverage: it stops the next agent from re-introducing bugs we
   already paid for (L10 undeclared state, L11 bare fetch, L12
   streaming lock, L13 runes gotchas, hover-only pin, raw hex in
   markup). Even a bad agent who skips §1–§6 will catch most of these.

2. **§3 State matrix — at least the chat surface** (~40 lines, table
   with loading/empty/error/streaming/interrupted/regenerate). The
   chat is the most complex surface, and the AGENTS-LESSONS.md L12
   streaming bug is the worst kind of state leak. Auth will need its
   own state matrix later, but the chat one is the proof-of-pattern.

3. **§1 Token reference table** (~50 lines, single source-of-truth
   bridge between DESIGN.md and app.css). Stops the next agent from
   inventing `--bg-deepest-2` or using `#262626` again. Already half-
   exists in DESIGN.md — just merge it with the actual `app.css`
   exports and the `@theme inline` Tailwind class names.

4. **§8 Voice & tone** (~20 lines, copy rules + 5 example error
   messages). The current voice is inconsistent (home says "the quill
   slipped", chat says "could not reach the narrator"). Without this,
   auth pages will invent their own voice and the product will feel
   like three apps. Voice is cheap to write and impossible to retrofit.

5. **§6 SSE / streaming UI states — interrupted + regenerate** (~25
   lines, with cancel). The L12 streaming-lock bug is the single
   biggest recurring risk in this codebase, and the existing chat
   page has no regenerate button at all. Writing this section now
   forces the auth-time agent (and the next chat-feature agent) to
   design for it from day one instead of bolting it on.

**Order to write:** §7 → §1 → §8 → §6 → §3. §7 is the lowest-effort
highest-payoff; §3 is highest-effort and can wait for after auth
ships.

---

## Appendix — file inventory cited

- `/Storage/Git/achiyon/web/DESIGN.md` (84 lines)
- `/Storage/Git/achiyon/web/src/app.css` (118 lines)
- `/Storage/Git/achiyon/web/src/routes/+layout.svelte` (9 lines)
- `/Storage/Git/achiyon/web/src/routes/+page.js` (3 lines)
- `/Storage/Git/achiyon/web/src/routes/+page.svelte` (769 lines)
- `/Storage/Git/achiyon/web/src/routes/chat/+page.js` (2 lines)
- `/Storage/Git/achiyon/web/src/routes/chat/+page.svelte` (521 lines)
- `/Storage/Git/achiyon/web/src/lib/sigil.js` (20 lines) + test (5 cases)
- `/Storage/Git/achiyon/web/src/lib/utils.ts` (cn helper)
- `/Storage/Git/achiyon/web/src/lib/components/ui/{button,input,label,radio-group,textarea}/`
- `/Storage/Git/achiyon/web/components.json` (shadcn-svelte, new-york, neutral base)
- `/Storage/Git/achiyon/AGENTS.md` (253 lines, esp. §UI line 151–159 + §Frontend 161–168)
- `/Storage/Git/achiyon/AGENTS-LESSONS.md` (154 lines, esp. L10–L14)
- `/Storage/Git/achiyon/development-docs/archive/THESIS.md` (62 lines)
- `/Storage/Git/achiyon/development-docs/archive/mockups/onboarding-v2/{onboarding,palette}.html` + README
