# APP_SPEC.md — Achlys

## Executive Overview

Achlys is a modern, mobile-first AI roleplay chat frontend that replaces SillyTavern. It fixes ST's documented structural failures (silent data loss, monolithic Generate(), mobile freezes, security CVEs, broken tool calling) while introducing features no competitor offers: dynamic character emergence, stateful lorebook activation, and voice RP — all in a multi-user, server-capable architecture.

**Target audience:** RP community members who want a polished mobile experience, self-hosters who want a server+client split, and potential SaaS operators who need multi-user from day one.

**Core differentiator:** Characters that grow themselves. Lorebooks that remember state. Voice RP. Mobile-first. All in one product.

---

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Desktop/Mobile shell | Tauri 2 | 3-10MB binaries, Rust backend shares crates with server, mobile support |
| Frontend | Svelte 5 (SvelteKit, static SPA) | No VDOM, smallest bundles, lowest learning curve, built-in animations/CSS scoping |
| Server | Rust + Axum | Type-safe, shares crates with Tauri backend, async tokio, high concurrency |
| Database | SQLite (embedded/all-in-one) + PostgreSQL (server/SaaS) via sqlx | Same schema, same migrations, one `DB_URL` env var decides. SQLite WAL for desktop, Postgres for multi-user server |
| Audio | WebSocket (getUserMedia → server → Whisper/TTS) | Bypasses Tauri IPC entirely, works local and remote |
| Deployment | Server+client split AND all-in-one embedded | User toggles local (embedded Axum on 127.0.0.1) vs remote (standalone server URL) |

### Shared Rust Crates (server + Tauri backend)

```
achlys-core/        ← shared crate: card parser, lorebook engine, prompt pipeline, macro engine, tokenizer
achlys-server/      ← Axum server binary (standalone or embedded)
achlys-app/         ← Tauri 2 shell (wraps Svelte SPA, optionally spawns embedded Axum)
achlys-web/         ← Svelte 5 PWA (the actual UI, loaded by browser/Tauri/phone)
```

---

## Feature Scope — MVP (Phase 1)

### 1. Chat Interface

- Virtualized message list (1000+ messages, 60fps, no freezes)
- Streaming token-by-token output
- Message editing (user + AI messages)
- Message swipes / regenerate
- Continue generation
- Delete messages
- Markdown rendering (bold, italic, code blocks, images)
- Stop generation mid-stream
- Touch gestures (swipe to delete, long-press for menu, pull-to-refresh)
- Split view on desktop (chat + sidebar)

### 2. Character Management

- Character Card V2/V3 import (PNG with embedded JSON)
- Character Card V2/V3 export
- Character editor (name, description, personality, first message, scenario, alternate greetings)
- Character avatars
- Alternate greetings selection
- Character tags / folders
- Character JSON import (non-PNG)
- Batch import (multiple cards at once, directory scan)

### 3. Chat / Session Management

- Multiple chats per character
- Chat rename
- Chat export (JSON, markdown)
- Chat import (from SillyTavern format)
- Chat folders
- Per-chat settings (model, temperature, system prompt overrides)

### 4. Dynamic Character Emergence (signature feature)

**Architecture:** Background agent runs after each AI message, extracts entities, auto-generates character cards.

- **Character extraction:** AI identifies new characters mentioned in narrative output
- **Card generation:** Auto-create V2/V3-compatible card from extracted data (name, role, species, personality, first impression)
- **Card updating:** Modify card as story evolves (relationship changes, new facts revealed, status changes)
- **Context injection:** Automatically include relevant NPC cards in prompt based on token budget
- **Silent operation:** Cards generate in background, user sees subtle indicator ("3 characters tracked")
- **User control:** Review, edit, delete auto-generated cards in a panel
- **Tool calling integration:** AI calls `create_character(name, traits)` → server creates card via tool calling pipeline

### 5. Prompt Engineering

