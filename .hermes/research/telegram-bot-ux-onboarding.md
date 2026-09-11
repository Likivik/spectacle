# Telegram Bot UX — Conversational Onboarding / Questionnaires / Multi-Step Intakes

Research notes compiled from current industry sources (2024–2026). Workspace
context: this repo builds aiogram-based Telegram bots, so the recommendations
below are written to be directly actionable on aiogram 3.x + Bot API 9.x.

Sources cited inline as `[N]` — see *References* at the bottom.

---

## Core principles (the spine every recommendation hangs off)

- **Buttons over typing.** Telegram users prefer tapping to typing. Mobile
  typing is high-friction; a predefined button is instant and un-typoable.
  Default to inline keyboards; only drop to free-text when the input is
  genuinely open-ended (name, free feedback, a phone number the user
  prefers to type). `[core.telegram.org/bots/features][gramio ux-patterns]`
- **Edit, don't append.** Treat a flow as one morphing message, not a stack
  of new ones. `editMessageText` / `editMessageReplyMarkup` for navigation;
  new `sendMessage` only for events (notifications, results, errors).
  Telegram itself recommends this: *"consider editing your keyboard when
  the user toggles a setting button … this is both faster and smoother than
  sending a whole new message and deleting the previous one."*
  `[core.telegram.org/bots/features]`
- **One micro-commitment at a time.** A step is one question + one decision
  + visible progress. Keep the cognitive load under ~5 buttons / ~4 lines
  per screen; users decide whether to stay inside ~3 seconds of `/start`.
  `[sudonull UX aiogram][gramio]`
- **Value before ask, contact last.** Never lead with a phone-number or
  email request. Give a reason (resource, route, quote), ask one or two
  light qualifiers, *then* request the contact with clear purpose text.
  `[onlytg contact-button][telego lead-funnel]`

---

## 10 concrete recommendations

### 1. `/start` is a hero screen, not a help page
- 2 lines max: what the bot does + one primary action button (e.g.
  `🚀 Start` or `🛒 Open catalog`).
- Optional secondary "How it works" / "Help" button.
- Never list every feature — `/start` is a homepage, not a sitemap.
  80% of users should find their path in one tap.
  `[gramio ux-patterns][telega onboarding 2026]`

### 2. State the question, then offer 2–5 buttons — never both at once
- Lead with a single short question in the message body.
- Then the keyboard. The message answers *why*; the keyboard answers
  *with what*.
- Keep each question to 3–5 options max — more = decision fatigue and
  drop-off. Verbs for labels: "Book demo", "Confirm", "Back". Avoid
  bare "Yes/No" — prefer "Confirm / Cancel".
  `[sudonull UX aiogram][telega quiz bot]`

### 3. Prefer `editMessageText` over `sendMessage` for every navigation step
- One bot message lives and gets rewritten as the user advances through
  the questionnaire.
- Send new messages only for: system events (payment confirmed, file
  received), external notifications, results, errors.
- Pair every callback with `answerCallbackQuery` as the *first line* —
  forgetting it leaves a hanging spinner for ~15 s and users think the
  bot is broken. `[gramio][tucnak editable]`
- Caveat: each message edit counts toward the ~1 edit/sec per-message
  rate limit; coarse progress (`⏳ Step 3 of 5`), not per-event spam.
  `[gramio]`

### 4. Buttons vs free-text — explicit tradeoff matrix

| Need | Use | Why |
|---|---|---|
| Choice from a fixed list | Inline buttons | Clean data, no parsing |
| Confirm / Cancel | Inline buttons (single row) | Faster than typing |
| Toggle a setting | Inline button + edit (✅/⬜) | Edit not send |
| "Other" / free feedback | Free-text with explicit handler | Don't force structure |
| Open URL, channel, Mini App | Inline URL / WebApp button | Native |
| Share phone | Reply-keyboard `request_contact=true` | Telegram-mediated consent |
| Pick a chat/user | Reply-keyboard `request_chat` / `request_user` | Telegram-mediated consent |
| Name, email, company, description | Free-text, validated | Open-ended, low volume |

Mixing is fine: persistent reply keyboard for main nav + inline keyboards
inside each screen — just don't make the user switch mental models
mid-flow. `[pcraft buttons][gramio][telegram bot features]`

### 5. Contact-sharing UX — the consent handshake
- Use a **reply-keyboard** `KeyboardButton(request_contact=True)` for
  phone numbers (Telegram shows a native confirm dialog before sending).
  Inline buttons cannot request contact — that's a reply-keyboard feature
  only. `[teloxide #748][pcraft buttons]`
