# Memory system comparison for opencode

## At a glance

| System | Type | Author | Stars | Latest | Storage | Auto-inject | Runtime |
|---|---|---|---|---|---|---|---|
| **codemem** | Plugin + CLI + MCP | kunickiaj | active | v0.29.0 (CLI) | SQLite + FTS5 + sqlite-vec | ✅ each turn | Node |
| **opencode-mem** | Plugin | tickernelz | ~892 | v2.15.0 | SQLite + USearch | ✅ session start | Bun / Node |
| **open-mem** | Plugin + MCP | clopca | ~17 | 0.14.2 | SQLite + FTS5 + sqlite-vec + KG | ✅ each turn | Bun |
| **agent-memory** | Plugin | joshuadavidthomas | ~178 | v0.2.0 | Markdown files + ONNX | ✅ always in prompt | Bun |
| **mnemosyne** | MCP only | — | — | 3.8.0 | SQLite + FTS5 + vectors | ❌ no hooks | Python (ad-hoc) |
| **with-context** | Plugin + MCP | boxpositron | — | — | Obsidian vault | ❌ explicit only | Node |
| **MemPalace** | Backend MCP | mempalaceofficial | — | active | Palace DB (vector) | depends on plugin | Python |
| Simple Memory | Plugin (built-in) | opencode | — | built-in | git-tracked markdown | ❌ agent chooses | opencode |
| supermemory | Plugin | — | — | — | — | — | — |
| **Mem0** | Plugin / Library / Server | mem0ai | ~58.8K | v0.2.0 (plugin) | Cloud or PostgreSQL (self-hosted) | ✅ | Requires API key |
| **Hindsight** | Plugin / Server | vectorize-io | ~16.5K | v0.8.2 | PostgreSQL (Docker) or embedded pg0 | ✅ | Docker + API key |
| **Graphiti** | MCP + Plugin | getzep | ~27.6K | v0.29.2 | Neo4j / FalkorDB (graph DB) | ✅ via opencode-graphiti | Python + Docker |
| **Cognee** | Library + MCP | topoteretes | ~17.9K | v1.2.0.dev0 | Postgres + KG | ✅ (Claude Code only) | Python |
| **Letta** | Server + CLI | letta-ai | ~23.4K | v0.16.8 | Postgres + blocks | ✅ (own platform) | Python |
| **pgmnemo** | Postgres extension + MCP | pgmnemo | ~4 | v0.9.1 | Postgres + pgvector | ❌ MCP only | PLpgSQL + Python |
| **A-MEM** | Research | WujiangXu | — | NeurIPS 2025 | Vector + graph | — | Python (ref impl) |
| **MemoryBank** | Research | Zhong et al. | — | 2023 | Vector | — | Python (ref impl) |

> **Name collision note**: kunickiaj's `codemem` was originally named `opencode-mem`, then renamed.
> `tickernelz/opencode-mem` is a different project that uses the vacated name.

---

## System deep dives

### codemem (kunickiaj)

**Repo**: github.com/kunickiaj/codemem
**Versions**: GitHub tag v0.36.0 | npm CLI `codemem` v0.29.0 | npm plugin `@codemem/opencode-plugin` v0.26.0 (these are different version streams — monorepo tag ≥ npm packages)
**Install**: `npx -y codemem setup --opencode-only`

- **Storage**: SQLite. Hybrid search via FTS5 BM25 + sqlite-vec semantic, merged via RRF.
- **Auto-capture**: Observer runs on idle / session end; captures events (not raw tool output).
- **Auto-inject**: `experimental.chat.system.transform` — context-aware pack built per turn.
- **Plugin tools (3)**: `mem-status`, `mem-stats`, `mem-recent`.
- **CLI tools**: stats, recent, search, pack, trace, embed, memory show/forget/remember/inject/export/import, serve, sync enable/disable/status/pair/once/doctor/bootstrap/coordinator, db prune/backfill, config, setup.
- **MCP tools**: search, timeline, pack, remember, forget.
- **Web UI**: built-in viewer.
- **Sync**: P2P via pairing payloads (coordinator server optional for groups).
- **Bundle**: ~661KB, 8 deps.

---

### opencode-mem (tickernelz)

**Repo**: github.com/tickernelz/opencode-mem
**npm**: `opencode-mem` v2.15.0 | ~2.1K weekly downloads
**Stars**: ~892
**Install**: `opencode plugin add opencode-mem`

- **Storage**: SQLite + USearch (in-memory vector, ExactScan fallback). No documented FTS.
- **Auto-capture**: Chat messages, user profile learning. Configurable interval, uses opencode's own provider.
- **Auto-inject**: Yes (hook not explicitly documented but uses the standard plugin hook system). Injects N most similar memories.
- **Plugin tools (1 function, 4 modes)**: `memory({ mode: "add" | "search" | "list" | "profile" })`.
- **Web UI**: Full-featured on port 4747.
- **Config file**: `~/.config/opencode/opencode-mem.jsonc`.
- **Embedding models**: 12+ local (Xenova/nomic-embed-text-v1 default). Smart deduplication.
- **Runtime**: Bun (primary). v2.15.0 added Node plugin loader support.
- **Bundle**: ~621KB, 7 deps.
- **Sync**: None.

---

### open-mem (clopca)

**Repo**: github.com/clopca/open-mem
**npm**: `open-mem` v0.14.2
**Stars**: ~17
**Install**: `bunx open-mem`

- **Storage**: SQLite + FTS5 + sqlite-vec + knowledge graph. No external vector DB.
- **Search** (most sophisticated pipeline): FTS5 BM25 → vector similarity → Reciprocal Rank Fusion → graph-augmented (entity extraction with relationships) → optional LLM reranking.
- **Auto-capture**: Hooks on `tool.execute.after` (captures tool outputs), `chat.message` (user prompts), `session.idle` (triggers queue processing).
- **AI compression**: Raw tool outputs distilled into typed observations (decision, bugfix, feature, refactor, discovery, change) with titles, narratives, concepts, importance scores. 5 provider fallback chain.
- **Auto-inject**: `experimental.chat.system.transform` — progressive disclosure. Token-budgeted index (~96% compression). Agent sees what exists, fetches details via mem-find / mem-get.
- **Plugin tools (10)**: mem-find, mem-create, mem-history, mem-get, mem-revise, mem-remove, mem-export, mem-import, mem-maintenance, mem-help. (README says "9", tools.md enumerates 10 — mem-maintenance is the 10th.)
- **Hooks**: `tool.execute.after`, `chat.message`, `event(session.idle)`, `experimental.chat.system.transform`, `experimental.session.compacting`, `event(session.end)`.
- **AGENTS.md generation**: Auto-generates root AGENTS.md on session end (or per-folder in "dispersed" mode).
- **Revision lineage**: Observations are immutable. Updates create new revisions. Deletes are tombstones.
- **Scoping**: project / user / all.
- **Workflow modes**: `code` (default: decision, bugfix, feature, refactor, discovery, change) and `research` (tuned vocabulary).
- **Web dashboard**: Timeline, sessions, search, stats, settings, config control plane, real-time SSE.
- **MCP server**: Exposes all 10 tools to any MCP client.
- **Platform adapters**: Claude Code, Cursor, HTTP bridge.

