# Achiyon `/settings` + 2FA + Registration — Adversarial Review (Round 1)

**Scope:** attack the planned UX for `/settings` (2FA enroll / disable / sign-out) and registration gaps for a dark, mobile-first, SvelteKit 5 SPA. Round 1 of 3. No code in this document — findings and concrete fixes only.

**Source of truth read:** `web/AGENT-UI.md`, `web/DESIGN.md`, `web/src/lib/auth.svelte.ts`, `web/src/routes/login/+page.svelte`, `server/src/auth_api.rs` (2FA endpoints), `web/package.json`.

**Authoritative spec notes that bound the fixes:**
- Auth is Bearer + httpOnly grant cookie + double-submit CSRF (`achiyon_csrf` → `X-CSRF-Token`).
- Setup **does not enable**; `enable` is a separate step that verifies a live code. `setup` **overwrites** any pending secret on the user row.
- `disable` requires `{ code }` if currently enrolled, no body required otherwise.
- No QR library is currently a dependency. Per AGENT-UI §9, dependencies need a justification; a ~3 KB in-tree QR encoder (or `qrcode` npm) is the only path that keeps the bundle slim without breaking the rule.
- Tokens: dark-only, true-neutral greys + purple accent, serif body, ≥52 px touch targets, copy in lowercase / no-blame / repo voice.
- SPA: there is no SSR for `/settings` (post-login route), so anything requiring `document` must run after mount.

Findings are ranked top-to-bottom in the order they must be fixed.

---

## [BLOCKER] 2FA setup stores a pending secret on every call — re-clicking "set up" silently rotates the secret and bricks the previous QR