- Always precede the button with a one-sentence *purpose*:
  > *"To send your demo reminder, please share your phone number. Telegram
  > will ask you to confirm before sending it."*
  Vague copy ("Submit") is the #1 contact-share drop-off driver.
  `[onlytg contact-button]`
- Don't mix too many goals in one screen. If you need phone + email +
  company + budget, do them in sequence, not all at once. `[onlytg]`
- Confirm receipt and next-step SLA immediately: *"Got it — an advisor
  will message you within 1 business day."* `[telego lead-funnel]`
- Compliance: explain *why* + *how used* + *how to stop*; link to a
  privacy policy when regulated. `[onlytg]`

### 6. Keep users engaged through visible progress and micro-wins
- Show progress explicitly: *"Almost there — 2 more questions."*
  `[telego lead-funnel]`
- Tag at every step, not at the end — if the user drops at Q3 you still
  have Q1+Q2 intent data. `[telega quiz bot]`
- Deliver a *value drop* within ~10 seconds of completion (resource,
  route, summary) before asking for the next action. `[telega onboarding 2026]`
- Use the user's name + previous answers to personalize subsequent
  prompts — *"Nice to meet you, Maria! What are you looking for?"*
  `[telego lead-funnel]`
- Always end with a confirmation message that recaps what was received —
  it shows the bot works and the time wasn't wasted. `[telego][botlaunch]`

### 7. Handle drop-off / abandonment explicitly
- Persist state per user (`FSMContext` in aiogram, `ConversationHandler`
  with `persistent=True` in python-telegram-bot) so a restart doesn't lose
  partial answers. `[telega flows][ptb ConversationHandler]`
- Set a `conversation_timeout` (e.g. 30 min) and route to a dedicated
  `TIMEOUT` state. On timeout, **edit the last prompt** to offer a resume
  button rather than letting it look stale. `[ptb ConversationHandler]`
- For inactive users, send at most 1 follow-up nudge (T+24h), and cap
  follow-ups at 2–3 total unless they reply. `[telega onboarding 2026]`
- Honor quiet hours (user timezone), include a `Stop` button, and
  immediately tag `optout` + halt on STOP. `[telega quiz bot]`

### 8. Message hygiene — keep the chat clean
- **Edit-don't-send** for navigation (see #3). `[gramio]`
- Delete temporary notices: send `msg`, wait, `deleteMessage(msg_id)` —
  useful for "Sending…" placeholders, ephemeral errors, debug banners.
  `[telebothost editing]`
- Strip expired choice buttons: when a user picks one, replace the
  keyboard with the next step's keyboard or pass `inline_keyboard: []`
  to remove buttons entirely. `[telebothost]`
- Cap breadcrumb depth with a "🏠 Home" button on any screen ≥2 levels
  deep — don't make the user tap Back three times. `[gramio]`
- Message budget ≤ 4096 chars; keep onboarding messages under ~300 chars
  for scannability. `[telega quiz bot][telega onboarding 2026]`

### 9. Format for scanning — reserve the chat's grammar
- **Bold** for the title only (every-second-word bold = nothing is bold).
- **Blockquote** for descriptive context — eyes jump to the left bar.
- *Italic* for secondary metadata (badges, dates).
- `code` / `pre` for IDs, tokens, URLs the user might copy; pair with a
  `.copy()` button when the value matters.
- Links only for external URLs; **internal nav = buttons, not links.**
- Pick a consistent emoji system and stick with it — Premium custom
  emojis as accents, not everywhere. `[gramio][sudonull]`

### 10. Plan for power-user escape hatches + safety rails
- A global `/cancel` command that resets `FSMContext` and re-prints the
  main menu. Pair with a "❌ Cancel" button in every multi-step screen.
  `[sudonull]`
- Fallback handlers for unexpected input: explain what was expected,
  show a valid example, and offer a button to recover (not a dead-end
  "Invalid input"). `[telesuite][botlaunch]`
- `/help` and an `ℹ️ Help` button reachable from every screen; never
  buried.
- Register a short command list (`setMyCommands`, ≤5 commands) so users
  can discover `/start` and `/help` from the menu — but every listed
  command must also be reachable by buttons. `[gramio]`
- Respect Telegram rate limits for any outbound sequence: 25–90 s
  between new conversations; cap frequency at ~1 automated message /
  12 h per user; warm vs cold account daily DM caps. `[telega quiz bot]`

