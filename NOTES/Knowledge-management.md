# Knowledge-Management Research

Source: buildin.ai exports from `~/Downloads/` — 9 ZIPs analyzed 2026-06-25.

## What's been evaluated

### Notes / Markdown editors
- **QOwnNotes, Zettlr, MarkText, Abricotine, Vnote, Joplin, Typora** (from Markdown_Notes_Editors CSV)
- **Wikis tried & rejected**: Smeagol, Tiki.org, Tiddly, Wiki.js, XWiki
- **VSCode/Codium extensions — full eval (2026-04-21)**:
  - **Best**: Markdown Collapsible Sections (`jayblack388.md-collapsible-sections`), Markdown Inline Editor (`CodeSmith.markdown-inline-editor-vscode` — WYSIWYG text editor modifier), Dendron Markdown Shortcuts (`dendron.dendron-markdown-shortcuts` — context menu + shortcuts)
  - **Maybe**: `remcohaszing.markdown-decorations` (real human), `tanishq-chaudhary.its-markdown-studio` (real, has `/` milkdown), `lwxyfer.new-markdown-editor` (hides marks), `jishii1204.markdown-live-editor` (real, has `/`, fold at headings, but no multi-line actions)
  - **No**: `easonruan.markdown-editor-ultra` (constant autosave), `vikgamov.calliope-md` (todolist autocomplete), `imaken.fractal` (theming only, no buttons), `ShinyaIwasaki.markcanvas` (broken), `chrp.markdown-beautiful-editor` (broken TOC), `masaya.wysiwyg-markdown` + `LawrenceRicher.visual-markdown-editor` (both Vditor — SLOP), `adamerose.markdown-wysiwyg` (corrupts todos), `slashmd.slashmd` (deletes checkboxes), `concretio.markdown-for-humans` (no button for todos, no folds), `1AbhishekPandey.live-markdown` (does nothing), lots of sketchy SLOP extensions
  - **Missing**: multi-cursor edits — none found that support it
- **Current**: Notion (reluctantly)

### Task / Project managers
- **Currently using**: Buildin.ai (flagged "Missing task features")
- **Active contender**: Todoist (passes most criteria)
- **Also tried**: TickTick, Amazing Marvin, Asana, ntask, Taiga.io, MLO3, ClickUp, Chaos Control, Colanode, Docmost, AnyType, Affine, Trilium, AppFlowy, LeanTime, OpenProject, Plane, Focalboard, Orgnise, Vikunja, RedMine, Stacks 2
- **MLO3 flagged**: "very high potential investigate on desktop"

### Sync / E2EE
- Syncthing, Tahoe-LAFS, Seafile, NextCloud
- Encryption: encFS, gocryptfs, cryFS

## Hard requirements (from notes)

### Notes
- WYSIWYG, single pane (no split)
- Tables edit cleanly
- Plain text on filesystem (markdown)
- Attachments in `[filename]_assets/`, deleted with note
- Each note + assets = one transferable artifact
- Sync by external tool (Syncthing / NextCloud / Seafile)
- Hierarchical folders, not tag-based
- No vendor lock-in
- Multi-cursor + `/` command palette + fold at headings

### Tasks
- Mobile fast input w/ duplicate detection + project/task decision help
- Nesting ≥ 3 levels
- Customizable recurrence
- CalDAV / Cal.com integration (Actual or Make)
- Group by top category, see completed for day/week

## Cross-cutting constraints
- FOSS / self-host preferred
- Russian localization + works in Russia
- Plain text > proprietary DB
- ADHD-friendly fast capture
- NixOS + KDE + Android stack

