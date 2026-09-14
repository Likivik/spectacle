# Achiyon `/settings` + Registration — UX-flow Adversarial Review (round 3 / 3)

Scope: navigation model, mid-stream SSE hazards, 2FA enrollment state across reloads,
error/recovery copy, registration field UX, mobile TOTP input.
Grounded in the live code at `/Storage/Git/achiyon/web/`, the existing audit
(`/Storage/Git/spectacle/AGENT-UI-AUDIT.md`), the server auth surface
(`/Storage/Git/achiyon/server/src/auth_api.rs`, `auth_user.rs`), and the
2FA-not-yet-built B5 note in `decisions.md`.

The task brief describes files that don't exist yet (`web/AGENT-UI.md`,
`auth.svelte.ts`, `routes/login/+page.svelte`, `routes/settings/...`). This
review therefore audits the **pre-build design space** the next agent will
inhabit, plus the live code that the new pages must interoperate with
(home header gear button, chat SSE state, server `register`/`login` shape).

---

## Severity legend

- **P0** — blocks the feature entirely or ships a state the user can't recover from.
- **P1** — visible failure the user will hit on a common path.
- **P2** — paper cut / consistency break that compounds into distrust.

---

## P0-1. The SSE connection is component-local — opening settings mid-stream kills the generation silently

**What's there now.** `chat/+page.svelte` owns the SSE connection entirely
inside the component: `messages`, `streaming`, `chatId`, `kept`, `card`, the
`ReadableStreamDefaultReader` handle, and the in-flight `idx0` index into
`messages` all live as `$state` on the chat route (`chat/+page.svelte:10–20`,
`141–179`). There is **no global store** — `find /Storage/Git/achiyon/web/src
-name '*.svelte.ts' -o -name '*.store*'` returns nothing. The reader is held
by a local closure inside `send` and only torn down when `done` or
`finally { streaming = false }` runs.

**The hazard.** When the user taps the ⚙ gear on the home page (`+page.svelte:209`),
the existing code merely toggles `settingsOpen` and shows a stub. But the
*new* /settings page will be a separate route (`#/settings`). Navigating away
from `#/chat` while `streaming === true` will:

1. Unmount `chat/+page.svelte` (hash routing replaces the page tree on
   `#/...` change — there is no SPA layout that keeps it alive).
2. Drop the `getReader()` reference. The fetch body stays open server-side
   until the connection is closed or the OS reaps the tab; tokens that were
   in flight at unmount time are lost.
3. The user comes back to `#/chat` — the route guard calls `resumeChat(id)`
   (`chat/+page.svelte:41–45, 65–77`), which **re-fetches `/api/chats/:id/messages`**
   and only restores what was persisted server-side. The partial in-flight
   generation is gone. There is no "you had 142 tokens mid-stream" recovery.

**Concrete fix shape (no code).**

- Lift streaming state to a module-scoped singleton in `web/src/lib/chat.svelte.ts`
  keyed by `chatId`. The reader lives in the store, not the component, so route
  transitions don't unmount it.
- On `#/chat` mount, the page subscribes to that store and re-renders the
  last `messages` snapshot + the cursor + a "stream resumed" pill if a
  stream is still active.
- When the user navigates `#/chat → #/settings`, render settings inside the
  same SPA shell (a stacked panel or a sibling route under the chat layout)
  rather than a true route replacement. The chat header should support an
  "inset settings drawer" mode — same approach iOS Messages uses for
  contact info: chat keeps mounting, settings is layered on top.