---

## Pre-ship checklist (derived)

- [ ] `/start` ≤ 2 lines + 1 primary button + optional Help.
- [ ] Every multi-step screen has a Back (and ≥2 levels deep a Home).
- [ ] Every `callback_query` handler calls `answerCallbackQuery` first.
- [ ] Navigation edits the same message; no new sends for nav.
- [ ] Phone/email requests are preceded by purpose copy and followed by
      a confirmation.
- [ ] State persists across bot restarts; timeout has a recovery state.
- [ ] Follow-up sequences have a STOP path and frequency caps.
- [ ] No `sendMessage` walls of text; ≤ ~300 chars per prompt.
- [ ] Every command in `setMyCommands` is also reachable by buttons.

---

## References

1. Telegram Bot Features (official) — `core.telegram.org/bots/features`
2. Introducing Bot API 2.0 (inline keyboards + edit semantics, official) —
   `core.telegram.org/bots/2-0-intro`
3. Gramio — *UX Patterns for Telegram Bots* (button-first, edit-don't-send,
   `answerCallbackQuery`, formatting, command discovery) —
   `gramio.dev/guides/ux-patterns`
4. Telega Blog — *Telegram Bot Onboarding Flow 2026* (5-step blueprint,
   metrics, rate limits, anti-spam guardrails) —
   `telega.to/blog/telegram-bot-onboarding-flow-2026-menu-based-start-sequence`
5. Telega Blog — *Telegram Onboarding Quiz Bot 2026* (3–5 question rule,
   tagging per step, deliverability) —
   `telega.to/blog/telegram-onboarding-quiz-bot-2026-segment-new-subscribers`
6. TeleGo — *Collect Leads in Telegram Without Google Forms* (lead funnel
   steps, button-vs-text conversion, contact-last) —
   `telego.io/blog/collect-leads-telegram`
7. OnlyTG — *Telegram Button to Collect Client Contact Info in 2026*
   (purpose-first copy, compliance, mistake patterns) —
   `onlytg.com/how_to_use_a_telegram_button_to_collect_client_contact_info_in_2026`
8. TeleSuite — *Telegram Bot Design Best Practices* (sequential friction
   reduction, progressive disclosure, vertical sprawl anti-pattern,
   time-to-task-completion metrics) —
   `telesuite.io/blog/telegram-bot-design-best-practices-ux-guide`
9. Papercraft — *How to Choose Buttons for Telegram Bot Flows*
   (inline vs reply, `request_contact`/`request_chat`/`request_user`,
   row limits, truncation on narrow screens) —
   `pcraft.dev/book/buttons`
10. Sudonull — *UX Telegram Bots: Buttons and FSM on aiogram*
    (button counts, verbs, scenarios vs commands, FSM rationale) —
    `sudonull.com/ux-telegram-bots-buttons-and-fsm-on-aiogram`
11. Bitders — *Keyboard Types: Complete Guide to Commands, Inline and
    Reply Keyboards* (hybrid usage strategy, error rates) —
    `bitders.com/blog/telegram-bot-keyboard-types-a-complete-guide-to-commands-inline-keyboards-and-reply-keyboards`
12. BotLaunch Docs — *Bot Design Best Practices* (progressive disclosure,
    onboarding flow, conversational form collection) —
    `botlaunch.io/docs/bestPractices/design`
13. TeleBothost — *Editing Messages* (editMessageText / ReplyMarkup /
    deleteMessage; edit-not-send rationale) —
    `docs.telebothost.com/api-instance/editing-messages/`
14. python-telegram-bot — *ConversationHandler* (states, TIMEOUT,
    persistence, fallbacks) —
    `docs.python-telegram-bot.org/en/v21.3/telegram.ext.conversationhandler.html`
15. Telega (Elixir) — *Conversation Flows* (recovery strategies: retry /
    fallback / cancel / escalate; parallel-step guidance) —
    `telega.hexdocs.pm/0.12.1/docs/conversation-flows.html`
16. Wyu-Telegram — *Proven Inline Keyboard UX Patterns* (≤3 row-per-action,
    4–9 grid, ≥10 carousel; payload byte budgeting) —
    `wyu-telegram.com/blogs/1580/`
17. teloxide issue #748 — *request user's phone number through inline
    keyboard button* (confirming contact-share is a reply-keyboard-only
    feature) — `github.com/teloxide/teloxide/issues/748`