## Gaps in research (resolved)
1. **Obsidian** — evaluated extensively; rejected due to sync friction (Syncthing last-writer-wins, proprietary paid options only, Obsidian Git poor mobile UX). No built-in databases/multi-user.
2. **Logseq** — evaluated; outliner-only format, no WYSIWYG block editor, poor database support.
3. **Silverbullet** — not evaluated (not a contender vs AppFlowy).
4. **TriliumNext** — evaluated in depth (2026-07-10). Impressive feature set but eliminated on 3 core requirements: semantic search removed (v0.95.0), sync is last-writer-wins (not CRDT), single-user only. See [TriliumNext deep dive](#triliumnext-deep-dive-2026-07-10).
5. **Task app FOSS self-host** — resolved by choosing AppFlowy (databases replace AmazingMarvin).

---

## Final Decision: AppFlowy Cloud (self-hosted on erebus)

### Tool comparison (top contenders)

| Feature | Obsidian | SiYuan | AppFlowy | AFFiNE | Anytype | TriliumNext |
|---|---|---|---|---|---|---|
| WYSIWYG editor | ✓ (markdown) | ✓ (block) | ✓ (block) | ✓ (block) | ✓ (block) | ✓ (CKEditor) |
| Databases/views | ✗ (plugins only) | ✓ (limited) | ✓ (4 views, relations, rollups) | ✓ (basic) | ✓ (limited) | ✓ (Table/Board/Calendar, attributes) |
| Multi-device sync | paid / hacky | ✗ (no multi-user) | ✓ (CRDT local-first) | ✓ | ✓ | ⚠ LWW (data loss risk) |
| Offline-first | ✓ | ✓ | ✓ (CRDT) | partial | ✓ | ✓ but conflicts lose data |
| Self-hosted | ✗ | ✓ | ✓ (Docker Compose) | ✓ | ✗ (p2p) | ✓ (single SQLite file) |
| Semantic search | ✗ | ✗ | ✓ (pgvector + LMDB) | ✗ | ✗ | ✗ (removed in v0.95.0) |
| MCP agent access | ✗ | community (mature) | CAREEMER (CRDT editing) | ✗ | ✗ | ✓ (4+ servers, 35 tools) |
| Task management | ✗ | ✓ | ✓ (Board view) | ✗ | ✓ | ⚠ (plugins, fragile) |
| Quick capture (Android) | ✓ | ✓ | ✓ (Quick Notes) | ✓ | ✓ | ✗ (third-party alpha) |
| Multi-user | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ (single-user) |
| Active development | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Markdown export | ✓ | ✓ | ✓ | ✓ | partial | ✓ |

**AppFlowy wins** on: databases + relations, semantic search, MCP agent access (CRDT block editing via CAREEMER), multi-user, Notion-class UI. Only real gap vs Obsidian: mature graph view (not needed — semantic search replaces wikilinks).

### Requirements table

| # | Requirement | AppFlowy status |
|---|---|---|
| **Core** | | |
| 1 | WYSIWYG block editor | ✓ |
| 2 | Databases with views (Table/Kanban/Calendar/Gallery) + relations/rollups | ✓ |
| 3 | Multi-device sync (Android + Linux desktops) | ✓ |
| 4 | Offline-first (CRDT, no conflicts) | ✓ |
| 5 | Self-hosted on erebus (Docker Compose) | ✓ |
| 6 | Agent access (read/write/semantic search) | ✓ CAREEMER MCP + REST API |
| 7 | Quick capture (Android + desktop) | ✓ Quick Notes |
| 8 | Task management (Board view, replace AmazingMarvin) | ✓ |
| 9 | File uploads + rich media | ✓ |
| 10 | Full-text search | ✓ LMDB |
| 11 | Semantic search (vector embeddings) | ✓ pgvector + OpenAI/Ollama |
| **Nice-to-have** | | |
| 12 | Official MCP support | ✓ in progress (PR #348, May 2026) |
| 13 | Multi-user accounts | ✓ |
| 14 | Shared workspaces | ✓ |
| 15 | Version history | ✓ |
| 16 | Markdown import/export | ✓ |
| 17 | AI chat (LLM integration) | ✓ (cloud + local Ollama) |
| **Anti-requirements** | | |
| 18 | Graph view | ✗ (semantic search replaces) |
| 19 | Manual wikilinks | ✗ (not needed) |
| 20 | Block references / transclusion | ✗ (not needed) |
| 21 | Zettelkasten numbering | ✗ (not needed) |

### Architecture on erebus

```
┌─────────────────────────────────────────────────┐
│  erebus (NixOS + Docker Compose)                │
│                                                 │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │ appflowy-   │  │ appflowy-search          │  │
│  │ cloud       │  │ (:4002 semantic vectors) │  │
│  │ (:8000)     │  └──────────────────────────┘  │
│  └─────────────┘                                │
│  ┌─────────────┐  ┌──────────┐  ┌───────────┐  │
│  │ PostgreSQL   │  │ Redis    │  │ MinIO     │  │
│  │ + pgvector   │  │ (cache)  │  │ (S3)      │  │
│  └─────────────┘  └──────────┘  └───────────┘  │
│  ┌─────────────┐                                │
│  │ GoTrue      │                                │
│  │ (auth/JWT)  │                                │
│  └─────────────┘                                │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ CAREEMER appflowy-mcp (Docker)           │   │
│  │ CRDT block-level edit via Yjs            │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  Reverse proxy: Nginx/Caddy via Tailscale      │
└─────────────────────────────────────────────────┘
```

### Migration plan

1. **Phase 1**: Deploy AppFlowy Cloud on erebus + CAREEMER MCP server
2. **Phase 2**: Install desktop clients (traversal, serenity) + Android app
3. **Phase 3**: Migrate buildin.ai notes → AppFlowy (markdown import)
4. **Phase 4**: Migrate AmazingMarvin tasks → AppFlowy Board view
5. **Phase 5**: Deprecate buildin.ai, shut down AmazingMarvin

### Key links

- AppFlowy Cloud deploy: https://github.com/AppFlowy-IO/AppFlowy-Cloud
- CAREEMER MCP: https://github.com/CAREEMER/appflowy-mcp
- AppFlowy MCP OAuth PR: https://github.com/AppFlowy-IO/AppFlowy/pull/348

---

## TriliumNext deep dive (2026-07-10)

### Overview
TriliumNext is a community fork of zadam/Trilium (36K+ GitHub stars). Active development, 435 commits on TriliumDroid alone. Impressive feature set: WYSIWYG (CKEditor), Table/Board/Calendar views, relations, spreadsheets (Univer Sheets, beta), OCR, LLM chat, per-note encryption, ETAPI REST API, single SQLite file deployment.

### Why eliminated

**1. Semantic search removed (v0.95.0)**
- `note_embeddings` table dropped in migration 232
- Embeddings caused sync conflicts — removed entirely
- LLM chat reintroduced in v0.103.0 but **without embeddings**
- Ollama support added for chat (PR #9338) but not for embeddings
- Only FTS5 full-text search available natively (PR #6839, trigram tokenization, 50-100x faster than LIKE)
- External RAG possible via MrDesjardins/trilium-ai (Weaviate) but separate service

**2. Sync is last-writer-wins (not CRDT)**
- Timestamp-based conflict resolution — older changes silently discarded
- Notes can be "recovered" to root when parent structure conflicts (#8639)
- Known data loss scenarios documented (#3600, #8397)
- No real-time sync — manual/periodic pull from central server
- Sync protocol: push/pull entity changes via HTTP, WebSocket for UI updates

**3. Single-user only**
- No multi-user accounts, no shared workspaces
- One sync server serves one user's devices

**4. Android app is third-party alpha**
- TriliumDroid: unofficial, 329 stars, alpha (v0.102.1-alpha16)
- Capacitor wrapper around web UI — not native
- No Quick Notes / fast capture / share-to-app
- Basic sync, text notes, images — no tables/kanban/calendar on mobile
- Russian translation available

**5. Task management is plugin-based**
- Kanban board: new (PR #6402), basic — no built-in due dates, priorities, recurrence
- Community plugins add this: Task Hub (ZangXincz), Gantt TODO Panel (youli42), weeklyplanner (ecodiv)
- These are script-notes, not core features — fragile, may break on upgrades
- Built-in Task Manager uses attributes (#todoDate, #doneDate, #P1-#P4) but no visual panel

### Where TriliumNext wins
- **Deployment simplicity**: single SQLite file, zero Docker services
- **MCP ecosystem**: 4+ mature servers (perfectra1n/triliumnext-mcp: 35 tools, OVDEN13/trilium-mcp: Go binary, RadonX/mcp-trilium: Java)
- **ETAPI**: more mature than AppFlowy's REST API — full CRUD, search, attributes, revisions, backup
- **Graph view**: relation map, note map (AppFlowy has none)
- **Per-note encryption**: AppFlowy has none
- **OCR**: built-in (images, PDFs, Office docs) — AppFlowy has none
- **Spreadsheets**: Univer Sheets (beta) — AppFlowy has none
- **Single-file backup**: copy one file vs AppFlowy's 5-service stack