---

### agent-memory (joshuadavidthomas)

**Repo**: github.com/joshuadavidthomas/opencode-agent-memory
**npm**: `opencode-agent-memory` v0.2.0
**Stars**: ~178
**Install**: `opencode plugin add opencode-agent-memory`

- **Storage**: Markdown files with YAML frontmatter. Global: `~/.config/opencode/memory/*.md`. Project: `.opencode/memory/*.md` (auto-gitignored).
- **Journal** (opt-in): Append-only entries with YAML frontmatter, stored in `~/.config/opencode/journal/`. Semantic search via local all-MiniLM-L6-v2 (ONNX) — no data leaves the machine.
- **Base tools (3)**: `memory_list` (list blocks with metadata), `memory_set` (create/update block, full overwrite), `memory_replace` (replace substring in block).
- **Journal tools (3, opt-in)**: `journal_write`, `journal_search`, `journal_read`.
- **Default blocks**: `persona` (global, behavior), `human` (global, user details), `project` (project, codebase knowledge).
- **Block fields**: label, description, limit (max chars, default 5000), read_only.
- **Auto-capture**: None. Agent must explicitly `memory_set`.
- **Auto-inject**: Always in system prompt. No tool call needed to read memory.
- **Concept**: Letta-style shared memory blocks. "AGENTS.md with a harness."
- **No MCP, no CLI, no web UI.**

---

### mnemosyne

**PyPI**: `mnemosyne-memory` v3.8.0 | MCP server v1.28.0
**Current setup**: pipx run via nix shell (ad-hoc, no permanent install)
**DB**: `~/.hermes/mnemosyne/data/mnemosyne.db`

- **Storage**: SQLite + FTS5 + vector columns.
- **Search**: Hybrid scoring with per-query configurable weights (vec_weight + fts_weight + importance_weight) and temporal decay (halflife in hours). Unique approach — agent tunes weights per-query.
- **Auto-capture**: None. Agent must explicitly `mnemosyne_remember`.
- **Auto-inject**: None. No opencode plugin exists. Agent must call `mnemosyne_recall`.
- **MCP tools (~28)**: remember, recall, forget, update, stats, sleep, diagnose; scratchpad (write/read/clear); graph (link/query); triples (add/query); canonical (remember/recall); validate; export; import; sync (push/pull/status); shared (remember/recall/forget/stats).
- **Sync**: Push/pull via remote sync server. Supports conflict resolution by timestamp + importance.
- **Memory graph**: `graph_link` with relationship labels and weights; `graph_query` for BFS traversal.
- **Triples**: Structured subject-predicate-object facts with temporal validity.
- **Canonical facts**: Slot-based single-source-of-truth (category + name → body). Supersedes old values automatically.
- **Shared surface DB**: Cross-agent memory bank with dedicated namespace.
- **Validation**: Collaborative ownership — any agent can attest/update/invalidate any memory.
- **Consolidation**: `mnemosyne_sleep` compresses old working memories into episodic summaries.
- **No web UI.**
- **Runtime**: Python (pure Python package, not Rust). Runs ad-hoc via `nix shell nixpkgs#python3 nixpkgs#python313Packages.pipx -c pipx run --spec mnemosyne-memory[mcp] --with mnemosyne-hermes mnemosyne mcp`.

---

### with-context (boxpositron)

**npm**: `with-context-mcp` (MCP server) + `with-context-plugin` (opencode plugin)
**Install**: `npx -y with-context-mcp` + `opencode plugin add with-context-plugin`

- **⚠️ Not a memory system. It's a note-taking / session-tracking / changelog tool.**
- **⚠️ Requires Obsidian running with Local REST API plugin** (needs OBSIDIAN_API_KEY, OBSIDIAN_API_URL, OBSIDIAN_VAULT env vars).
- **Plugin tools (25)**: Session (start/pause/resume/end, get_status), Changelog (add_entry, get_session, get_commit_suggestion), Todos (add/update/list), Notes CRUD (write/read/delete/list/search/get_metadata/batch_write), Templates (list/create_from_template), Sync (ingest/sync/teleport), Utils (set_project_context, with_context_status).
- **Auto-capture**: None. Tool use is explicit (though AGENTS.md can tell the agent to use them).
- **Auto-inject**: None. Recommended to add rules to AGENTS.md.

---

### MemPalace

**Website**: mempalaceofficial.com
**Backend**: Python MCP server (`python3 -m mempalace.mcp_server`)
**Storage**: Palace DB (vector-based)

The MemPalace **backend** provides 33 MCP tools. There are **5 different opencode plugins** that integrate with it, each by a different author with different features:

| Plugin | Author | Exposed tools | Hook | Notes |
|---|---|---|---|---|
| `opencode-mempalace` | nguyentamdat | **19** (subset of 33) | `experimental.chat.system.transform` | Auto-init, wakeUp() L0+L1, background mining, auto-update |
| `opencode-mempalace` | rvboris | **1 tool** (`mempalace_memory` w/ 5 modes) | hidden retrieval + autosave | Bundled Python adapter (no separate mempalace install needed), privacy filtering |
| `@devtheops/opencode-plugin-mempalace` | DEVtheOPS | **1 tool** (`mempalace_mine_session`) + slash commands | `experimental.chat.system.transform` | Requires existing mempalace install. Injects skill + MCP server |
| `opencode-mempalace-persistence` | geco | auto (no explicit tools) | `experimental.chat.messages.transform` | Auto-saves every turn. Zero model discipline. Privacy filtering |
| `opencode-plugin-mempalace` | option-K | plugin managed | `experimental.chat.system.transform` + `experimental.session.compacting` | Crash safety (SIGINT handlers), idle auto-save |

> There is no single "mempalace" opencode plugin — each wraps the backend differently.

**Backend MCP tools (33)**:
- **Palace** (13): status, list_wings, list_rooms, get_taxonomy, search, check_duplicate, get_aaak_spec, add_drawer, delete_drawer, mine, sync, get_drawer, list_drawers, update_drawer
- **Knowledge Graph** (5): kg_query, kg_add, kg_invalidate, kg_timeline, kg_stats
- **Navigation** (7): traverse, find_tunnels, graph_stats, create_tunnel, list_tunnels, delete_tunnel, list_hallways, delete_hallway, follow_tunnels
- **Diary** (2): diary_write, diary_read
- **System** (3): hook_settings, memories_filed_away, reconnect
- **Notable features**: Tunnels (cross-project connections via hallways/wings), AAAK compression, L0-L3 memory stack.

---

### Mem0

**Repo**: github.com/mem0ai/mem0
**Stars**: ~58,800
**npm plugin**: `@mem0/opencode-plugin` v0.2.0
**PyPI**: `mem0ai`
**Website**: mem0.ai
**Install**: `opencode plugin add @mem0/opencode-plugin` or pip/npm library