**Problem.** `POST /api/auth/2fa/setup` always overwrites `user.totp_secret` with a new value (server/src/auth_api.rs:357-378). If the user starts enrollment, sees the QR, then re-clicks "set up" (because the screen looked stale, because they navigated away and back, because the QR didn't scan cleanly), the previous secret is gone. The authenticator app on their phone still holds the *old* secret and will forever produce codes that fail `enable`. There is no UI affordance to detect or recover from this.

**Worse:** the endpoint stores the secret *immediately*, even before any code is verified. The login-2fa path already reads this column (`server/src/auth_api.rs:195,242-254`), so a half-enrolled user is treated as `totp_secret IS NOT NULL` at next login — but `twofa_enabled` is implicit, not a stored boolean, so the server's "is 2FA on?" logic is *whatever the column value is*. Re-reading `auth_api.rs:354-356` confirms: enforcement = "totp_secret present AND twofa_enabled = true" — and `twofa_enabled` is not written anywhere yet, so 2FA is **never enforced** even after a successful `enable` if the row only stores the secret. (The comment claims it is, but the code does not.) This is a separate latent bug; the UI must not ship on top of it.

**Concrete fix.**
1. Treat the setup response as **idempotent per enrollment session**: only call `/setup` once per mount of the settings panel; freeze the QR / secret in component state and never re-request while the panel is open. If the user navigates away mid-flow, on return to `/settings` either resume the pending enrollment (if the backend reports one) or start fresh — never silently rotate.
2. Surface a "this secret will be discarded if you leave" hint under the QR.
3. Add a backend contract gap to the round-1 punchlist: confirm whether `twofa_enabled` is meant to be a separate column and whether `setup` should NOT persist the secret until `enable` succeeds. The UI must reflect whatever the final contract is; do not build the screen assuming current behavior.

---

## [BLOCKER] QR-on-mobile is a known dead-end — the entire flow must collapse on coarse pointers

**Problem.** This is a mobile-first app. The standard "scan this QR with your authenticator app" pattern is useless when the user is *on the phone they would scan with*. Confirmed in current literature: QRAuth's web-component docs explicitly call out the "QR on a phone is a dead-end" trap and switch to a `Continue with QRAuth` CTA on `(pointer: coarse) and (hover: none)` devices. The plan as briefed ("QR code display on mobile") will leave a sizeable fraction of users staring at a square they cannot use.

**Concrete fix.**
1. Detect mobile via `window.matchMedia('(pointer: coarse) and (hover: none)')` (with a UA sniff fallback) **at mount**, and on coarse-pointer viewports **do not render the QR at all**. Render the manual-entry fallback as the primary surface: large monospace `secret` field with group-by-4 spacing (e.g. `JBSW Y3DP EHPK 3PXP`), a single-tap copy button, and an "I added it to my authenticator — continue" CTA that opens the verify step.
2. On desktop, render the QR **and** a small "Trouble scanning? Enter the code manually" disclosure that expands into the same manual-entry surface as mobile.
3. The QR encoder (when shown): use SVG, not canvas — SVG is crisp at any DPR, accessible (`<title>` for the otpauth label), and trivial to size responsively. If a library is added, `qrcode` npm (`QRCode.toString(url, { type: 'svg' })`) is the standard pick. If the AGENT-UI §9 rule blocks a dep, a 2-3 KB in-tree QR encoder is fine — there are MIT-licensed minimal ones that fit in one file.
4. Render the QR with sufficient quiet zone (≥4 modules) and high-contrast foreground/background using the existing dark tokens. Do not animate it.

---

## [BLOCKER] Verify-step is the only barrier to account takeover if enable succeeds — needs code-attempt feedback, lockout awareness, and rate-limit UX

**Problem.** `/enable` verifies a TOTP code and turns 2FA on. The plan must include (a) what the user sees when their first code is wrong (clock skew on the phone, entered 30 seconds too late, mistyped), (b) what happens after N failures, and (c) how the success state is shown. From `auth_api.rs:387-397` and the current `/login` code, the existing error path is just `"invalid code — 2FA not enabled"` — that copy will appear in the enroll flow too, but here it has different semantics (the secret has not been "enabled" yet). Conflating those two contexts will mislead users.

**Concrete fix.**
1. Verify step copy must distinguish enrollment-failure from login-failure. Suggest: "code didn't match — make sure your phone clock is set to automatic, and that you're entering the current code (it rotates every 30s)."
2. Show the **next code countdown** (a thin progress bar or `00:24` mono digits ticking) so the user knows whether they're racing the clock. Pure UX; do not show the actual code.
3. Show a "try a new code" affordance after every failure (auto-clear the input, focus it, leave focus trapped there until success). The current 2FA login input is already 6-digit auto-submit-capable; reuse the pattern.
4. On success, do **not** auto-redirect. Show a confirmation state with explicit "2FA is now on" and a single "done" CTA that returns to `/settings`. The plan needs an intermediate success state — otherwise the user has no way to know it actually worked, and there's no place to show backup codes (see next finding).

---

## [BLOCKER] No backup / recovery codes in the design — users who lose their phone lose the account

**Problem.** The briefed plan covers enroll, disable, sign-out. It does not cover recovery from a lost phone. With no backup codes and no `disable` path that does not require a current code, a phone-loss event = permanent account lockout. This is the single biggest 2FA UX failure; missing it in round 1 is a blocker.

**Concrete fix.**
1. After successful `enable`, generate ~10 single-use backup codes (server-side; treat them like `totp_secret` in storage: hashed at rest). Show them **once** on a dedicated "save these somewhere safe" screen with monospace, copy-all, and a checkbox "I've stored them" that must be ticked before the "done" CTA enables.
2. Persist them to `/api/auth/2fa/backup-codes` (new endpoint, round-2 work) and let the user regenerate from `/settings` (which invalidates the old set).
3. Show a row in `/settings` for "recovery codes" with `last generated <date>` and a `regenerate` destructive action gated by a current TOTP code. The login-2fa path accepts a backup code in lieu of a TOTP code on a separate endpoint — design that as round 2.
4. Until backup codes exist, the disable action must warn "if you lose your phone you will be locked out" — and the registration / enroll screens must surface that warning *before* the user commits, not after.

---

## [HIGH] Pending-enrollment state must be visibly distinct from "not enrolled" on /settings

**Problem.** The brief lists `/settings` sections but not how the UI reflects the three 2FA states (not enrolled / enrolled-pending / enabled). `/setup` writes a secret but does not flip an "enabled" flag. So when the user navigates away mid-enrollment and returns, the panel must either resume the in-flight enrollment (showing the QR + verify step) or treat the row as "not enrolled" and offer a fresh start. The former is correct UX; the latter is the easy-to-implement wrong choice.

**Concrete fix.**
1. Add a server endpoint or piggyback on a new `/api/auth/me` (or extend `tryResume`) to report `twofa: { state: 'off' | 'pending' | 'on', has_recovery_codes: bool }`.
2. Settings panel maps the three states to three different layouts:
   - **off** — single "set up two-factor" CTA, explanation of what it is, no QR.
   - **pending** — show the QR + verify step with a "cancel pending enrollment" ghost button that calls a new `DELETE /api/auth/2fa/pending` (or just an extra `setup`-with-empty-body? — design this with backend in round 2). Crucially: this is *not* the same UI as the fresh off→setup flow.
   - **on** — show "two-factor is on", last-enrolled date, "recovery codes" row (see above), and a destructive "turn off 2FA" section.
3. Never auto-advance the user through enrollment. Stay on the verify step until success or explicit cancel.

---

## [HIGH] Disable-2FA confirmation pattern: a code gate plus a typed-confirmation gate, not just one

**Problem.** Disabling 2FA drops the user's account from `password + TOTP` to `password only`. The plan must pick a confirmation strength that matches the action's destructive weight. The existing `/login/2fa` code input is good but not sufficient alone — a phone-pickpocket who already has the user's session cookie can disable 2FA in 6 seconds with a stolen phone glance. Two factors of friction is the floor for destructive auth actions.

**Concrete fix.**
1. Require a **current TOTP code** (already mandated by the backend if 2FA is on) **plus** a typed-confirmation: the user types their **username** (not "DISABLE", not "confirm" — username is the thing an attacker does not know) into a separate field before the button enables. This is the standard pattern (GitHub, Stripe, 1Password all do one or both).
2. Inline confirmation panel (expand-in-place), not a modal. Modals on dark mobile-first apps hide the underlying context and trap focus awkwardly; an expand-in-place under the "turn off 2FA" row keeps the user oriented and the danger localized.
3. On submit: disable the button until the response lands; show an error inline ("code didn't match — 2FA stays on") that does **not** clear the code field, so a typo can be corrected without re-typing.
4. On success: show "2FA is now off" inline, then collapse the destructive section and replace it with the "off" state from the previous finding. Do not navigate away.
5. Copy must say explicitly what changes: "you'll only need your password to sign in from now on" and "if someone learns your password, they can take your account".

---

## [HIGH] Sign-out must not be the most prominent action on the page

**Problem.** Sign-out is a one-shot, mostly-irreversible action on this device (server expires both cookies; the next visit needs fresh login). It belongs in `/settings`, but if it sits next to "set up 2FA" at the same visual weight, users will tap it accidentally and lose their session mid-task. This is an architectural placement problem, not a confirm-dialog problem — the standard "are you sure?" modal does not protect against the muscle-memory tap.

**Concrete fix.**
1. Sign-out lives at the **bottom** of `/settings`, after all the security-positive actions (2FA, password change when it lands). Visually demote it: secondary surface (`--bg-inset`), `--text-dim` label, no destructive red unless hovered. Per DESIGN.md the only saturated color is purple — use `--text-dim` and let the action speak for itself.
2. Confirmation is **inline expand-in-place** (consistent with disable-2FA), not a `confirm()` dialog. Browser `confirm()` is jarring on mobile, breaks the dark-first design language, and is being deprecated by some browsers for cross-origin iframes anyway.
3. No typed-confirmation required for sign-out (it is recoverable — log back in). A single tap on "sign out" → confirm panel → "sign out" CTA is enough.
4. After successful logout: clear any in-memory state (`auth.token`, `auth.username`, pending 2FA enrollment state), navigate to `/login`. Do not leave the URL as `/settings`.

---

## [HIGH] Registration lacks server-side username feedback that the UI can render — design must accommodate "username taken" without a real-time check

**Problem.** Current register endpoint returns 201 or an error. There is no `GET /api/auth/check-username?name=...` style endpoint, and adding one is a separate concern. The naive plan will probably skip the availability question and surface only the post-submit failure. That is acceptable, but the UI must:
- Not allow the user to type a 40-char username and only learn "taken" after a full submit cycle.
- Show field-level errors (vs page-level) so the username field can be marked invalid in place.
- Disable the submit button while a submit is in flight (current `login/+page.svelte` does this).

**Concrete fix.**
1. On blur of the username field, **debounced** (250-400 ms) `GET /api/auth/check-username?name=...` if such an endpoint is added (round-2 backend ask). Until it exists, skip — do not invent it as a UI feature.
2. As a lower-effort interim: validate client-side only the **format** (length, charset: `[a-z0-9_-]`, no leading hyphen, case-fold comparison). Show a hint near the field, not an error. Server remains source of truth.
3. The error from the existing `register` path (`{error: ...}` body) must be routed to the **username field** when it indicates a name collision, not dumped into the form-level error slot. Concretely: standardize the error code from the server (`name_taken`, `invalid_name`, `weak_password`) so the client can pick the right field to mark red.
4. **Password confirmation field** is required. Current login page has none. Two accidental-mistype failures (CAPS LOCK, autocomplete inserting wrong value) is the dominant new-account support load — a "confirm password" field with match-validation that only enables submit when both match eliminates 80% of it.

---

## [HIGH] Password strength feedback without a library — use the AGENT-UI copy rules, not zxcvbn

**Problem.** The plan mentions "password strength hint without a library". `zxcvbn` is ~400 KB and the AGENT-UI §9 rule against new deps applies. The naive implementation will either drop strength feedback entirely (then users pick `password123`) or invent a weak heuristic that green-lights `Password1!`.

**Concrete fix.**
1. Server is the strength gate (10-char min on the client; whatever the server enforces is what counts). Client only **mirrors** that floor and shows three tiers via length-only:
   - `< 10` — block submit (red).
   - `10–15` — "ok" (dim).
   - `≥ 16` — "strong" (accent-pale).
2. Do not attempt character-class heuristics; they mislead more than they help, and they are wrong about passphrases.
3. Add a single italic helper line under the password field: *"longer is better. a 4-word phrase beats a complex short one."* This is the current OWASP / NIST guidance and matches the repo voice.
4. Add a `show password` toggle (eye icon). Mobile users mistype constantly; the cost of showing it briefly is far less than the support cost of a typo. Standard accessibility: `aria-pressed` on the toggle.

---

## [HIGH] No CSRF protection visible on the cookie-authed register/login endpoints — but the bearer+CSRF helper applies; the bigger risk is a session-fixation gap on first register

**Problem.** `auth.svelte.ts` attaches `X-CSRF-Token` on every POST. The server's `register` endpoint sets the refresh-cookie and the csrf cookie, both on the same response. The plan must respect: (a) the CSRF token in the response is what subsequent writes must echo, (b) there is no `Origin` / `Referer` check documented, and (c) the access token lives only in JS memory — meaning a refresh of the page after register must work.

**Concrete fix.**
1. UI must treat the register response as the **single source of truth** for the CSRF token: read `achiyon_csrf` from `document.cookie` after register, not before. The current `csrfToken()` reads it any time; the order-of-operations does not matter for cookie-authed routes that already have a CSRF cookie from a prior session, but for first-ever register it does.
2. After register, **do not redirect through `/login`** — `goto('/chat')` directly. Round-tripping through `/login` will trigger a silent `tryResume`, which races the cookie set. The current login page does `goto('/chat')` immediately on register success (line 35 of login/+page.svelte), which is correct; preserve that.
3. If the user opens `/login` while already authed, the existing `$effect` redirects to `/chat` (line 17-20). Good. Make sure `/register` does the same — currently `/` is the only entry, and the register form lives inside the login page. Document this and do not split register into a separate route unless you also handle the deep-link case.

---

## [MEDIUM] TOTP secret display: monospace, grouped-by-4, copy + clear-after-copy

**Problem.** Showing a 32-char base32 secret as a single run of uppercase is hard to read and easy to mistype into the authenticator app. Showing it as the same single run inside an `<input readonly>` is worse — the user cannot select individual groups.

**Concrete fix.**
1. Display the secret as four groups of four (e.g. `JBSW Y3DP EHPK 3PXP` with non-breaking spaces and visible-but-copiable separators). Use `font-feature-settings: 'tnum' 1` for tabular numerals in the serif stack.
2. One-tap **copy** button next to the secret. After successful copy, change the button label to "copied" for 1.5 s, then revert. Do **not** auto-clear the secret from the screen on copy — the user may need to glance at it twice — but **do** auto-clear it (and the QR) on successful `enable` so a screen-recording or shoulder-surf after enrollment does not retain it.
3. After the QR + secret are shown, the verify-step input is the visual focus — do not let the secret persist into the "2FA is now on" confirmation state.

---

## [MEDIUM] Re-setup after disable: the spec says `disable` clears the secret, but the user can re-setup immediately — UI must reflect this without a stale state

**Problem.** After `disable`, the user's row has `totp_secret = NONE`. The next `/settings` visit shows the "off" state. The next `/setup` call generates a fresh secret. There is no cooldown, no audit message. That is fine — but the UI must not display a stale QR from the previous enrollment when the user clicks "set up" again, and it must not double-call `/setup` if the user double-taps the CTA.

**Concrete fix.**
1. Disable the "set up" CTA for the duration of the request; on the existing `busy` rune pattern.
2. On success of `/setup`, **replace** the local QR/secret state with the new values, not append.
3. After disable, the panel must hard-refresh its `twofa` state — call the `/me` endpoint (or whatever reports current state) again on return-to-focus, not rely on the in-memory copy. The session module does not currently track 2FA state at all; this needs a small addition.

---

## [MEDIUM] Error handling on the verify step must not look identical to "code expired" vs "code wrong" vs "rate-limited"

**Problem.** `auth_api.rs:395` returns `unauthorized("invalid code — 2FA not enabled")` for any failure during enrollment. If the server rate-limits the verify attempt (or should — see next finding), the client cannot distinguish "you typed wrong" from "you're being throttled" from "your clock is off". The user needs to know whether to wait or to act.

**Concrete fix.**
1. Standardize server error codes: `bad_code`, `clock_skew` (if server can detect ±1 step drift), `rate_limited` (with `retry_after`), `setup_required` (if the pending secret vanished between setup and enable).
2. UI maps:
   - `bad_code` — clear input, refocus, no countdown reset.
   - `clock_skew` — distinct helper text: "your phone's clock may be off. enable automatic time in settings."
   - `rate_limited` — show the `retry_after` countdown as a disabled submit button with "try again in 12s" label.
   - `setup_required` — show an error card: "enrollment expired. start over." with a single CTA that re-calls `/setup`.
3. Until the server emits these codes, the UI must at minimum not silently swallow a 429 — show the body verbatim under the input.

---

## [MEDIUM] No rate-limit affordance on enroll — the UI should not invite brute force on the verify step

**Problem.** The plan does not mention rate limits. The current server endpoint accepts unlimited `enable` attempts against a single pending secret. An attacker with a stolen session cookie can guess a 6-digit code in ~minutes if no throttle exists.

**Concrete fix.**
1. Round-2 server work: rate-limit `enable` (e.g. 5 attempts per 5 min per user, lock enrollment for 30 min on exhaustion). This is a backend concern but the UI must be designed against the contract.
2. UI: the submit button stays disabled until 250 ms after the user stops typing, and a single in-flight request is enforced (no double-submit). The current login/2fa code-input already has the right shape.
3. After a failed attempt, do **not** re-enable submit immediately — wait 1 s of visual feedback (the error line fading in) so the user is forced to read the error.

---

## [MEDIUM] Mobile keyboard on the 6-digit code input — must be numeric, not full keyboard

**Problem.** Current `login/+page.svelte:64-72` already uses `inputmode="numeric"`, `pattern="[0-9]*"`, `autocomplete="one-time-code"`. Reuse this pattern verbatim on the enroll verify step — do not re-design it. But: also ensure `enterkeyhint="done"` so the keyboard shows a "done" key, not "return", on mobile.

**Concrete fix.**
1. Mirror the login-2fa code input byte-for-byte on the enroll verify step. Same classes, same pattern, same `autocomplete`.
2. Add `enterkeyhint="done"` on both.
3. Auto-focus the input on mount of the verify step (the user just scanned a QR; their thumb is already near the input).
4. If the input fails HTML5 validation (non-digits slipped in), do not submit; show "digits only" inline.

---

## [MEDIUM] The `name` field label in register is confusing — `username` is the term the rest of the app and the backend use

**Problem.** `login/+page.svelte:92` labels the field `name`, but `auth.svelte.ts:60` and `auth_api.rs` use `username`, and the otpauth URL the user sees in their authenticator will say `username` or the user-chosen name. Mismatch causes confusion on the enroll screen ("which one? the display name or the login name?").

**Concrete fix.**
1. Standardize the label as `username` in the UI everywhere — register, login, settings.
2. The otpauth URL sent to the authenticator app should use `username` as the account label (per the spec, `otpauth://totp/<issuer>:<username>?secret=...&issuer=<issuer>`). Backend `twofa_setup` passes `uname` to `build_totp(uname, ...)` already; verify the issuer prefix is also `achiyon` (or a configurable service name from env) so the user sees "achiyon / username" in their authenticator, not just a bare username. The current code at `auth_api.rs:357-377` does not set an issuer explicitly — confirm what `get_url()` produces with `username` only.

---

## [MEDIUM] Information architecture for a minimal /settings page — what belongs, in what order

**Problem.** The brief asks for an IA but does not pin one. A naive IA puts every action at the same weight, with destructive actions adjacent to safe ones. This is an architectural decision that, once shipped, is hard to restructure.

**Concrete fix.** Section order, top to bottom:
1. **Account** — username (read-only), member-since date (if backend exposes it). No edit affordances yet.
2. **Security** — 2FA section (state-driven: off / pending / on, see HIGH finding above). Placeholder for "change password" with a "coming soon" dim row, not a dead button.
3. **Sessions** — current device (this browser), last-active. No "sign out everywhere" yet — that is a future endpoint.
4. **Sign out** — visually demoted, bottom of page, expand-in-place confirm. See HIGH finding above.

Rules:
- No raw hex, no color outside DESIGN.md tokens.
- No nested accordions deeper than one level. Each section is its own `<section>` with a serif `<h2>` at 1.1 rem.
- Destructive actions live inside their parent section, not in a shared "danger zone" footer — that pattern hides them from context. The "sign out" row is the *only* destructive action that lives at the page root, because it is the only one that does not require a section's positive counterpart.
- Every row that toggles state must show a `last changed <relative date>` in `--text-faint`.

---

## [MEDIUM] Settings page route guard — must respect the existing session gate, not duplicate it

**Problem.** The current `+layout.svelte` (per the B6 frontend PR merged into main) gates authenticated routes. `/settings` is post-login, so it must rely on the existing `tryResume` + redirect logic, not reimplement it.

**Concrete fix.**
1. `/settings` does **not** call `tryResume` itself — the layout does. The page only reads `auth.authed` and `auth.username`.
2. While `auth.busy` is true on first paint, render a single full-bleed skeleton (one row of `--bg-inset`, no spinner — design language is calm, not busy). Once `authed` resolves true, render the page. If it resolves false, the layout should redirect to `/login`; `/settings` must not have its own redirect.
3. The settings page must **not** read the access token. It uses `api()` from `auth.svelte.ts`, which already attaches the bearer. The bearer stays in memory.

---

## [LOW] otpauth URL issuer prefix should be consistent with the service name

**Problem.** The current `build_totp(uname, secret)` in `auth_api.rs:260` constructs a TOTP without an explicit issuer — the resulting otpauth URL has `<uname>` as the label only. In an authenticator app alongside other services, this is anonymous.

**Concrete fix.**
1. Backend round-2: add an `issuer` argument (e.g. `Issuer = "achiyon"`, or pulled from an env var `OTPAUTH_ISSUER`). The resulting URL: `otpauth://totp/achiyon:<username>?secret=<b32>&issuer=achiyon`. Per the Google Authenticator wiki, having issuer in both the label prefix and the `issuer` parameter is the recommended interoperability pattern (old GAuth versions ignore the parameter; new versions prefer the parameter).
2. UI: the QR must visibly encode the issuer (it does, via the URL). The settings page does not need to render the issuer separately, but the copy under the QR should say "this will appear in your authenticator as `achiyon / <username>`".

---

## [LOW] Accessibility — code input must announce errors via `aria-live`, not by re-rendering the input

**Problem.** Current login/2fa page uses `role="alert"` on the `form-error` paragraph. Good. The enroll verify step must do the same, and the countdown ticker must use `aria-live="polite"` (not assertive) so screen reader users hear it without it interrupting the error message.

**Concrete fix.**
1. Reuse the existing `form-error` pattern.
2. The countdown ticker is a `<span aria-live="polite" aria-atomic="true">`.
3. The QR's `<svg>` has `<title>two-factor QR for achiyon / <username></title>` so assistive tech sees something meaningful; an empty alt is worse.
4. Color is never the only signal — every state change also changes copy. (Per DESIGN.md greys are neutral, which means relying on color alone is a real risk.)

---

## [LOW] `prefers-reduced-motion` — countdown ticker and any QR pulse must disable

**Problem.** DESIGN.md says "every animation needs a `prefers-reduced-motion` disable". The countdown bar is a motion surface; if any QR entrance animation is added later, it must respect this. Easy to forget.

**Concrete fix.**
1. The countdown ticks via CSS transition on `width` or a CSS variable driven by a `setInterval`. Wrap the transition declaration in `@media (prefers-reduced-motion: no-preference)`. In `reduce`, render the bar as a static "next code in ~30s" with no animation.
2. Document this constraint in `web/AGENT-UI.md` §Motion if it is not already there.

---

## [LOW] Logout on tab close — no `beforeunload` prompt; do not add one

**Problem.** The plan must decide what happens if the user closes the tab mid-enrollment. Some apps add a `beforeunload` warning. For a chat app, that warning is hostile and inconsistent (it does not fire on mobile back, only on desktop tab-close). Don't add it.

**Concrete fix.**
1. No `beforeunload` handler anywhere. Closing the tab silently discards the pending enrollment; the next visit to `/settings` shows the resumed / fresh state per HIGH finding above.
2. Document the discard-on-navigate behavior under the QR ("if you leave this page, this secret will be discarded and you'll need to start over").

---

## [LOW] Sign-out copy must use the repo voice — "sign out", not "log out" or "end session"

**Problem.** DESIGN.md and the existing login page use "sign in" / "register". Sign-out must be "sign out" — same family, lowercase, no jargon ("log out" is jargony, "end session" is corporate). The server endpoint is `/api/auth/logout`, but the UI label is its own concern.

**Concrete fix.**
1. UI label: `sign out`. Always.
2. Inline confirm copy: "sign out of achiyon on this device? you'll need to sign in again to use it."
3. Success state (brief, inline): "you're signed out" — then navigate to `/login` after 600 ms (or on user tap of an explicit "go to sign in" CTA — pick one and be consistent).

---

## Round-1 summary — what must change before any code is written

| # | Severity | One-line fix |
|---|---|---|
| 1 | BLOCKER | setup must not silently rotate; fix the pending-secret handling before shipping the panel |
| 2 | BLOCKER | QR is a dead-end on mobile — collapse to manual entry on coarse pointers |
| 3 | BLOCKER | verify-step needs distinct copy from login-failure + a countdown |
| 4 | BLOCKER | no backup / recovery codes in design — add them or the whole feature is hostile |
| 5 | HIGH | three states (off / pending / on) on /settings, with distinct layouts |
| 6 | HIGH | disable-2FA: TOTP code + typed-username confirmation, inline expand |
| 7 | HIGH | sign-out at page bottom, inline confirm, no destructive red |
| 8 | HIGH | registration: confirm-password field, error-code routing, format hint |
| 9 | HIGH | password strength: length-only tiers + a passphrase hint, no library |
| 10 | HIGH | CSRF / register / redirect — use the existing helper, don't reinvent |
| 11 | MEDIUM | secret display: monospace, grouped-by-4, copy button, auto-clear on enable |
| 12 | MEDIUM | re-setup after disable: replace state, do not append |
| 13 | MEDIUM | distinct error codes for bad-code / clock-skew / rate-limited / setup-required |
| 14 | MEDIUM | rate-limit affordance on enroll verify — design against the contract |
| 15 | MEDIUM | numeric keyboard + enterkeyhint on verify step |
| 16 | MEDIUM | label the field `username` everywhere, not `name` |
| 17 | MEDIUM | IA: account → security → sessions → sign-out, no deep accordions |
| 18 | MEDIUM | route guard: rely on layout's `tryResume`, do not duplicate |
| 19 | LOW | otpauth URL must include `issuer=achiyon` in both label prefix and parameter |
| 20 | LOW | accessibility: aria-live on countdown, `<title>` on QR svg |
| 21 | LOW | `prefers-reduced-motion` disables countdown animation |
| 22 | LOW | no `beforeunload`; document the discard-on-navigate behavior |
| 23 | LOW | "sign out" copy, lowercase, repo voice |

## Open questions for round 2 (not blockers, but answers needed before round 2)

1. Is `twofa_enabled` a real column on the user row, or is the comment in `auth_api.rs:354-356` aspirational? (Round-1 server audit must resolve this — UI cannot ship on a contract the backend does not implement.)
2. Should `/api/auth/2fa/setup` persist the secret immediately, or only after a successful `enable`? The "pending secret" semantics change significantly depending on the answer.
3. Does the server rate-limit `enable` and `disable`? If yes, what are the windows?
4. Is there a planned `GET /api/auth/me` (or similar) that returns the current `twofa` state, or does `/settings` need a new endpoint?
5. What is the service issuer string for the otpauth URL — hard-coded "achiyon", env-driven, or per-deployment?