- Prompt layer system (system, char description, personality, scenario, greeting, world info, chat history)
- Drag-and-drop visual prompt ordering (prompt canvas)
- Token counter per layer + total
- Macro system ({{char}}, {{user}}, {{time}}, {{getvar}}, {{setvar}}, etc.) — ST-compatible
- Author's notes (injectable at configurable depth)
- Prompt presets (save/reload configurations)
- Token budget slider (max context size)
- Per-model prompt formatting (different formats per provider)
- Prompt trace (see exactly what's sent to the AI, per-layer breakdown)

### 6. Lorebook / World Info (with stateful activation)

**Gate system (ST-level + beyond):**
- AND_ANY, AND_ALL, NOT_ANY, NOT_ALL
- Constant entries (always active)
- Probability gates (X% chance to insert)
- Inclusion groups (only one entry per group fires)
- Recursive scanning (activated entry text triggers more entries)
- Recursion levels (grouped, deepest checked after shallower find no matches)
- Sticky (stays active N messages after firing)
- Cooldown (can't reactivate for N messages)
- Delay (won't fire until N messages into chat)
- Min activations (force backward scan until N entries trigger)
- Max recursion steps (cap recursion depth)
- Character / persona filters (3-state: OR/AND/NOT)
- Token budget + priority-based eviction
- Scan depth (configurable message window)

**Stateful activation (signature feature — no competitor has this):**
- Entries can read/write state variables
- Conditional activation based on persistent variables: `activate IF state["met_grimm"] == true`
- Mutually exclusive states: activating Entry B deactivates Entry A's state
- State persists across chat turns
- State machine support: `state = "tavern" → state = "forest"` transitions

**Activation trace:**
- Visual display of which entries fired and why
- Per-entry: matched keys, logic result, state condition result
- Token count per active entry
- Sticky/cooldown/delay remaining turns displayed

**Lorebook management:**
- Multiple lorebooks per chat
- Global lorebooks (attach to all chats)
- Per-character lorebooks
- Per-persona lorebooks
- Lorebook import from ST format
- Lorebook editor with live activation preview

### 7. AI Provider Integration

- OpenAI-compatible API (GPT-4, GPT-4o, etc.)
- Anthropic (Claude models)
- Google (Gemini models)
- OpenRouter (100+ models via one API)
- Local (Ollama, LM Studio)
- BYOK (user provides own API key)
- API key encryption at rest (encrypted with user password, never plaintext)
- Per-model settings (temperature, top_p, max tokens, frequency penalty, etc.)
- Streaming support (token-by-token)
- Custom endpoints (any OpenAI-compatible URL)
- Model-specific prompt formatting (chat completions vs messages API vs raw)

### 8. Tool Calling (function calling)

- AI can call functions during generation
- Built-in tools:
  - `create_character(name, traits)` → creates dynamic NPC card
  - `update_character(id, fields)` → updates existing card
  - `set_state(key, value)` → writes to stateful activation system
  - `get_state(key)` → reads from stateful activation system
  - `roll_dice(sides, count)` → dice roll
  - `search_lorebook(query)` → search lore entries
- Custom tools (user-defined functions with JSON schema)
- Tool results injected back into conversation
- Streaming-compatible (tool calls detected mid-stream)

### 9. Context Management

- Sliding window (keep recent N messages)
- Token budget display (used / total before sending)
- AI summarization (old messages summarized into compressed block)
- Summarizer extracts key facts for dynamic character system
- Database-backed sessions (all messages in SQLite, no file-only storage)
- Auto-save on every message (no manual save, no data loss)
- Summarization trigger configurable (every N messages, or on user demand)

### 10. Voice RP (TTS + STT)

**TTS (text-to-speech):**
- AI reads messages aloud
- Server-side TTS engine (Edge TTS, OpenAI TTS, or custom)
- Per-character voice selection
- Audio streamed from server via WebSocket
- Played via Web Audio API in frontend
- Auto-read toggle

**STT (speech-to-text):**
- Voice input via getUserMedia
- Audio streamed to server via WebSocket
- Server-side STT (Whisper, Deepgram, or custom)
- Transcribed text appears in input field
- Push-to-talk and continuous modes

**Architecture:**
```
MIC:  WebView (getUserMedia) → WebSocket → Axum server → Whisper/Deepgram → text
TTS:  Axum server (TTS engine) → WebSocket → WebView (Web Audio API) → speaker
```
Both bypass Tauri's invoke() IPC entirely. Same code path for local (127.0.0.1) and remote.

### 11. Persona Management

- Create user personas (name, description, pronouns, avatar)
- Quick-switch persona from chat header
- Per-persona lorebooks
- Persona appears in prompt as {{user}} macro

### 12. UI / UX

- Dark / light themes
- Mobile-first responsive layout (bottom sheets, carousels, swipe gestures)
- Settings panel (organized, not ST's chaos)
- Quick toggles for common settings
- Split view on desktop (chat + sidebar/lorebook/prompt canvas)
- Touch gestures (swipe, long-press, pull-to-refresh)
- QR code pairing (desktop generates QR, phone scans to connect to server)
- Keyboard shortcuts (desktop)

### 13. Data & Persistence

- SQLite database (WAL mode for concurrent reads)
- Import from SillyTavern (cards, chats, lorebooks, personas)
- Export to JSON (full backup)
- Export to markdown (human-readable chat export)
- Backup / restore (full data backup)
- Entity revisions (track changes, undo/redo) — Phase 2

### 14. Security

- Authentication on by default (password/token to access app)
- Encrypted API keys at rest (encrypted with user-derived key)
- No path traversal (sanitized file access, no user-controlled paths)
- Multi-user isolation (per-user data, no cross-user access)
- CORS configured for known origins only
- WebSocket auth (token-based, per-session)

### 15. Multi-User

- User accounts (register, login, sessions)
- Per-user data isolation (chats, characters, lorebooks, personas, API keys)
- Shared server mode (multiple users connect to one server instance)
- Admin panel (user management, usage stats)
- Per-user API key storage (encrypted separately)

---

## Phase 2 (Post-MVP)

- Emotion sprites (character expression images that change with mood)
- Message branching / forking (branch conversation at any point)
- Chat search (across all conversations)
- Chat statistics (token count, message count, word count)
- Generation queue (queue multiple requests, process in order)
- Regex scripts (find/replace patterns in AI output)
- Group chat (multiple AI characters in one conversation)
- Context visualization (token tracer, see what's included in prompt)
- Background generation (generate while user continues typing)
- Entity revisions (track all changes, undo/redo)
- Jinja2 templates (advanced conditional prompt logic)
- Long-term memory (entity tracking across sessions, HypaMemory-style)
- Image generation integration (DALL-E, Stable Diffusion for scene images)
- Custom themes (user-created themes)
- Character versioning (branch a character into parallel editable variants)

---

## Phase 3 (Future)

- Sandboxed plugin system (WASM/Deno worker isolation)
- Extension marketplace
- Director / GM agent (AI manages world state, NPCs, plot)
- World state tracking (variables, relationships, inventory)
- Lorebook+ (vector similarity instead of keyword matching)
- Generation type triggers (fire lore only on specific generation types)
- @@activate / @@dont_activate decorators
- Mobile app store deployment (Tauri mobile wrappers)
- Hosted SaaS option

---

## Non-Goals (explicitly excluded from MVP)

- No Electron, Flutter, React Native, or native Swift/Kotlin
- No Dioxus for v1 (watching as potential future migration path)
- No React (chose Svelte 5)
- No file-only storage (all data in SQLite)
- No plaintext API keys
- No unauthenticated access by default
- No monolithic Generate() function (modular prompt pipeline)
- No extension-in-main-process (plugins sandboxed or not at all)

---

## Open Decisions (to discuss)

1. **License:** ✅ AGPL-3.0 + CLA (decided)
2. **Database schema:** ✅ Decided — schema as proposed, dual SQLite (embedded) + PostgreSQL (server) via sqlx
3. **Deployment model:** ✅ Decided — 1) OCI containers (Podman/quadlet, rootless), 2) NixOS module, 3) Bare binary (all-in-one, SQLite)
4. **Auth method:** ✅ Decided — JWT (15min access + 7day refresh), refresh tokens stored in sessions table for revocation
5. **Summarization model:** ✅ Decided — Separate configurable model for summarizer (default: small/fast), same for dynamic character extraction agent
6. **STT engine:** ✅ Decided — User-configurable, default Whisper local (whisper-rs/whisper.cpp). Deepgram as cloud option.
7. **TTS engine:** ✅ Decided — Fish Audio as default (free model, emotion markers for RP, need to solve API/streaming quirks), Edge TTS as backup. User-configurable.
8. **Character extraction model:** ✅ Decided — Separate configurable model (default: small/fast), same as summarizer
9. **Project name:** ✅ "Achlys" — primordial Greek goddess of the death-mist. Domain: achlys.io (available). Unique, no trademark conflicts.