- **Storage**: Cloud (Mem0 Platform) or self-hosted with Docker + PostgreSQL.
- **Algorithm** (as of April 2026): "Single-pass ADD-only extraction — one LLM call, no UPDATE/DELETE. Memories accumulate; nothing is overwritten."
- **Search**: Multi-signal retrieval — semantic (vector), BM25 (keyword), and entity matching fused → cross-encoder reranking.
- **Temporal reasoning**: Time-aware retrieval that ranks the right dated instance for "current state" vs "past" queries.
- **Entity linking**: Entities extracted, embedded, and linked across memories at query time.
- **Auto-capture**: ✅ via opencode plugin.
- **Auto-inject**: ✅ via opencode plugin.
- **Dedup**: Entity linking connects related memories but no explicit duplicate detection.
- **Stale handling**: ADD-only (no DELETE). Relies on temporal ranking to return newer facts for "current state" queries. Old facts persist and can surface for historical queries. No explicit invalidation or contradiction detection.
- **Requires API key** for cloud or self-hosted Docker deployment.
- **Y Combinator S24**, 58.8K stars.
- **Notable**: The ADD-only design is a deliberate choice — avoids the complexity of conflict resolution entirely. "Right version" emerges from temporal ranking, not from data mutation.

---

### Hindsight

**Repo**: github.com/vectorize-io/hindsight
**Stars**: ~16,500
**npm plugin**: `@vectorize-io/opencode-hindsight` v0.8.2
**Website**: hindsight.vectorize.io
**Install**: `opencode plugin add @vectorize-io/opencode-hindsight` + Docker