If you instead keep /settings as a peer route, you MUST at minimum:
- show a banner at the top of /settings when `streaming === true`
  ("Achiyon is still writing — leave settings and you'll lose the
  unfinished turn unless you wait");
- offer a "wait here" inline view that doesn't unmount chat.

The simplest correct design is the drawer approach. Anything else creates
a data-loss path.

---

## P0-2. Settings entry point is unreachable from chat — but is the only place to disable 2FA

**Where settings "lives" today.** Home page header has the only gear button:
`+page.svelte:209` (`<button class="ghost gear" onclick={() => (settingsOpen = !settingsOpen)}>⚙</button>`),
backed by `let settingsOpen = $state(false)` and rendered inline
(`+page.svelte:212–214`). On chat, the header has `← back`, sigil, `✎` (edit
character card), `📌` (kept memories), and a `think` toggle
(`chat/+page.svelte:229–244`). **There is no settings affordance on the chat
header.**

**Failure path.** The user enables 2FA on home, then opens a chat. They want
to disable it (lost phone, switching apps). There is no entry point to
settings from chat. They tap back (←), land on home, tap ⚙ — but the home
gear button is currently a local `settingsOpen` toggle, not a route link.
Even if you turn it into `#/settings`, the user has to: leave the chat →
go to home → tap ⚙. That's two deliberate navigations while a stream may
be live (see P0-1).

**Concrete fix.**

- Add a settings affordance to the chat header (right-side, ⓘ or ⚙ or
  person-icon). One tap → settings drawer layered over chat (ties into
  P0-1). Never deep-route.
- Keep the home ⚙ as a route link to `#/settings` (full page) so the user
  has a destination when not in chat.
- Define and stick to one rule: gear-icon = "account & device" (2FA, sign
  out, account delete). Header ✎ = "this chat's character card". The
  📌 drawer is per-chat ephemeral state. Don't reuse the same glyph for
  different scopes.

---

## P0-3. 2FA enrollment across reload has no plan — QR + secret in component state will evaporate on every navigation event

**What 2FA enrollment will need.** Standard TOTP enroll: client calls
`POST /api/auth/2fa/setup` → server generates secret, returns
`{ otpauth_url, qr_data_url, recovery_codes[] }`. User scans QR with
phone, types a 6-digit code, client calls `POST /api/auth/2fa/verify { code }`
→ server flips `totp_enabled = true` and returns success.

**The reload/return hazard.** The user's flow on phone:

1. Tap "Enable two-factor" on /settings.
2. QR appears. User opens phone camera → Authenticator app → scans.
3. Authenticator shows a 6-digit code; user switches back to Achiyon to
   type it.
4. **Between step 2 and step 3, the browser tab may be backgrounded.** On
   iOS Safari, backgrounding for ~30s triggers BFCache eviction on return;
   on Android Chrome, an OOM kill; on desktop, the user may have closed
   the laptop. In all three cases the QR + secret are gone on reload.
5. Worse: if Achiyon is PWA-installed, the user may get a fresh browser
   process on resume.

Where can the QR + secret live? Three choices:

- **In-memory `$state` only.** Lose on every reload / page change. Unacceptable.
- **In `sessionStorage`.** Survives reload and back/forward navigation.
  Survives closing the tab on iOS Safari (per Apple docs, sessionStorage
  is kept through tab resume in same session). Does NOT survive PWA kill.
- **On the server, keyed by an enrollment token.** `POST /api/auth/2fa/setup`
  returns `{ enrollment_token, qr_data_url, otpauth_url, recovery_codes[] }`.
  Subsequent `verify` calls send the `enrollment_token`. Server holds the
  secret until verify (with a TTL, e.g. 15 min) or explicit cancel. Then
  QR re-issuance (`GET /api/auth/2fa/enrollment?token=…`) re-fetches the
  same QR with the same secret.

**The third is the only correct design.** Reasoning:

- The QR encodes the secret. If the secret is regenerated on reload, the
  user has to re-scan, and their authenticator may end up with two
  entries (stale + new) — which becomes "which code do I use?" panic.
- It also enables "user navigated away, came back, wants to finish" without
  resetting the enrollment.
- It lets the server invalidate an enrollment if the user cancels, signs
  out, or the TTL expires.
- The recovery codes must be shown **exactly once** and never recoverable
  — they belong on the verify-success screen, not on the QR setup screen.

**Concrete requirements for the next agent.**

- `auth_api.rs` needs `POST /api/auth/2fa/setup` returning
  `{ enrollment_token, qr_data_url (data:image/png;base64,…), otpauth_url,
  manual_secret, recovery_codes[], expires_at }`. Server stores
  `(enrollment_token → { user, secret, recovery_codes_hash, created_at })`
  in-memory or in a TTL'd Surreal table. TTL 15 min.
- `POST /api/auth/2fa/verify { enrollment_token, code }` → flip
  `totp_enabled=true` on user, invalidate token, return success.
- `POST /api/auth/2fa/cancel { enrollment_token }` → drop the pending
  secret (user changed their mind).
- `DELETE /api/auth/2fa` → disable (requires valid access token + current
  TOTP code in body, not just bearer — see P1-3 below).
- The client NEVER holds the secret long-term. It only holds the
  `enrollment_token` for the duration of the enrollment session.

---

## P0-4. Registration + first-login has no 2FA gate, but the threat model in ADR-008 says 2FA is "day one"

`decisions.md:6` says "2FA required from day one, not yet built (B5)". The
current `auth_api.rs::register` (`auth_api.rs:92–122`) accepts any 10+ char
password and returns a working access+refresh token immediately. There is
no flag for `totp_enabled` (the schema doesn't yet have the field — ADR-008
mentions it but no `DEFINE FIELD totp_enabled` is present in the live code).

**The hazard.** When /settings ships 2FA, the registration flow needs to
decide: enroll at signup, or enroll later. The "later" path requires a
logged-in user with a working bearer token to visit /settings — that
already works because /settings lives behind the existing auth gate (the
`AuthedDb` extractor at `auth_user.rs:25`).

But the more dangerous design is: **silent 2FA opt-in** ("we strongly
recommend enabling 2FA after signup") — which research repeatedly shows
gets ignored by 80%+ of users. The settings page must enforce, not nudge:

- On the very first successful registration, the user lands on a "secure
  your account" interstitial that has only TWO buttons: "Enable 2FA" and
  "Skip for now (you can do this in Settings)". No other navigation is
  reachable until they pick one. Skipping logs the choice to the server so
  the system can prompt again on day 7 / day 30 / day 90 (see P1-6).
- "Skip for now" is a real choice, not nag-ware. The user is the customer.

If the threat model is genuine ("account takeover = lost creative work
memories"), the second-best alternative is to ship without a skip and
require TOTP at registration. That decision belongs in ADR-008 amendment,
not in the UI.

---

## P1-1. Mid-stream navigation has no UI affordance, no in-flight indicator, no "go back to the live turn" path

Tied to P0-1, but visible even on chat-only navigation. The streaming
cursor (`▍`, `chat/+page.svelte:298, 305`) only renders at the end of the
message bubble, not in the header. There's no global "Achiyon is writing…"
indicator outside the chat surface.

When the user backgrounds the tab on mobile and returns:

- The browser may have frozen the timer-driven UI updates (Safari iOS
  pauses requestAnimationFrame in background tabs).
- On return, the stream may have completed server-side during the
  background period, but the cursor is still there because no event drove
  a re-render.
- The user sees a frozen cursor with no progress bar, no "tap to load the
  completed turn", no indication that text exists but isn't shown.

**Concrete fix.**

- Header (chat) should show a thin top-edge pulse or a "writing…" pill
  whenever `streaming === true`, regardless of which surface the user is
  looking at (settings drawer included). Tied to the global store from
  P0-1.
- On chat mount, if the server-side message has more tokens than the
  client knows about (compare last `messages[messages.length-1].content`
  length with `GET /api/chats/:id/messages/:msgId` final length), reconcile.
- A "rewind to last completed turn" affordance for the case where the
  stream was abandoned.

---

## P1-2. `signOut` is implied by the brief but has no UI placement, no server endpoint, no token-revocation story

The task says /settings includes "sign out". The audit found no
`/api/auth/logout` endpoint in `auth_api.rs` (only `register`, `login`,
`refresh`). Surreal refresh tokens are single-use (per `auth_api.rs:7`:
"reuse of a rotated-out refresh is rejected by Surreal itself"), but the
*access* JWT is valid for 15 min and the server has no revocation list.

**The hazard.** "Sign out" on the client clears `localStorage` but leaves
the access JWT valid server-side until natural expiry. If the device is
stolen within 15 min, the thief keeps the session. Worse: refresh tokens
are not server-revoked on logout (no endpoint exists), so any tab that
re-opens with the still-valid refresh can mint a new access token.

**Concrete fix.**

- Server: `POST /api/auth/logout` accepts the current access JWT AND the
  refresh token; revokes the refresh grant (Surreal handles via
  `db.invalidate()` on the access — check 3.x docs for the right method);
  responds 204.
- Optional: `POST /api/auth/logout-all` to invalidate all sessions for
  the user — useful for "my phone was stolen" from a desktop session.
- Client: clear `localStorage` + `sessionStorage`; navigate to `#/login`;
  the JWT in flight (if any) is allowed to fail naturally on next API
  call → 401 → redirect.
- The 15-min access window is acceptable trade-off ONLY if logout revokes
  the refresh grant. Without refresh revocation, logout is theatre.

---

## P1-3. Disable 2FA has no "are you sure" + no re-auth, but enabling does — asymmetry invites account-takeover

Standard 2FA UX:

- **Enable:** requires current password + TOTP confirmation at the end.
- **Disable:** requires current TOTP code. Optional: also current password.

If /settings disables 2FA on a single button tap ("Are you sure you want
to remove two-factor authentication?" + Yes), an attacker who has the
session cookie + a one-time passcode-theft moment can permanently remove
the protection. The screen-tap by the user happens under duress (the
attacker tells them to).

**Concrete fix.**

- Disable flow MUST require a fresh TOTP code (not just the access JWT).
- Show the recovery codes as part of the disable confirm step ("you'll
  lose the ability to recover via these codes; if you've used them all,
  generate new ones first").
- Optional: 24-hour cool-down before 2FA actually turns off, with a
  "confirm via email link" gate. The email link is the only defense
  against coercion.

---

## P1-4. Error copy coverage is inconsistent across pages already, so /settings inherits two voices before it ships

`AGENT-UI-AUDIT.md §1.10` documents the existing drift. Same event, different
words:

- Server unreachable (home, persona save): "could not save — tap again"
- Server unreachable (home, soulspark): "the quill slipped — check connection, tap again"
- Server unreachable (home, goChat): "could not open the conversation — check connection, then try again"
- Server unreachable (chat, send): "⚠ could not reach the narrator — tap ↻ or resend"

That's four voices for one event on two pages. /settings will be the third.

Worse: every `chatError` is rendered through the same `.hint` style
(`chat/+page.svelte:246`) — italic, dim, small. A user reading "could not
unpin — retry" at 0.8rem italic dim on a dark background may miss it
entirely.

**Concrete fix.** Before /settings is built, the AGENT-UI.md voice table
must specify:

- Three error severities: `destructive` (red, full opacity, action verb),
  `warning` (italic dim, recoverable), `info` (dim, FYI).
- The exact wording template per failure, per surface. Example for
  /settings 2FA enable:
  - Wrong code: "That code didn't match. Codes refresh every 30 seconds
    — try the current one." (NOT: "Invalid TOTP" — the user knows nothing
    about TOTP.)
  - Code expired (entered on the last second): "The code rolled over
    while you were typing. Enter the new one."
  - Network failure mid-enroll: "Could not reach the server. Your
    enrollment is still active — tap retry." (states the recovery path.)
  - Setup then enable-out-of-order: "Open your authenticator app and
    use the code from the account you just added." (if multiple entries
    exist — see P1-5)
  - Rate-limited: "Too many tries. Wait 30 seconds, then try again."
  - Already enrolled: "Two-factor is already on. To re-enroll, disable
    it first." (with link)

Each surface (login, register, settings, settings/enable-2fa,
settings/disable-2fa, signout, recovery-codes) must enumerate its four-state
matrix (loading / empty / error / success) before the page is coded. The
DESIGN.md token table needs a `--warning` token alongside `--destructive`.

---

## P1-5. TOTP recovery codes UX is missing from the brief — and is the load-bearing feature for lost-phone recovery

When 2FA is enabled, the user is shown ~10 single-use recovery codes
(industry norm: 8 codes, 6 digits each, one-time). The brief specifies
"2FA state + enroll/disable + sign out" but does not mention recovery
codes. Without them, a user who loses their phone loses the account
forever.

**Concrete requirements.**

- Show recovery codes ONCE on the verify-success screen. Force the user
  through a "I've saved these codes" checkbox before the success state
  dismisses.
- Provide a "show codes again" path in /settings that requires fresh
  password re-auth (not just bearer — because if the bearer is
  compromised, codes-again is the second attack vector).
- "Regenerate codes" path that invalidates all old codes and issues new
  ones, again behind fresh TOTP.
- Print-friendly view (CSS `@media print` on the codes screen — a single
  sheet, no nav).
- Never write recovery codes to `localStorage`. They belong in
  human-only memory / a vault.

---

## P1-6. Registration field UX has zero documented behavior — the agent building it will rediscover every decision

The audit (§2.4) explicitly calls out: "Form UX rules. No documented
behavior for: validation timing (on-blur vs on-submit), inline vs banner
errors, disabled-CTA-until-valid vs always-enabled, maxlength feedback,
multi-step draft persistence."

This matters acutely for registration. Defaults the next agent will pick
arbitrarily:

- **Inline validation timing.** On-blur is best for "this field is bad" +
  inline UI feels modern. On-submit is best for "your whole form has
  issues" + avoids the user feeling harassed mid-typing. The current
  home wizard `wizardNext` (`+page.svelte:51–77`) only validates on
  continue (effectively on-submit), with a disabled CTA until valid —
  this is the consistent pattern for the codebase. **Use it for
  registration too.** Don't introduce on-blur validation as a new pattern.
- **Username: collision error vs typo suggestion.** Surreal returns
  `username taken` (`auth_api.rs:118`). The user typing "ada" gets that
  even if the existing one is "Ada_" — case-sensitive uniqueness is fine
  but the error copy should offer "tap to try with digits" or similar.
  Or auto-suggest: "ada → ada2, ada_01, ada_loves_iris".
- **Username vs display name.** `register` takes `username`
  (`auth_api.rs:38–40`); no display name field. The home wizard has
  `wizardName` for the persona (later assigned to `kind: 'persona'` soul,
  not the auth user). Need to decide: is `username` a display name (shown
  in chat header? settings? "signed in as: ___")? Or a true login
  handle? If both, two fields, but server only accepts one. **Pick one
  scope per field. Document it.**
- **Password rules.** Server enforces `>= 10 chars` (`auth_api.rs:100`).
  No upper bound shown to user. No strength meter (zxcvbn or similar).
  No breach check (haveibebeenpwned k-anonymity API). Without strength
  meter, "password must be 10 characters" produces "passwords123" as
  compliance. Either accept that (and document the threat model) or add
  zxcvbn and require score >= 3.
- **Password manager autofill.** The home wizard inputs use shadcn
  `Input` (`+page.svelte:228, 242`). Shadcn-svelte inputs preserve native
  autofill. Good. **For login, register, and 2FA code inputs**, the
  `autocomplete` attributes MUST be set correctly per WHATWG spec:
  - username: `autocomplete="username"`
  - new password: `autocomplete="new-password"`
  - current password: `autocomplete="current-password"`
  - one-time code: `autocomplete="one-time-code"` (iOS/Android will
    autofill from SMS — wrong for TOTP but the browser doesn't know
    that; see P2-2)
- **Double-submit.** Current pattern is `disabled={!valid || busy}`
  (`+page.svelte:247, 319`). Use the same: registration's primary CTA is
  disabled until valid AND after submit until response. Add the `busy`
  state explicitly so the user knows their tap registered.
- **Trim/case handling.** `register` already trims username
  (`auth_api.rs:62`). It does NOT lowercase. So `Ada` and `ada` are two
  different accounts. Decide: either lowercase in `from_req` (recommended
  — usernames should be case-insensitive for user sanity; passwords are
  already case-sensitive), or document the case-sensitivity loudly.
- **Username charset.** 1–40 chars, no other constraint
  (`auth_api.rs:97–99`). No Unicode handling specified. `name` field in
  Surreal `DEFINE ACCESS` may have stricter rules — verify.

---

## P1-7. The "name shown in chat header" is currently the companion, not the user — adding auth will create a "signed in as" placement question

`chat/+page.svelte:232` shows `card.name` (the companion), not the human's
name. There's no "me: Ada" indicator anywhere on chat. With auth
introduced, the user will expect to see their own name somewhere — and
the most natural place is the settings drawer or the chat header's
back-area. Decide before shipping: is the username shown in the chat
header (and if so, where), or only on /settings?

Also: the home stage currently shows the *persona* soul's sigil and
name (`+page.svelte:342–343`: `<div class="sigil big you">…</div><p class="hint">Welcome, {me.name}.</p>`).
With multi-user, multiple personas per user becomes possible. The
relationship between "auth user" and "persona soul" needs a clear rule
that's documented in AGENT-UI.md before the third page ships.

---

## P1-8. The 6-digit TOTP input — IME, paste, autofill, spacing

The live code has no TOTP input. The next agent will be tempted to
hand-roll one. Common failure modes:

- **Numeric keyboard on mobile.** `inputmode="numeric"` triggers the
  number pad on iOS/Android. `type="number"` adds spinbox chrome and
  breaks `maxlength` semantics; never use it for TOTP. Use
  `<input type="text" inputmode="numeric" autocomplete="one-time-code"
  pattern="[0-9]*" maxlength="6">`. The `pattern` and `[0-9]*` together
  force digit-only on keyboards that don't honor `inputmode`.
- **Paste from Authenticator apps.** Some authenticators put a "copy
  code" button. The input must accept paste of 6+ digits and strip
  whitespace (`"123 456"` → `123456`). Some apps paste with a leading
  space from the clipboard; trim.
- **Auto-submit on 6th digit.** Once `value.length === 6`, focus the
  Verify button (or auto-submit if no other field). Don't make the user
  tap Verify after typing the last digit.
- **Visual segmentation.** Many UIs show six single-digit boxes. This is
  nice on mobile where the keyboard is full-width and a single box makes
  the digits cramped. But segmentation breaks paste unless you write a
  custom handler that distributes pasted digits across boxes. Decide:
  one input (paste-friendly, paste-and-go) vs six inputs (UX-clearer,
  paste-fragile). Recommend one input with monospace digit groups
  rendered via CSS `font-variant-numeric: tabular-nums` and a subtle
  letter-spacing.
- **SMS autofill collision.** `autocomplete="one-time-code"` will trigger
  iOS SMS one-time-code autofill. If a user uses SMS-based 2FA anywhere
  else, the wrong code may land in the field. The behavior is correct for
  SMS-based systems and wrong for TOTP — there's no clean fix. Either
  remove `autocomplete="one-time-code"` (and lose autofill from
  SMS-based 2FA users, but those shouldn't be here), or document the
  trade-off.
- **Code expiry mid-typing.** User types 5 digits, code rolls over.
  Visual feedback: when length === 6, kick off verify; if verify says
  "code rolled over", don't auto-clear — the user might still be on the
  same valid code with a small clock skew. Always re-fetch from the
  authenticator after the error.
- **Accessibility.** The input needs `aria-label="six-digit
  authenticator code"` and `aria-invalid` toggled when the server
  rejects. Error message linked via `aria-describedby` to the input.
  Live region (`aria-live="polite"`) announces "Code accepted, two-factor
  is on" / "That code didn't match".
- **Recovery code input.** Same input, longer — `maxlength="8"` for
  8-digit codes (or 10 for the chosen format), accepts hyphens
  ("abcd-1234-efgh"). Strip non-alphanumeric on parse. Different
  `autocomplete` (none — recovery codes are not a credential autofill
  field).

---

## P1-9. Sign-out has no "where do you go after?" — and the existing routes assume a logged-in user

`#/` renders home, which calls `boot()` → `/api/souls` → no auth check
because there is no auth yet. After sign-out, the user expects to land on
`#/login`. The home page must become auth-aware (`AuthedDb`-equivalent
gate on the client: if no token in `localStorage`, redirect to `#/login`
on mount).

**Concrete fix.**

- A layout-level guard (`+layout.svelte`, currently 9 lines and does
  nothing besides import CSS) decides: authed → render child route;
  unauthed → render `#/login`. The home page's existing `boot()` is fine
  for authed users but must not fire on the login route.
- Token refresh on app focus: every time the user returns to the tab,
  attempt refresh-if-stale (silent) so they don't get booted mid-chat.
- Concurrent tabs: same `localStorage` key for the access JWT means two
  tabs both read the same soon-to-expire token. Use `BroadcastChannel`
  to coordinate sign-out across tabs (one tab signs out → all tabs
  redirect to `#/login`).

---

## P2-1. Registration copy collides with the existing wizard — "your name" means two different things

The home wizard asks "What's your name?" (`+page.svelte:224`) referring to
the persona (a `kind: 'persona'` soul, not the auth user). The new
`/register` page will ask for a username that becomes the auth identity.
Two different fields with overlapping vocabulary.

**Concrete fix.** Pick unambiguous wording:

- Register / login: "Pick a username", "Your password". Clear that this
  is for signing in.
- Home wizard step 1: "What should we call you in the stories?" or "Your
  character's name" — make it clear this is a *narrative* name, not a
  login name. Today the wizard says "What's your name?" — fine for an
  unsigned-in flow, wrong once auth is added.

---

## P2-2. Username autocomplete can collide with browser-saved "persona names"

If the wizard persists persona names into `localStorage` (it does —
`boot()` reads them from the server, which keeps them, and the user's
browser may autofill them on the username field based on prior submits),
the user gets weird autofill. `autocomplete="off"` doesn't work —
browsers ignore it on login fields. Use the right `autocomplete` token
(`username` for the auth one, `name` for the persona one).

---

## P2-3. Existing ⚙ stub on home shows "coming with multi-user + worlds" — when /settings ships, this copy lies

`+page.svelte:213`: `<div class="stub">settings — coming with multi-user + worlds</div>`. As
soon as /settings exists, this stub must be replaced (it would otherwise
remain visible when `settingsOpen === true` if the toggle is kept
alongside the route link).

---

## P2-4. Chat header back button has no aria-label; settings buttons must not repeat this mistake

`chat/+page.svelte:230`: `<a class="no-underline text-base" href="#/">←</a>`.
No `aria-label`. A screen reader announces "link, left arrow" — useless.
Every nav affordance on /settings must have `aria-label`: "Back to
chat", "Account settings", "Enable two-factor", "Disable two-factor",
"Sign out".

---

## P2-5. The `think` toggle's `label` wraps the input — won't work for chip toggles on /settings

`chat/+page.svelte:241–243`:

```
<label class="think-toggle …">
  <input type="checkbox" bind:checked={showThink} /> think
</label>
```

Wrapping `<input>` in `<label>` is fine for inline text. For settings
toggles with longer descriptions ("Show reasoning as it streams —
useful for debugging; off for normal use"), the label association
breaks visually. Use `aria-labelledby` + `<label for>` pointing at a
`<span id>` next to the toggle. Same for "Enable 2FA" switch + description
+ link to learn-more.

---

## P2-6. Error banner in chat has no dismissal, persists across re-renders, and accumulates

`chatError` is a single string (`chat/+page.svelte:47`); every error path
overwrites it (`chat/+page.svelte:55, 96, 117, 137, 162, 174`). When
stream fails AND card-save fails AND pin fails, the user sees only the
last one. There's no toast queue, no dismissal, no
"X / dismiss" affordance. `chat/+page.svelte:246` renders it once per
update.

**Concrete fix.** Either a toast queue (transient, dismissable, queue of
3) or an inline error region with explicit "×" — pick one and document
in AGENT-UI.md. /settings must use the same pattern; two error UX
patterns in one app is worse than zero.

---

## P2-7. The `⚙` glyph on home is currently a button without `aria-label`

`+page.svelte:209`: `<button class="ghost gear" onclick={() => (settingsOpen = !settingsOpen)}>⚙</button>`.
A screen reader announces "button, gear emoji". Add
`aria-label="Settings"` (and toggle to `aria-expanded={settingsOpen}`).

---

## P2-8. The home wizard's "could not save — tap again" surfaces as `.hint`, not `.err`

`+page.svelte:67–71`: catch on persona save sets `soulError` (the
poetic-voice variable, displayed via `.hint` at `:322`). The recovery
copy is dim italic — same style as positive hints. The user can't tell
error from "Welcome to your companion" at a glance. The next agent must
not let /settings regress this — every error must use `.err` /
`--destructive`, never `.hint`.

---

## Cross-cutting: write AGENT-UI.md FIRST, then build the pages

The audit found that `web/AGENT-UI.md` does not exist. The decisions
documented in this review (token name usage, voice table per surface,
state matrix per surface, form UX rules, motion rules, accessibility
rules) belong there before any code is written. The current state is
that the home page and chat page have codified different patterns for
the same concepts (three button styles, two fade-in keyframes, two
input styles, two error styles) — the third page will inevitably pick
the wrong one for some concept unless the doc is written first.

The order should be:

1. Write `web/AGENT-UI.md` per the outline in `AGENT-UI-AUDIT.md §3`.
2. Add server 2FA endpoints (`auth_api.rs` + 2FA schema in Surreal).
3. Build `/login` and `/register` with auth state in `lib/auth.svelte.ts`.
4. Build `/settings` as a drawer mounted on `+layout.svelte`, NOT a peer
   route, to avoid the P0-1 mid-stream hazard.
5. Add /settings entry to chat header.
6. Migrate the existing two pages to use the consolidated patterns
   (button = shadcn only; input = shadcn only; one `.fade-in`; one error
   pattern; one `.hint` italic).

---

## Quick severity recap

| ID | Title | Sev |
|---|---|---|
| P0-1 | SSE state is component-local; navigation away drops the stream | P0 |
| P0-2 | Settings unreachable from chat | P0 |
| P0-3 | 2FA enrollment across reload has no design | P0 |
| P0-4 | 2FA opt-in vs required at signup is undecided | P0 |
| P1-1 | No mid-stream UI indicator outside chat surface | P1 |
| P1-2 | No logout endpoint, no refresh-revocation | P1 |
| P1-3 | Disable 2FA needs re-auth, not just confirm tap | P1 |
| P1-4 | Error copy drift will get worse on /settings | P1 |
| P1-5 | Recovery codes missing from brief entirely | P1 |
| P1-6 | Form UX rules undocumented; agent will re-decide | P1 |
| P1-7 | "Me" indicator missing on chat; auth user ≠ persona soul | P1 |
| P1-8 | TOTP input mobile/paste/autofill matrix | P1 |
| P1-9 | No auth gate on existing routes | P1 |
| P2-1 | Registration "name" collides with wizard "name" | P2 |
| P2-2 | Username vs persona-name autocomplete collision | P2 |
| P2-3 | Settings stub copy lies once /settings ships | P2 |
| P2-4 | Chat header back button has no aria-label | P2 |
| P2-5 | `<label>` wrap pattern doesn't scale to settings toggles | P2 |
| P2-6 | Error banner has no dismissal/queue | P2 |
| P2-7 | ⚙ button has no aria-label | P2 |
| P2-8 | Error vs hint styled identically on home wizard | P2 |