- **Storage**: PostgreSQL (via Docker) or embedded pg0. Default image ~400MB.
- **Architecture**: Biomimetic data structures — **World** (general facts), **Experiences** (agent's own past actions/outputs), **Mental Models** (reflected understanding synthesized from raw data).
- **3 core operations**: `retain` (store, LLM extracts entities + temporal data), `recall` (4 parallel strategies — semantic + BM25 + graph + temporal — fused via RRF → cross-encoder rerank), **`reflect`** (agent-initiated deep analysis that generates new Mental Models from raw memories).
- **Auto-capture**: ✅ via opencode plugin.
- **Auto-inject**: ✅ via opencode plugin.
- **Dedup**: Canonical entity normalization. No explicit duplicate detection on raw memories.
- **Stale handling**: The `reflect` operation can detect contradictions and form new Mental Models that supersede old ones. Temporal filtering in `recall` de-emphasizes old data. Raw stale facts persist but Mental Models (which reflect higher-level understanding) effectively replace them.
- **Requires Docker + PostgreSQL** (or embedded but heavy). Supports OpenAI, Anthropic, Gemini, Ollama, etc.
- **Performance**: SOTA on LongMemEval benchmark.
- **Notable**: Hindsight is the **only opencode-plugin system with a dedicated reflection pipeline** that can detect contradictions and synthesize new understanding. (Graphiti also auto-detects contradictions but via a different mechanism — see below.)

---

### Graphiti (getzep)

**Repo**: github.com/getzep/graphiti
**Stars**: ~27,600
**PyPI**: `graphiti-core` v0.29.2
**Paper**: arxiv 2501.13956 ("Zep: A Temporal Knowledge Graph Architecture for Agent Memory")
**Install**: `pip install graphiti-core` + Neo4j or FalkorDB (Docker)
**SOTA**: State of the Art in Agent Memory (per Zep blog)

- **Storage**: Neo4j, FalkorDB (Docker or embedded `falkordblite` for Python 3.12+), Amazon Neptune, or Kuzu (deprecated).
- **Architecture**: Temporal context graphs — **Entities** (nodes with evolving summaries), **Facts/Relationships** (edges with temporal validity windows), **Episodes** (provenance — raw data stream, every fact traces back here), **Custom Types** (ontology via Pydantic models).
- **Bi-temporal tracking**: Every fact has `valid_time` (when it became true) and `transaction_time` (when it was recorded). When information changes, old facts are **invalidated — not deleted**. Query what's true now, or what was true at any point in time.
- **Auto-invalidate on contradiction**: When a new fact contradicts an existing one, the LLM detects the contradiction on insert and automatically invalidates the old edge while preserving full temporal history. **This is the only evaluated system that auto-detects contradictions.**
- **Search**: Hybrid — semantic embeddings + BM25 keyword + graph traversal. Cross-encoder reranking. Sub-second latency.
- **Incremental construction**: New data integrates immediately without batch recomputation.
- **MCP server**: Built-in (`mcp_server/` directory) — episode management, entity/relationship handling, semantic + hybrid search, group management, graph maintenance.
- **LLM providers**: OpenAI (default), Anthropic, Gemini, Groq, or any OpenAI-compatible endpoint (Ollama, vLLM, llama.cpp, LM Studio). Works best with models that support Structured Output.
- **Requires**: Graph DB (Neo4j/FalkorDB) + LLM API key. LLM call on every insert (for entity extraction + contradiction detection).
- **No opencode plugin from getzep**, but community plugin exists (below).

#### opencode-graphiti (happycastle114) — community plugin

**Repo**: github.com/happycastle114/opencode-graphiti
**Stars**: ~17
**npm**: `opencode-graphiti`
**Install**: `bunx opencode-graphiti@latest install` + Docker for Graphiti MCP server

- Fork of opencode-supermemory, wraps Graphiti MCP server as backend.
- **Auto context injection**: User profile + project knowledge + relevant memories injected at session start.
- **"Remember" trigger detection**: Automatically prompts agent to save when user says "remember this", "save this", etc.
- **Context compaction**: Saves session summaries before context window limits.
- **Multi-tenant scoping**: User-scope and project-scope via `group_id`.
- **Plugin tool (1 function, 6 modes)**: `graphiti({ mode: "add" | "search" | "list" | "profile" | "forget" | "status" })`.
- **Slash command**: `/graphiti-init`.
- **Config**: `~/.config/opencode/graphiti.jsonc` (mcpUrl, groupIdPrefix, maxMemories, maxProjectMemories).
- **Backend**: FalkorDB (recommended, `docker compose --profile falkordb up -d`) or Neo4j.
- **Plugin needs no API keys** — OpenAI API key is for the Graphiti MCP server (entity extraction + embeddings).
- **Memory types**: project-config, architecture, learned-pattern, error-solution, preference, conversation.
- **Memory scopes**: `user` (cross-project), `project` (this repo only).

---

### Cognee (topoteretes)

**Repo**: github.com/topoteretes/cognee
**Stars**: ~17,900
**PyPI**: `cognee` v1.2.0.dev0
**Paper**: arxiv 2505.24478 ("Optimizing the Interface Between Knowledge Graphs and LLMs for Complex Reasoning")
**Install**: `uv pip install cognee` or `pip install cognee`

- **Storage**: Self-hosted knowledge graph (Postgres + pgvector + graph) or Cognee Cloud.
- **4 operations**: `remember` (store, runs add + cognify + improve), `recall` (auto-routing, picks best search strategy), `forget` (delete), **`improve`** (re-synthesize graph, reflection-like).
- **Session memory**: Fast cache that syncs to permanent graph in background. `recall` checks session first, falls through to graph.
- **Architecture**: Vector embeddings + graph reasoning + cognitive-science-grounded ontology generation. Documents searchable by meaning AND connected by relationships that evolve.
- **Claude Code plugin exists** (hooks: SessionStart, PostToolUse, UserPromptSubmit, PreCompact, SessionEnd). **No opencode plugin.** Could be used via `cognee-mcp` folder (MCP server).
- **Deploy**: Cognee Cloud, Modal, Railway, Fly.io, Render, Daytona.
- **LLM providers**: OpenAI (default), others configurable.
- **Dedup/stale**: `improve` operation re-synthesizes the graph (reflection-like). Doesn't explicitly claim contradiction detection in README.
- **CLI**: `cognee-cli remember/recall/forget`, `cognee-cli -ui` for local UI.

---

### Letta (letta-ai, formerly MemGPT)

**Repo**: github.com/letta-ai/letta
**Stars**: ~23,400
**npm CLI**: `@letta-ai/letta-code`
**PyPI SDK**: `letta-client`
**Install**: `npm install -g @letta-ai/letta-code` (CLI) or `pip install letta-client` (SDK)

- **Storage**: Postgres + memory blocks.
- **Architecture**: Memory blocks (core memory, always in context) + archival memory (retrieval-based). Letta-style shared blocks — similar shape to `agent-memory` but with a full agent platform around it.
- **Letta Code CLI**: Run agents locally in terminal. Supports skills and subagents. Bundles pre-built skills for advanced memory and continual learning.
- **Letta API**: Build stateful agents into applications. Python + TypeScript SDKs.
- **Model-agnostic**: Recommends Opus 4.5 and GPT-5.2 for best performance. Has a model leaderboard.
- **Auto-capture**: Yes (via own platform hooks).
- **Auto-inject**: Yes (memory blocks always in context, archival retrieved on demand).
- **Dedup/stale**: Block-level overwrite (similar to agent-memory). No explicit contradiction detection. No temporal validity tracking.
- **No opencode plugin.** Letta is an agent platform, not a memory plugin.
- **Requires**: Letta API key (cloud) or self-hosted Letta server + Postgres.

---

### pgmnemo

**Repo**: github.com/pgmnemo/pgmnemo
**Stars**: ~4
**Version**: v0.9.1 (June 2026)
**PyPI (MCP)**: `pgmnemo-mcp`
**Install**: `CREATE EXTENSION pgmnemo CASCADE` in Postgres + `pip install pgmnemo-mcp`
**In production**: Agency (~100k agent runs/week)

- **Storage**: PostgreSQL extension (pure SQL, no compiler). Uses pgvector for HNSW vector search.
- **Bitemporal tracking**: Facts have `t_valid_from` / `t_valid_to` validity windows. `recall_lessons(..., as_of_ts)` does point-in-time recall ("time-travel your agent's memory").
- **Provenance-gated writes**: `gate_strict='enforce'` blocks writes without `commit_sha` or `artifact_hash` at the Postgres constraint layer → "hallucinated memories cannot silently accumulate." Unique feature — prevents the agent from inventing facts.
- **Outcome-learning**: `reinforce(lesson_id, 'success' | 'failure' | 'neutral')` adjusts per-lesson confidence. Facts that never lead to success decay in confidence. Different angle on staleness — doesn't detect contradictions but learns which memories are useful.
- **$0 LLM write cost**: Ingestion is pure SQL (constraint check + indexed INSERT). No model API call on the write path. Embeddings server optional (without it, recall is BM25-only).
- **Single-plan multimodal recall**: HNSW vector + BM25 full-text + graph-edge proximity (`mem_edge` BFS) + JSONB metadata pushdown — all in ONE SQL query plan. `EXPLAIN (ANALYZE)` the full plan.
- **Graph traversal**: `traverse_causal_chain()`, `traverse_temporal_window()` with edge kinds (semantic, temporal, causal, entity).
- **Token-economy navigation**: `navigate_locate()` returns ranked IDs within a character budget; `navigate_expand()` fetches content + graph neighbors on demand.
- **MCP server**: `pip install pgmnemo-mcp && pgmnemo-mcp` — exposes `pgmnemo.ingest` and `pgmnemo.recall` tools. Can register in `opencode.jsonc`.
- **Benchmark**: recall@10 = 0.9604 on LongMemEval-S.
- **LangChain integration**: `pgmnemo_langchain` retriever.
- **Dedup/stale**: Bitemporal model provides validity windows but invalidation appears manual (set `t_valid_to`). Outcome-learning decays confidence over time. No auto-contradiction-detection.
- **No opencode plugin.** MCP only.
- **Requires**: PostgreSQL 14-17 + pgvector ≥ 0.7.0. Embeddings server optional.
- **Risk**: 4 stars, very new (v0.9.1, June 2026). Small community but in production at Agency.

---

### A-MEM (research)

**Paper**: arxiv 2502.12110 ("A-MEM: Agentic Memory for LLM Agents", Wujiang Xu et al., NeurIPS 2025)
**Ref impl**: github.com/WujiangXu/A-mem-sys

- **Architecture**: Based on the **Zettelkasten method** — dynamic indexing and linking. When a new memory is added, generates a comprehensive note with contextual descriptions, keywords, and tags. Analyzes historical memories to identify relevant connections, establishes links where meaningful similarities exist.
- **Memory evolution**: As new memories are integrated, they can trigger updates to the contextual representations and attributes of existing historical memories, allowing the memory network to continuously refine its understanding.
- **Dedup/stale**: Doesn't explicitly detect contradictions. "Refines understanding" via dynamic linking — existing memories get updated when new related ones arrive. No temporal validity windows.
- **Performance**: Superior improvement against existing SOTA baselines on six foundation models.
- **No opencode plugin.** Research system with reference implementation. Not production-ready for opencode.

---

### MemoryBank (research)

**Paper**: arxiv 2305.10250 ("MemoryBank: Enhancing Large Language Models with Long-Term Memory", Zhong et al., 2023)

- **Architecture**: **Ebbinghaus Forgetting Curve** theory — memories decay over time unless reinforced. Memory updating mechanism permits the AI to forget and reinforce memory based on time elapsed and relative significance.
- **Dedup/stale**: Doesn't detect contradictions. Naturally ages out stale facts over time via forgetting curve. Facts that are recalled/reinforced stay; unused facts fade. **Tradeoff**: if user reconfirmed an old (wrong) fact recently, it stays fresh despite being wrong.
- **Personality adaptation**: Synthesizes information from past interactions to understand user personality.
- **Versatile**: Accommodates closed-source (ChatGPT) and open-source (ChatGLM) models.
- **No opencode plugin.** Research paper from 2023. Reference implementation may exist but not production-ready for opencode.

---

### Dropped — insufficient data

These appeared in the initial survey but I couldn't verify details:

| System | npm | Known |
|---|---|---|
| **Simple Memory** | (built-in to opencode) | Git-tracked markdown. Agent saves/loads explicitly. No auto-inject. |
| **supermemory** | `opencode-supermemory` | Could not find published package or repo. Marked "?" in ecosystem lists. |

---

## Capability comparison tables

### Search & retrieval

| System | FTS | Vector | Hybrid fusion | Graph | Reranking |
|---|---|---|---|---|---|
| **codemem** | ✅ FTS5 BM25 | ✅ sqlite-vec | ✅ RRF | ❌ | ❌ |
| **opencode-mem** | ❌ (not documented) | ✅ USearch | ExactScan fallback (not true hybrid) | ❌ | ❌ |
| **open-mem** | ✅ FTS5 | ✅ sqlite-vec | ✅ RRF + graph-augmented | ✅ entity + relationships | ✅ optional LLM |
| **agent-memory** | ❌ | ✅ all-MiniLM-L6-v2 (journal only) | ❌ | ❌ | ❌ |
| **mnemosyne** | ✅ FTS5 | ✅ vector columns | ✅ weighted (vec/fts/importance) + temporal decay | ✅ graph_edges BFS | ❌ |
| **MemPalace** | ❌ | ✅ vector | ❌ | ✅ KG | ❌ |
| **Mem0** | ✅ BM25 | ✅ vector | ✅ multi-signal (semantic + BM25 + entity) | ✅ entity linking | ✅ cross-encoder |
| **Hindsight** | ✅ BM25 | ✅ vector | ✅ RRF (semantic + BM25 + graph + temporal) | ✅ graph | ✅ cross-encoder |
| **Graphiti** | ✅ BM25 | ✅ embeddings | ✅ semantic + keyword + graph traversal | ✅ temporal context graph | ✅ graph distance rerank |
| **Cognee** | ✅ | ✅ pgvector | ✅ vector + graph reasoning | ✅ KG + ontology | ❌ |
| **Letta** | ❌ | ✅ (archival) | ❌ | ❌ | ❌ |
| **pgmnemo** | ✅ BM25 | ✅ pgvector HNSW | ✅ single-plan (vector + BM25 + graph + JSONB) | ✅ mem_edge BFS (semantic/temporal/causal/entity) | ❌ (EXPLAIN-able) |
| **A-MEM** | ❌ | ✅ | ❌ | ✅ Zettelkasten links | ❌ |
| **MemoryBank** | ❌ | ✅ | ❌ | ❌ | ❌ |

mnemosyne's hybrid scoring is unique — per-query tunable weights with temporal halflife.
open-mem has the most stages (FTS → vector → RRF → graph → LLM rerank).
Graphiti is the only system with bi-temporal graph traversal (query what was true at any point in time).
pgmnemo is unique in doing all fusion inside a single SQL query plan (EXPLAIN-able).

---

### Context injection

| System | Hook / mechanism | Granularity | Progressive disclosure |
|---|---|---|---|
| **codemem** | `experimental.chat.system.transform` | Context-aware pack built per-turn | ✅ packs are relevance-ranked |
| **opencode-mem** | plugin (hook not explicitly documented) | N most similar memories | ❌ injects full memories |
| **open-mem** | `experimental.chat.system.transform` | Token-budgeted index → agent fetches details | ✅ ~96% compression |
| **agent-memory** | system prompt injection | All blocks always in context | ❌ full block content |
| **mnemosyne** | ❌ none | agent must call `mnemosyne_recall` | ❌ |
| **mempalace** | varies by plugin | L0+L1 (wakeUp) or per-turn | ✅ L0→L1→L2→L3 stack |
| **with-context** | ❌ none | agent must use tools explicitly | ❌ |
| **Mem0** | opencode plugin | relevant memories | ❌ |
| **Hindsight** | opencode plugin | relevant memories | ❌ |
| **Graphiti** | opencode-graphiti plugin (`experimental.chat.system.transform`) | profile + project + memories at session start | ❌ (injects full memories) |
| **Cognee** | Claude Code plugin (UserPromptSubmit hook) | relevant context | ❌ |
| **Letta** | own platform (memory blocks always in context) | all blocks always in context | ❌ full block content |
| **pgmnemo** | ❌ none (MCP only) | agent must call `pgmnemo.recall` | ❌ |
| **A-MEM** | — | — | ❌ |
| **MemoryBank** | — | — | ❌ |

open-mem's progressive disclosure is the most sophisticated: injects a compact index, agent fetches via mem-find/mem-get.
codemem's per-turn context-aware pack building is also smart.
Graphiti's opencode-graphiti plugin auto-injects at session start but doesn't do progressive disclosure.

---

### Auto-capture

| System | Captures | What | Triggers |
|---|---|---|---|
| **codemem** | ✅ | tool events | idle, session end (observer) |
| **opencode-mem** | ✅ | chat messages, user profile | per-message, configurable interval |
| **open-mem** | ✅ | tool outputs → AI-compressed observations | `tool.execute.after`, `chat.message`, `session.idle` |
| **agent-memory** | ❌ | — | agent must explicitly `memory_set` |
| **mnemosyne** | ❌ | — | agent must explicitly `mnemosyne_remember` |
| **mempalace** | ✅ (varies by plugin) | conversation, files, decisions | idle, threshold (N messages), exit |
| **Mem0** | ✅ | conversation | via opencode plugin |
| **Hindsight** | ✅ | experiences (agent actions/outputs) | via opencode plugin |
| **Graphiti** | ✅ (via opencode-graphiti) | "remember" triggers, session summaries | "remember this" detection, context compaction |
| **Cognee** | ✅ (Claude Code plugin) | tool calls → session memory → graph | PostToolUse, SessionEnd |
| **Letta** | ✅ | conversation, agent actions | own platform hooks |
| **pgmnemo** | ❌ | — | agent must explicitly `pgmnemo.ingest` |
| **A-MEM** | ❌ | — | research system, manual |
| **MemoryBank** | ❌ | — | research system, manual |

open-mem has the most sophisticated capture pipeline: raw tool output → AI compression → typed observations → knowledge graph → storage. mempalace plugins vary from "save every turn" (geco) to "threshold-based mining" (nguyentamdat).
Cognee's Claude Code plugin captures tool calls into session memory then syncs to permanent graph at session end.

---

### Tool surface

| System | Plugin tools | MCP / CLI tools | Total | Unique capabilities |
|---|---|---|---|---|
| **codemem** (plugin) | 3 (mem-status, mem-stats, mem-recent) | 5 MCP + many CLI | 8+ CLI | pack trace, P2P sync |
| **opencode-mem** | 1 function (4 modes) | none | 4 modes | user profile learning |
| **open-mem** | 10 | same 10 via MCP | 10 | revision lineage, export/import, agents.md gen |
| **agent-memory** | 3 base + 3 opt-in (journal) | none | 3-6 | Letta-style blocks, always in-context |
| **mnemosyne** | none (no plugin) | ~28 MCP | ~28 | canonical facts, triples, graph edges, scratchpad, sync, consolidate |
| **mempalace plugins** | 1-19 (varies) | backend 33 | plugin-dependent | tunnels between projects, diary, wing/room taxonomy |
| **with-context** | 25 | same 25 via MCP | 25 | session tracking, changelog, Obsidian sync |
| **Mem0** | via plugin | MCP + library | — | temporal reasoning, entity linking |
| **Hindsight** | via plugin | MCP + library | 3 ops (retain, recall, reflect) | Mental Models, reflection pipeline |
| **Graphiti** (plugin) | 1 function (6 modes) | MCP server (episode/entity/search/group/maintenance) | 6 modes + MCP | **bi-temporal auto-invalidation**, provenance (episodes) |
| **Cognee** | none (no opencode plugin) | 4 ops (remember, recall, forget, improve) + MCP | 4 | `improve` re-synthesis, session + permanent graph |
| **Letta** | none (no opencode plugin) | full agent API + CLI | many | memory blocks, archival, agent platform |
| **pgmnemo** | none (no opencode plugin) | 2 MCP (ingest, recall) + SQL functions | 2 MCP + SQL | **provenance-gated writes**, outcome-learning, bitemporal, EXPLAIN-able |
| **A-MEM** | none | — | — | Zettelkasten, memory evolution (research) |
| **MemoryBank** | none | — | — | Ebbinghaus forgetting curve (research) |

**Raw tool count**: MemPalace backend (33) > with-context (25) > mnemosyne (~28) > open-mem (10) > mempalace plugins (1-19) > agent-memory (3-6) > codemem (3 plugin + MCP) > opencode-mem (1 function). But tool count alone doesn't matter — tools behind auto-inject get used, tools behind MCP-only calls get forgotten. Graphiti and pgmnemo offer the most unique capabilities (bi-temporal, auto-invalidation, provenance-gating, outcome-learning) but have fewer raw tools.

---

### Storage

| System | DB | Vector engine | Project scoping | DB location |
|---|---|---|---|---|
| **codemem** | SQLite | sqlite-vec (in-DB) | ✅ per-project | project-local |
| **opencode-mem** | SQLite | USearch (in-memory, ExactScan fallback) | ✅ per-project | `~/.opencode-mem/data` |
| **open-mem** | SQLite | sqlite-vec (in-DB) | ✅ project/user/all | configurable (dbPath) |
| **agent-memory** | Markdown files | ONNX (journal only) | ✅ project + global | `~/.config/opencode/memory/` + `.opencode/memory/` |
| **mnemosyne** | SQLite | FTS5 + vector columns | ❌ global only | `~/.hermes/mnemosyne/data/mnemosyne.db` |
| **mempalace** | Palace DB | mempalace internal | ✅ wings + rooms | `~/.mempalace/palace` |
| **with-context** | Obsidian vault | none | ✅ per-project | Obsidian vault |
| **Mem0** | Cloud or Postgres | vector (cloud) | ✅ per-user | cloud or self-hosted |
| **Hindsight** | Postgres (Docker) | vector | ✅ per-agent | Docker volume |
| **Graphiti** | Neo4j / FalkorDB | embeddings (in graph) | ✅ via group_id | Docker container |
| **Cognee** | Postgres + KG | pgvector | ✅ per-user/tenant | self-hosted or cloud |
| **Letta** | Postgres | (archival via pgvector) | ✅ per-agent | Letta server |
| **pgmnemo** | Postgres extension | pgvector HNSW | ✅ role + project_id | your Postgres |
| **A-MEM** | Vector + graph | — | — | research |
| **MemoryBank** | Vector | — | — | research |

---

### Sync

| System | Sync method | Server requirement |
|---|---|---|
| **codemem** | P2P sync (pairing payloads) | Optional coordinator for groups |
| **mnemosyne** | push/pull | Required (remote sync server) |
| **mempalace** | mempalace_sync (drawer pruning), tunnels | None (local) |
| **with-context** | ingest/sync/teleport tools | None (relies on Obsidian) |
| **agent-memory** | git-trackable (manual) | None |
| **opencode-mem** | none | — |
| **open-mem** | export/import only | — |
| **Mem0** | cloud sync | cloud (or self-hosted) |
| **Hindsight** | none (local) | — |
| **Graphiti** | none (graph is local) | — |
| **Cognee** | Cognee Cloud | optional |
| **Letta** | Letta cloud | optional |
| **pgmnemo** | Postgres logical replication | None (uses Postgres native) |
| **A-MEM** | — | — |
| **MemoryBank** | — | — |

codemem's P2P sync is the most elegant — no central server needed. Pair via payload, devices find each other.

---

### Weight

| System | Bundle | Deps | Runtime | Persistent footprint |
|---|---|---|---|---|
| **codemem** | ~661KB | 8 | Node | npm install |
| **opencode-mem** | ~621KB | 7 | Bun / Node | npm install |
| **open-mem** | ? | ? | Bun | npm install |
| **agent-memory** | ? | 4 | Bun | npm install |
| **mnemosyne** | ad-hoc | Python stack | Python (via nix shell) | **0** (runs via pipx) |
| **mempalace** (backend) | ? | Python deps | Python | pip install or nix |
| **with-context** | ? | ? | Node | npm install |
| **Mem0** | — | — | — | cloud or Docker |
| **Hindsight** | — | — | Python | Docker (~400MB image) |
| **Graphiti** | — | graphiti-core | Python | Docker + graph DB + LLM API |
| **Cognee** | — | cognee | Python | pip install + Postgres |
| **Letta** | — | letta-client | Python | Letta server + Postgres |
| **pgmnemo** | — | pgmnemo-mcp | PLpgSQL + Python | **Postgres extension** (no new service) |
| **A-MEM** | — | — | Python | research (ref impl) |
| **MemoryBank** | — | — | Python | research (ref impl) |

All plugin-based systems are lightweight. mnemosyne is unique: zero permanent footprint. pgmnemo is unique among the heavy systems: it's a Postgres extension (no new service to run if Postgres exists). Graphiti/Cognee/Letta all require Docker + a separate server process.

---

### Web UI

| System | Web UI | Port | Features |
|---|---|---|---|
| **opencode-mem** | ✅ full-featured | 4747 | visual browsing, management |
| **open-mem** | ✅ dashboard | ? | timeline, sessions, search, stats, settings, real-time SSE |
| **codemem** | ✅ built-in viewer | dynamic | browse memories, sessions, observer output |
| **agent-memory** | ❌ | — | — |
| **mnemosyne** | ❌ | — | — |
| **mempalace** | ❌ (CLI/MCP only) | — | — |
| **with-context** | ❌ (Obsidian is the UI) | — | Obsidian vault |
| **Mem0** | ✅ (cloud dashboard) | — | if using Mem0 Platform |
| **Hindsight** | ❌ | — | — |
| **Graphiti** | ✅ (Neo4j Browser / FalkorDB Browser) | 7474 / 3000 | graph visualization |
| **Cognee** | ✅ (`cognee-cli -ui`) | — | local UI |
| **Letta** | ✅ (Letta dashboard) | — | agent management, memory blocks |
| **pgmnemo** | ❌ (SQL only) | — | `EXPLAIN` for query plans |
| **A-MEM** | ❌ | — | — |
| **MemoryBank** | ❌ | — | — |

---

## Dedup & stale fact handling

The core tension: **every system writes new facts, but no system reliably detects when a new fact contradicts an old one and auto-invalidates the stale entry.**

### Dedup mechanisms

| System | Dedup method | Prevents duplicates? | Notes |
|---|---|---|---|
| **codemem** | Similarity check on insert (configurable threshold) | ✅ configurable | Prevents near-duplicate inserts. No stale detection. |
| **opencode-mem** | Smart dedup (similarity check, configurable threshold) | ✅ configurable | Prevents duplicates. No stale detection. |
| **open-mem** | Entity linking (graph-based, revision lineage) | Partial | Immutable observations with revision history prevents overwrite confusion. Entity linking connects related facts. |
| **agent-memory** | Block-based (full overwrite on `memory_set`, substring replace on `memory_replace`) | ✅ by design | Write-once per block name. Agent must decide when to update a block — no automatic dedup. |
| **mnemosyne** | Canonical slot dedup (category+name → single body) | ✅ canonical supersede | `mnemosyne_remember` stores working memory (no dedup). Canonical facts (`mnemosyne_remember_canonical`) dedup by slot. `invalidate` with replacement_id chains old→new. |
| **Mem0** | Entity linking (connects related memories) | ❌ no explicit dedup | ADD-only design — nothing is deleted or deduplicated. Entity linking surfaces related facts at query time. |
| **Hindsight** | Canonical entity normalization | ❌ no explicit dedup | Entity normalization for retrieval, but raw experiences accumulate without dedup. |
| **mempalace** | `check_duplicate` tool (manual/explicit) | ❌ must be called explicitly | Has a check_duplicate endpoint but no auto-dedup on insert. |
| **Graphiti** | LLM-driven entity extraction + edge dedup on insert | ✅ automatic | Every insert runs an LLM call that extracts entities, checks for existing matching edges, and either updates or creates. **Auto-invalidates old edges when new fact contradicts.** |
| **Cognee** | Graph-based (ontology + entities) | Partial | `improve` re-synthesizes the graph. No explicit dedup on insert. |
| **Letta** | Block-based (full overwrite) | ✅ by design | Same as agent-memory — one value per block. No auto-dedup across blocks. |
| **pgmnemo** | Provenance-gated (commit_sha / artifact_hash constraint) | ✅ provenance | Dedup by provenance — same commit_sha won't create duplicate lessons. No semantic dedup. |
| **A-MEM** | Dynamic linking (Zettelkasten) | Partial | New memories link to related existing ones; existing memories get updated attributes. Not dedup per se — more like evolution. |
| **MemoryBank** | Reinforcement-based | ❌ | No dedup. Memories decay unless reinforced. Duplicates would both decay. |

### Stale fact handling

The hard problem: **after 6 months of daily use, a system has stored "user prefers tabs → user prefers spaces → user prefers tabs again". How does it know which fact is current?**

| System | Stale handling approach | Auto-detect contradictions? | Recovers from flip-flop? |
|---|---|---|---|
| **Mem0** | Temporal ranking — ADD-only, time-aware retrieval sorts by recency for "current state" queries. Old facts persist for historical queries. | ❌ No contradiction detection. | ✅ Yes — temporal ranking returns the most recent fact when asked "current preference". Old facts still exist but ranked lower. |
| **Hindsight** | `reflect` operation synthesizes Mental Models from raw Experiences. Contradictions can surface during reflection. Temporal filtering in recall. | ✅ Partial — reflection can surface contradictions when agent-initiated. | ✅ Mental Models supersede raw Experience. Agent must remember to `reflect`. |
| **mnemosyne** | Canonical `remember_canonical` auto-supersedes by slot. `invalidate` with replacement_id chains old→new. `sleep` consolidates old working memory. `triple_add` temporal validity. | ❌ No auto-detection. Agent must detect contradictions and explicitly invalidate. | ✅ Strongest tooling once conflict is detected — slot supersede, invalidation chains, triple validity windows, canonical fact system. |
| **open-mem** | Immutable observations + revision lineage. Updates create new revisions; deletes are tombstones. No temporal ranking or invalidation. | ❌ No auto-detection. | Partial — old revisions are preserved but there's no mechanism to prefer newer ones. |
| **codemem** | No explicit stale handling. Memories accumulate. | ❌ | ❌ Agent must manually forget/search. |
| **opencode-mem** | No explicit stale handling. Memories accumulate. Configurable dedup threshold prevents near-duplicates but doesn't mark old ones as stale. | ❌ | ❌ |
| **agent-memory** | Block-level overwrite. Agent calls `memory_set` with new content to replace old. | ❌ | ✅ Block overwrite means only one value per block exists. But this is manual. |
| **mempalace** | Manual invalidation via `delete_drawer`, `kg_invalidate`. No automatic stale detection. | ❌ | ❌ Manual only. |
| **Graphiti** | **Bi-temporal auto-invalidation.** When a new fact contradicts an existing one, the LLM detects it on insert and invalidates the old edge. Old facts get `valid_to` set, not deleted. Query "what's true now" returns only valid facts. | ✅ **Yes — automatic on insert.** | ✅ Yes — each new fact creates a new edge; old one is invalidated. Full temporal history preserved. |
| **Cognee** | `improve` operation re-synthesizes the graph. May surface contradictions during re-synthesis. | Partial — via `improve` (manual). | Partial — depends on `improve` run. |
| **Letta** | Block-level overwrite (same as agent-memory). | ❌ | ✅ Block overwrite means only one value per block. But manual. |
| **pgmnemo** | Bitemporal model (`t_valid_from` / `t_valid_to`). Outcome-learning decays confidence (`reinforce` with success/failure). Point-in-time recall. | ❌ No auto-detection. Invalidation is manual (set `t_valid_to`). | ✅ Bitemporal allows tracking flip-flops. Outcome-learning decays confidence on facts that don't lead to success. |
| **A-MEM** | Memory evolution — existing memories get updated when new related ones arrive. | ❌ No explicit contradiction detection. | Partial — "refines understanding" via linking. |
| **MemoryBank** | Ebbinghaus forgetting curve — memories decay over time unless reinforced. | ❌ No contradiction detection. | ✅ Decay naturally ages out old facts. But reconfirmed wrong facts stay fresh. |

### The 6-month stale fact problem — analysis

After sustained use (6+ months of daily sessions), every memory system faces this:

1. **Fact A** is stored (e.g., "user prefers spaces over tabs")
2. **Fact B** contradicts Fact A (e.g., after user tries Go, they prefer tabs)
3. If Fact B overwrites Fact A ✅ — no problem. But most systems **don't overwrite** (they accumulate)
4. A query for "preference" returns both facts, possibly with the wrong one ranked higher
5. The agent acts on stale information

**Three approaches exist across all evaluated systems:**

#### Approach 1: Auto-invalidate on insert (only Graphiti)

Graphiti is the **only evaluated system that auto-detects contradictions**. On every insert, an LLM call extracts entities and checks for existing edges that contradict the new fact. If a contradiction is found, the old edge is automatically invalidated (`valid_to` set) while preserving full temporal history. The query "what's true now" returns only currently-valid facts.

- **Strength**: Fully automatic. No agent discipline needed. Flip-flops are handled correctly — each new fact creates a new edge, old ones are invalidated.
- **Weakness**: Requires Docker + graph DB (Neo4j/FalkorDB) + LLM API key. LLM call on every insert (cost + latency). The opencode-graphiti plugin (17 stars) wraps this for opencode.

#### Approach 2: Decay old memories (MemoryBank, pgmnemo, Generative Agents)

Instead of detecting contradictions, let old memories fade. MemoryBank uses the Ebbinghaus forgetting curve (memories decay unless reinforced). pgmnemo uses outcome-learning (`reinforce` with success/failure adjusts confidence — facts that never lead to success decay). Generative Agents (Stanford) use recency + importance + relevance scoring.

- **Strength**: No contradiction detection needed. Stale facts naturally age out. Lightweight — no LLM call per insert (pgmnemo is $0 LLM write cost).
- **Weakness**: Doesn't detect contradictions — a recently-reconfirmed wrong fact stays fresh. Decay is time-based, not truth-based. Requires periodic reinforcement of true facts (MemoryBank) or success/failure feedback (pgmnemo).

#### Approach 3: Manual invalidation + bitemporal model (mnemosyne, pgmnemo)

Provide the data model for staleness (validity windows, canonical slots) and the tools to invalidate, but rely on the agent (or user) to detect contradictions and manually mark old facts as stale.

- **mnemosyne**: Canonical slot supersede (category+name → single body, restating supersedes), `invalidate` with replacement_id chains, temporal triples with validity windows, `validate` by any agent.
- **pgmnemo**: Bitemporal columns (`t_valid_from` / `t_valid_to`), point-in-time recall, but invalidation is manual (set `t_valid_to`). Outcome-learning adds confidence decay as a secondary mechanism.
- **Strength**: Strongest tooling once a conflict is detected. No LLM cost per insert. Full control.
- **Weakness**: Relies entirely on agent discipline to detect contradictions. If the agent doesn't notice the conflict, stale facts persist.

#### Per-system summary

- **Graphiti** — ✅ Approach 1 (auto-invalidate). Only automatic solution. Cost: Docker + graph DB + LLM API.
- **MemoryBank** — Approach 2 (Ebbinghaus decay). Research only, no opencode plugin.
- **pgmnemo** — Approach 2 (outcome-learning decay) + Approach 3 (bitemporal manual invalidation). Postgres extension, $0 LLM writes. 4 stars risk.
- **mnemosyne** — Approach 3 (canonical slots + invalidate). Zero footprint, but no auto-detection.
- **Mem0** — Pseudo-Approach 2 (temporal ranking returns most recent for "current state" queries, but old facts persist and can surface).
- **Hindsight** — Approach 2/3 hybrid (`reflect` can surface contradictions, but agent must initiate it; Mental Models supersede raw Experiences).
- **codemem, opencode-mem** — None. Append-only. Manual pruning only.
- **A-MEM** — Approach 2/3 hybrid (memory evolution updates existing memories, but no explicit contradiction detection).

**Verdict on the 6-month problem**: Graphiti is the only system that solves it automatically. Without Graphiti's infra cost, you must pick ONE system — no "pairing" strategy works because systems write to **separate DBs** (e.g., codemem writes to its own SQLite, mnemosyne writes to `~/.hermes/`). An auto-inject plugin can't see mnemosyne's invalidated facts, so stale facts in the plugin's DB will keep getting injected from the plugin's recall, not mnemosyne's. The agent would have to override its own auto-injected context by explicitly calling mnemosyne_recall — which defeats the purpose of auto-inject. The real choice:
  - **Graphiti** (via opencode-graphiti plugin) — **only system that does both** auto-inject AND auto-invalidate in one DB. Cost: Docker + graph DB + LLM API.
  - **codemem / open-mem** — auto-inject + auto-capture in one DB, but **no stale handling**. Stale facts accumulate.
  - **mnemosyne** — canonical slots + invalidate tools in one DB, but **no auto-inject**. Agent must explicitly recall.
  - **pgmnemo** — bitemporal + outcome-learning in one DB (Postgres). Decay handles staleness slowly; manual invalidation available. MCP only, no auto-inject.

---

## Decision guide

| If you prioritize... | Best choice | Why |
|---|---|---|
| Auto-recall with no agent effort | **opencode-mem** or **codemem** | Both auto-inject. opencode-mem simpler (one function). codemem richer CLI/MCP. |
| Most sophisticated capture + search | **open-mem** | AI compression → KG → progressive disclosure → LLM rerank. But only 17 stars. |
| Richest tool surface (if agent uses it) | **mnemosyne** (~28) or **MemPalace** (33) | Most tools. But no auto-inject — agent must remember to call them. |
| Minimal footprint, already works | **mnemosyne** (current) | Zero install, ad-hoc via nix shell. No auto-recall. |
| Ultra-light structured memory | **agent-memory** | Markdown files. Always in context. Good for stable facts (identity, preferences). Weak on episodic recall. |
| Cross-machine sync | **codemem** | P2P pairing, no server needed. |
| Note-taking + session tracking | **with-context** | Obsidian-based. Not a memory system. |
| **Auto contradiction detection** (6mo+) | **Graphiti** + opencode-graphiti | **Only system that auto-invalidates old facts on insert.** Bi-temporal. SOTA. Cost: Docker + graph DB + LLM API. |
| **Bitemporal + lightweight writes** | **pgmnemo** | Postgres extension, $0 LLM writes, bitemporal + outcome-learning. 4 stars risk. No auto-detection but decay + manual invalidation. |
| **Reflection pipeline** (agent-initiated) | **Hindsight** | `reflect` detects contradictions when agent runs it. Mental Models supersede raw facts. Cost: Docker + Postgres. |
| Long-term stale handling (6mo+) | **Graphiti** (auto) > **pgmnemo** (decay+manual) > **mnemosyne** (manual only) | Graphiti: only auto solution. pgmnemo: decay + bitemporal manual. mnemosyne: strongest manual tooling, zero footprint. |

**Verdict**: If auto-recall is #1, any plugin-based system (codemem, opencode-mem, open-mem, mempalace plugin, opencode-graphiti) beats any MCP-only system (mnemosyne, pgmnemo). For the 6-month stale-fact problem: **Graphiti is the only automatic solution** (requires Docker + graph DB + LLM API) **and the only system that combines auto-inject with stale handling in one DB**. Without that infra, you must choose one tradeoff: **auto-inject with no stale handling** (codemem/open-mem), **active recall with invalidation tools** (mnemosyne, zero footprint), or **Postgres-native bitemporal + decay** (pgmnemo, 4 stars). No "pairing" strategy works — separate DBs can't share invalidation state.
