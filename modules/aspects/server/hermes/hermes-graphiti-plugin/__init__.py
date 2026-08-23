"""Graphiti memory provider plugin for Hermes Agent."""

from __future__ import annotations

import asyncio
import json
import logging
import http.server
import os
import queue
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

MAX_EPISODE_CHARS = 5000
CACHE_TTL_SECS = 30
CACHE_MAXSIZE = 256
QUEUE_MAXSIZE = 200

# ── Priority signals (for smart flush) ────────────────────────────────
PRIORITY_PATTERNS = re.compile(
    r"remember|запомни|save this|don'?t forget|deploy|mistake|bug|fixed|"
    r"decided|always|never|prefer|hate|important|critical|blocker",
    re.IGNORECASE,
)

# ── Salience filter (drop trivial turns before they hit the graph) ────
# Skipping low-signal turns keeps the graph lean so retrieval stays precise.
# Anything matching is dropped entirely (no episode written). Conservative.
# Pattern: anchored `^...$` (whole string must match) for greeting-only
# strings; falling out of `match()` means the turn is salient.
SALIENCE_PATTERNS = re.compile(
    r"^(\s*)$"                              # whitespace only
    r"|^(hi|hello|hey|yo|sup|hola|привет|здравствуйте)\s*[!,.?]*$"
    r"|^(thanks|thx|ty|спасибо|благодарю)\s*[!,.?]*$"
    r"|^(ok|okay|короче|ладно|да|yes|no|нет|ага|угу)\s*[!,.?]*$"
    r"|^(bye|goodbye|cya|пока|до встречи)\s*[!,.?]*$"
    r"|^[\U0001F300-\U0001FAFF\U0001F000-\U0001F9FF\u2600-\u27BF]+$"
    r"|^[\.\?\,\!]{1,5}$",
    re.IGNORECASE,
)

SALIENCE_MIN_WORDS = 3

# ── Episode naming convention ─────────────────────────────────────────
# First line of the turn body is matched against these patterns to pick a
# Category prefix for the graphiti episode name. Episodes get organized
# under "Category:Topic - Aspect" headers so search_nodes groups them nicely.
# Order matters: more-specific patterns (Tool Usage, Anti-Pattern) come before
# broader ones (Procedure, Lesson) so a turn that says "Run uv sync" lands
# under Tool Usage:, not Procedure:.
EPISODE_CATEGORIES = [
    ("Question:",     re.compile(r"^(what|why|when|where|как|что|почему|где|кто)\b", re.IGNORECASE)),
    ("Anti-Pattern:", re.compile(r"\b(don'?t|avoid|never|wrong|bad|bug|mistake|broken|fail)\b", re.IGNORECASE)),
    ("Preference:",   re.compile(r"\b(prefer|like|want|love|hate|always|never use|use x over y)\b", re.IGNORECASE)),
    ("Decision:",     re.compile(r"\b(decided|agreed|chose|going to|will use|switching to|plan)\b", re.IGNORECASE)),
    ("Lesson:",       re.compile(r"\b(learned|lesson|realized|insight|found out|figured out|now i know|takeaway)\b", re.IGNORECASE)),
    ("Procedure:",    re.compile(r"\b(how to|step[- ]by[- ]step|setup|install|configure|workflow)\b", re.IGNORECASE)),
    ("Tool Usage:",   re.compile(r"\b(uv sync|git apply|nixos-rebuild|uvicorn|pytest|deploy|restart|docker|podman|graphiti|mcp|falkordb|commit|push|pull|chmod|chown|patch|run\s+\w+)\b", re.IGNORECASE)),
]

# Max chars per chunk when sub-chunking. Graphiti chokes on episodes >~5kB
# (issue #1516) so we cap at SAFE_CHUNK_CHARS and split long bodies on
# paragraph boundaries.
SAFE_CHUNK_CHARS = 2500

# ── Smart gate ─────────────────────────────────────────────────────────

SYNTHETIC_PATTERNS = re.compile(
    r"^(/new|/reset|/help|/config|/\?)"
    r"|^session (started|ended|reset)\b"
    r"|^(\s*)$",
)

ENVELOPE_PATTERNS = re.compile(
    r"Conversation info.*?-{5,}.*?(?=\n\n|\Z)", re.DOTALL,
)

ENVELOPE_PATTERNS_SENDER = re.compile(
    r"Sender \(untrusted metadata\).*?-{5,}.*?(?=\n\n|\Z)", re.DOTALL,
)


def is_synthetic(user: str) -> bool:
    return bool(SYNTHETIC_PATTERNS.search(user.strip()))


def is_salient(text: str) -> bool:
    """Return True if a turn is worth storing in the graph.

    Filters out trivial turns (greetings, thanks, pure filler, emoji-only,
    <5 words). Conservative by design — only drops obvious noise.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped.split()) < SALIENCE_MIN_WORDS:
        return False
    if SALIENCE_PATTERNS.match(stripped):
        return False
    return True


def category_for_turn(body: str) -> str:
    """Pick a Category prefix for an episode name based on content.

    Returns "" when no category matches. Synced to EPISODE_CATEGORIES.
    """
    first_line = body.split("\n", 1)[0]
    for prefix, pattern in EPISODE_CATEGORIES:
        if pattern.search(first_line):
            return prefix
    return ""


def chunk_episode(body: str, max_chars: int = SAFE_CHUNK_CHARS) -> list[str]:
    """Split a long episode body into sub-chunks at paragraph boundaries.

    Graphiti's add_episode is impractically slow for >5kB bodies (issue #1516).
    Keeps the chunk count small — appends `:p0`, `:p1` suffixes for provenance.
    Returns a single-element list when the body fits. Lossless: the joined
    chunks reproduce the original body (including blank-line separators).
    """
    if len(body) <= max_chars:
        return [body]
    chunks: list[str] = []
    paragraphs = body.split("\n\n")
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        # Add 2 for the `\n\n` separator we will re-insert on join, but only
        # if this is not the first paragraph in the chunk.
        sep_len = 2 if current else 0
        para_len = len(para) + sep_len
        if current_len + para_len > max_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para) + (2 if len(current) > 1 else 0)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def strip_envelopes(content: str) -> str:
    content = ENVELOPE_PATTERNS.sub("", content)
    content = ENVELOPE_PATTERNS_SENDER.sub("", content)
    return content.strip()


def should_prefetch(query: str, min_length: int = 8) -> bool:
    if len(query) < min_length:
        return False
    if query.strip().startswith(("/", "!")):
        return False
    return True


# ── Scopes ─────────────────────────────────────────────────────────────

def current_scope(agent_context: str = "") -> str:
    """Group namespace for graphiti writes.

    Single-tenant: always returns "likivik". Kept as a function for
    future extensibility (e.g. a per-project group) without churn at
    call sites.
    """
    return "likivik"


def cascading_scopes(_scope: str) -> list[str]:
    """Read scope cascade. Single-tenant: just likivik.

    The cascade is a no-op for the flat-namespace setup, but the
    function is kept so future multi-tenant (project → user) reads
    can change one site without touching callers.
    """
    return ["likivik"]


# ── Observability ──────────────────────────────────────────────────────

LOG_PATH = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes")) / "logs" / "graphiti-plugin.log"


class GraphitiMetrics:
    """Tracks operation counts and latencies for health monitoring."""

    def __init__(self) -> None:
        self.prefetch_ok = 0
        self.prefetch_error = 0
        self.prefetch_empty = 0
        self.search_ok = 0
        self.search_empty = 0
        self.write_ok = 0
        self.write_error = 0
        self.session_reinits = 0
        self.flushes = 0
        self.latencies: list[float] = []
        self.max_queue_depth = 0
        self.search_relevance_hits = 0
        self.search_relevance_misses = 0

    def record_latency(self, ms: float) -> None:
        self.latencies.append(ms)
        if len(self.latencies) > 50:
            self.latencies.pop(0)

    def record_queue_depth(self, depth: int) -> None:
        if depth > self.max_queue_depth:
            self.max_queue_depth = depth

    def record_search_relevance(self, has_results: bool) -> None:
        if has_results:
            self.search_relevance_hits += 1
        else:
            self.search_relevance_misses += 1

    def summary(self) -> str:
        total_prefetch = self.prefetch_ok + self.prefetch_error + self.prefetch_empty
        avg_lat = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        total_search = self.search_relevance_hits + self.search_relevance_misses
        relevance_pct = self.search_relevance_hits * 100 // max(total_search, 1)
        return (
            f"prefetch: {self.prefetch_ok}/{total_prefetch} ok, "
            f"{self.prefetch_empty} empty, {self.prefetch_error} errors | "
            f"search: {self.search_ok} ok, {self.search_empty} empty | "
            f"writes: {self.write_ok} ok, {self.write_error} errors | "
            f"flushes: {self.flushes} | reinits: {self.session_reinits} | "
            f"relevance: {relevance_pct}% ({self.search_relevance_hits}/{total_search}) | "
            f"max_queue: {self.max_queue_depth} | "
            f"avg_latency: {avg_lat:.0f}ms"
        )




def log_event(event: str, **fields: object) -> None:
    record: dict[str, object] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


# ── TTL Cache ──────────────────────────────────────────────────────────

class TTLCache:
    def __init__(self, maxsize: int = CACHE_MAXSIZE, ttl: float = CACHE_TTL_SECS):
        self._maxsize = maxsize
        self._ttl = ttl
        self._data: OrderedDict[str, str] = OrderedDict()
        self._expires: dict[str, float] = {}

    def get(self, key: str) -> str | None:
        result = self.get_with_age(key)
        return result[0] if result else None

    def get_with_age(self, key: str) -> tuple[str, float] | None:
        if key not in self._data:
            return None
        now = time.monotonic()
        if now > self._expires.get(key, 0):
            del self._data[key]
            self._expires.pop(key, None)
            return None
        self._data.move_to_end(key)
        put_at = self._expires.get(key, now) - self._ttl
        age_ms = max(0, (now - put_at) * 1000.0)
        return self._data[key], age_ms

    def put(self, key: str, value: str) -> None:
        if key in self._data:
            del self._data[key]
        elif len(self._data) >= self._maxsize:
            self._data.popitem(last=False)
        self._data[key] = value
        self._expires[key] = time.monotonic() + self._ttl

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __setitem__(self, key: str, value: str) -> None:
        self.put(key, value)


# ── Graphiti MCP Client (mcp library) ────────────────────────────────

class GraphitiClient:
    """Async-backed MCP client for graphiti-mcp via HTTP streamable transport.

    Uses the official `mcp` Python library for protocol parsing, SSE framing,
    session lifecycle, and error recovery. Each sync method runs its async
    work via `asyncio.run` (the prefetch thread already provides isolation).
    """

    BASE_URL = "http://127.0.0.1:8000/mcp"

    def __init__(self) -> None:
        self._session_id: str | None = None

    async def _call_tool(self, name: str, arguments: dict) -> "CallToolResult":
        """Connect → initialize → call tool → disconnect. Each call is a fresh
        session. mcp ≥2.0 `streamable_http_client` is an async generator yielding
        `(read, write)`; we nest `async with` (the old manual `__aenter__` +
        3-tuple `get_session` API is gone). Default client timeouts: 30s
        connect/write, 300s read (SSE-friendly, graphiti extraction can be slow)."""
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        try:
            async with streamable_http_client(self.BASE_URL) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    if result.is_error:
                        raise RuntimeError(
                            f"graphiti-mcp tool error: {result.content}"
                        )
                    return result
        except Exception:
            self._session_id = None
            raise

    def _run(self, coro):
        try:
            return asyncio.run(coro)
        except BaseException as e:
            # repr(e) unwraps ExceptionGroup sub-exceptions (str(e) hides them)
            log_event("run_error", exc=repr(e))
            if "Session not found" in str(e) or "404" in str(e):
                log_event("session_expired_reinit")
                self._session_id = None
                return asyncio.run(coro)
            raise

    @staticmethod
    def _content_to_text(result) -> str:
        """Extract text content from a CallToolResult."""
        for block in result.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    @staticmethod
    def _parse_payload(result) -> dict:
        """Parse the JSON payload inside a tool result's text content."""
        text = GraphitiClient._content_to_text(result)
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    def add_memory(
        self, name: str, body: str, group_id: str,
        source: str = "text", source_description: str = "",
        reference_time: str | None = None,
    ) -> dict:
        args: dict[str, object] = {
            "name": name, "episode_body": body, "group_id": group_id,
            "source": source, "source_description": source_description,
        }
        if reference_time:
            args["reference_time"] = reference_time
        return self._run(self._call_tool("add_memory", args)).model_dump()

    def search_nodes(
        self, query: str, group_ids: list[str] | None = None, max_nodes: int = 10,
    ) -> dict:
        args: dict[str, object] = {"query": query, "max_nodes": max_nodes}
        if group_ids:
            args["group_ids"] = group_ids
        result = self._run(self._call_tool("search_nodes", args))
        return self._parse_payload(result)

    def search_memory_facts(
        self, query: str, group_ids: list[str] | None = None, max_facts: int = 10,
    ) -> dict:
        args: dict[str, object] = {"query": query, "max_facts": max_facts}
        if group_ids:
            args["group_ids"] = group_ids
        result = self._run(self._call_tool("search_memory_facts", args))
        return self._parse_payload(result)

    def get_episodes(
        self, group_ids: list[str] | None = None, limit: int = 10,
    ) -> dict:
        args: dict[str, object] = {"limit": limit}
        if group_ids:
            args["group_ids"] = group_ids
        result = self._run(self._call_tool("get_episodes", args))
        return self._parse_payload(result)

    def delete_episode(self, uuid: str) -> dict:
        result = self._run(self._call_tool("delete_episode", {"uuid": uuid}))
        return self._parse_payload(result)

    def close(self) -> None:
        pass


# ── Tool schemas ───────────────────────────────────────────────────────

SEARCH_SCHEMA = {
    "name": "graphiti_search",
    "description": (
        "Search the temporal knowledge graph for facts and entities related to a query. "
        "Single-tenant: searches group 'likivik' by default. "
        "Pass `group_ids` to override."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in the knowledge graph.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return (default 10).",
                "default": 10,
            },
            "group_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional scope override. Defaults to ['likivik']. "
                    "Pass an explicit list to restrict or expand."
                ),
            },
        },
        "required": ["query"],
    },
}

REMEMBER_SCHEMA = {
    "name": "graphiti_remember",
    "description": (
        "Durably save a high-priority fact to the knowledge graph. "
        "Use when the user explicitly says 'remember this' or for facts "
        "that should persist indefinitely."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The fact or content to remember.",
            },
            "group_id": {
                "type": "string",
                "description": (
                    "Optional scope override. Defaults to 'likivik' (single-tenant)."
                ),
            },
        },
        "required": ["content"],
    },
}

FORGET_SCHEMA = {
    "name": "graphiti_forget",
    "description": "Delete an episode from the knowledge graph by its UUID.",
    "parameters": {
        "type": "object",
        "properties": {
            "uuid": {
                "type": "string",
                "description": "UUID of the episode to delete.",
            },
        },
        "required": ["uuid"],
    },
}

RECALL_EPISODE_SCHEMA = {
    "name": "graphiti_recall_episode",
    "description": (
        "Fetch the full text of a single episode by its UUID. Use after a "
        "graphiti_search returned an episode reference and you need to read it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "uuid": {
                "type": "string",
                "description": "UUID of the episode to recall.",
            },
        },
        "required": ["uuid"],
    },
}

LIST_EPISODES_SCHEMA = {
    "name": "graphiti_list_episodes",
    "description": (
        "List recent episodes in the knowledge graph, newest first. Useful for "
        "debugging what was remembered, auditing memory state, or paginating "
        "history before search."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum episodes to return (default 10, max 100).",
                "default": 10,
            },
            "group_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional scope filter. Defaults to current agent scope.",
            },
        },
    },
}

STATUS_SCHEMA = {
    "name": "graphiti_status",
    "description": (
        "Report plugin health: graph node/edge/episode counts, sync queue depth, "
        "prefetch cache hit rate, and recent error counts. Cheap call."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


# ── MemoryProvider ─────────────────────────────────────────────────────

class GraphitiMemoryProvider(MemoryProvider):

    @property
    def name(self) -> str:
        return "graphiti"

    def is_available(self) -> bool:
        return True

    def _ensure_client(self) -> bool:
        """Return True if client is ready; lazily init if not.

        Defensive: handles the case where hermes calls prefetch/sync_turn
        before initialize(), or initialize() itself failed (e.g. MCP init 406).
        """
        if getattr(self, "_client", None) is not None:
            return True
        return self._late_init()

    def _late_init(self) -> bool:
        """Common bring-up path used by both `initialize()` and `_ensure_client()`.
        Idempotent after first success. Logs late_init or late_init_failed.
        Must NOT raise."""
        try:
            if getattr(self, "_client", None) is None:
                self._agent_context = getattr(self, "_agent_context", "primary")
                self._scope = current_scope(self._agent_context)
                self._cache = TTLCache()
                self._prefetch_result = {}
                self._prefetch_lock = threading.Lock()
                self._sync_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
                self._sync_worker = None
                self._client = GraphitiClient()
                self._turn_counter = 0
                self._turn_buffer = []
                self._sync_batch_every = 25
                self._last_flush_time = time.monotonic()
                self._metrics = GraphitiMetrics()
            self._ensure_sync_worker()
            self._ensure_metrics_server()
            log_event("late_init", ok=True)
            return True
        except Exception as e:
            log_event("late_init_failed", exc=str(e))
            return False

    def late_init(self) -> bool:
        """Hermes MemoryProvider hook — called after initialize()."""
        return self._late_init()

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id
        self._agent_context = kwargs.get("agent_context", "primary")
        self._scope = current_scope(self._agent_context)
        self._cache = TTLCache()
        self._prefetch_result: dict[str, str] = {}
        self._prefetch_lock = threading.Lock()
        self._sync_queue: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=QUEUE_MAXSIZE)
        self._sync_worker: threading.Thread | None = None
        self._client = GraphitiClient()
        self._turn_counter: int = 0
        self._turn_buffer: list[str] = []
        self._sync_batch_every: int = kwargs.get("sync_batch_every", 25)
        self._last_flush_time: float = time.monotonic()
        self._metrics = GraphitiMetrics()
        self._ensure_sync_worker()
        # Bring up the Prometheus metrics server too — initialize() is the
        # canonical entry point. _late_init() is idempotent and safe to call
        # even if a lazy _ensure_client already ran (it no-ops then).
        self._late_init()

    def system_prompt_block(self) -> str:
        return (
            "## Graphiti Memory\n"
            "Active. Temporal knowledge graph with bi-temporal entity tracking.\n"
            "Tools: graphiti_search(query) to query facts/entities, "
            "graphiti_remember(content) for high-priority facts, "
            "graphiti_forget(uuid) to delete.\n"
            "Auto-recall injects relevant context before each turn. "
            "Don't re-search what was just injected."
        )

    def _format_results(self, nodes: dict, facts: dict) -> str:
        lines: list[str] = []
        # Handle both MCP envelope {"result": {"nodes": [...]}} and
        # unwrapped format {"nodes": [...]} after _call extracts content.
        node_result = nodes.get("result", nodes)
        if isinstance(node_result, dict) and "nodes" in node_result:
            for n in node_result["nodes"]:
                name = n.get("name", "")
                summary = n.get("summary", "")
                labels = ", ".join(n.get("labels", []))
                parts: list[str] = []
                if name:
                    parts.append(f"[{name}]")
                if summary:
                    parts.append(summary)
                if labels:
                    parts.append(f"({labels})")
                if parts:
                    lines.append("  " + " — ".join(parts))
        fact_result = facts.get("result", facts)
        if isinstance(fact_result, dict) and "facts" in fact_result:
            for f in fact_result["facts"]:
                fact_text = f.get("fact", "")
                if fact_text:
                    lines.append("  • " + fact_text)
        if not lines:
            return ""
        return "## Graphiti Memory\n" + "\n".join(lines)

    def _start_prefetch(self, query: str) -> None:
        def _work() -> None:
            try:
                group_ids = cascading_scopes(self._scope)
                nodes = self._client.search_nodes(query, group_ids, max_nodes=10)
                facts = self._client.search_memory_facts(query, group_ids, max_facts=10)
                packed = self._format_results(nodes, facts)
                self._cache[query] = packed
                with self._prefetch_lock:
                    self._prefetch_result[query] = packed
                node_count = 0
                fact_count = 0
                try:
                    node_envelope = nodes.get("result", nodes)
                    fact_envelope = facts.get("result", facts)
                    if isinstance(node_envelope, dict):
                        node_count = len(node_envelope.get("nodes", []) or [])
                    if isinstance(fact_envelope, dict):
                        fact_count = len(fact_envelope.get("facts", []) or [])
                except Exception:
                    pass
                # DEBUG: log what we actually got so we can diagnose the
                # persistent facts=0 issue from log events. Remove after fix.
                log_event("prefetch_raw_shape",
                          nodes_type=type(nodes).__name__,
                          facts_type=type(facts).__name__,
                          nodes_keys=list(nodes.keys()) if isinstance(nodes, dict) else None,
                          facts_keys=list(facts.keys()) if isinstance(facts, dict) else None,
                          nodes_repr=str(nodes)[:200],
                          facts_repr=str(facts)[:200])
                if packed:
                    self._metrics.prefetch_ok += 1
                    self._metrics.record_search_relevance(bool(packed.strip()))
                    log_event("prefetch_ok", query=query[:80],
                              nodes=node_count, facts=fact_count,
                              chars=len(packed))
                else:
                    self._metrics.prefetch_empty += 1
                    log_event("prefetch_empty", query=query[:80],
                              nodes=node_count, facts=fact_count)
            except Exception as e:
                log_event("prefetch_error", exc=str(e))
                self._metrics.prefetch_error += 1
        threading.Thread(target=_work, daemon=True, name="graphiti-prefetch").start()

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not should_prefetch(query):
            log_event("prefetch_skipped", query=query[:80], reason="too_short_or_command")
            return ""
        if not self._ensure_client():
            log_event("prefetch_skipped", query=query[:80], reason="client_unavailable")
            return ""
        cached_with_age = self._cache.get_with_age(query)
        if cached_with_age is not None:
            cached, age_ms = cached_with_age
            log_event("prefetch_hit", query=query[:80],
                      chars=len(cached), age_ms=int(age_ms))
            return cached
        with self._prefetch_lock:
            inflight = self._prefetch_result.get(query)
        if inflight is not None:
            log_event("prefetch_inflight", query=query[:80], chars=len(inflight))
            return inflight
        self._start_prefetch(query)
        log_event("prefetch_started", query=query[:80])
        return ""

    def _sync_loop(self) -> None:
        while True:
            try:
                name, body = self._sync_queue.get()
            except Exception:
                break
            try:
                self._client.add_memory(
                    name=name,
                    body=body,
                    group_id=self._scope,
                    source="text",
                    source_description="sync_turn",
                    reference_time=datetime.now(timezone.utc).isoformat(),
                )
            except Exception as e:
                log_event("sync_turn", captured=False, exc=str(e))

    def _ensure_sync_worker(self) -> None:
        if self._sync_worker is None or not self._sync_worker.is_alive():
            self._sync_worker = threading.Thread(
                target=self._sync_loop, daemon=True, name="graphiti-sync",
            )
            self._sync_worker.start()

    def _ensure_metrics_server(self) -> None:
        """Background HTTP server exposing Prometheus-style metrics on
        http://127.0.0.1:<PORT>/metrics (default 8765). Stdlib only —
        no extra deps. Idempotent; one server per provider instance.
        """
        if getattr(self, "_metrics_server_started", False):
            return
        port = int(os.environ.get("GRAPHITI_METRICS_PORT", "8765"))

        def _render_metrics() -> bytes:
            m = self._metrics
            total_search = m.search_relevance_hits + m.search_relevance_misses
            relevance_pct = (
                m.search_relevance_hits * 100.0 / total_search
                if total_search else 0.0
            )
            avg_lat = (
                sum(m.latencies) / len(m.latencies)
                if m.latencies else 0.0
            )
            return (
                "# HELP graphiti_prefetch_ok_total Prefetch completions with results\n"
                "# TYPE graphiti_prefetch_ok_total counter\n"
                f"graphiti_prefetch_ok_total {m.prefetch_ok}\n"
                "# HELP graphiti_prefetch_empty_total Prefetch completions with no results\n"
                "# TYPE graphiti_prefetch_empty_total counter\n"
                f"graphiti_prefetch_empty_total {m.prefetch_empty}\n"
                "# HELP graphiti_prefetch_error_total Prefetch errors\n"
                "# TYPE graphiti_prefetch_error_total counter\n"
                f"graphiti_prefetch_error_total {m.prefetch_error}\n"
                "# HELP graphiti_search_ok_total Internal search hits with results\n"
                "# TYPE graphiti_search_ok_total counter\n"
                f"graphiti_search_ok_total {m.search_ok}\n"
                "# HELP graphiti_search_empty_total Internal searches with no results\n"
                "# TYPE graphiti_search_empty_total counter\n"
                f"graphiti_search_empty_total {m.search_empty}\n"
                "# HELP graphiti_write_ok_total graphiti_remember successes\n"
                "# TYPE graphiti_write_ok_total counter\n"
                f"graphiti_write_ok_total {m.write_ok}\n"
                "# HELP graphiti_write_error_total graphiti_remember errors\n"
                "# TYPE graphiti_write_error_total counter\n"
                f"graphiti_write_error_total {m.write_error}\n"
                "# HELP graphiti_flushes_total Successful sync flushes\n"
                "# TYPE graphiti_flushes_total counter\n"
                f"graphiti_flushes_total {m.flushes}\n"
                "# HELP graphiti_session_reinits_total MCP session reinitializations\n"
                "# TYPE graphiti_session_reinits_total counter\n"
                f"graphiti_session_reinits_total {m.session_reinits}\n"
                "# HELP graphiti_max_queue_depth Max sync queue depth observed\n"
                "# TYPE graphiti_max_queue_depth gauge\n"
                f"graphiti_max_queue_depth {m.max_queue_depth}\n"
                "# HELP graphiti_search_relevance_pct % of prefetch_ok events with non-empty packed results\n"
                "# TYPE graphiti_search_relevance_pct gauge\n"
                f"graphiti_search_relevance_pct {relevance_pct:.2f}\n"
                "# HELP graphiti_avg_latency_ms Mean latency across prefetch + tool calls\n"
                "# TYPE graphiti_avg_latency_ms gauge\n"
                f"graphiti_avg_latency_ms {avg_lat:.2f}\n"
            ).encode("utf-8")

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/metrics":
                    body = _render_metrics()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"ok\n")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):  # silence stderr noise
                pass

        try:
            server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
            thread = threading.Thread(
                target=server.serve_forever,
                daemon=True,
                name="graphiti-metrics",
            )
            thread.start()
            self._metrics_server_started = True
            self._metrics_port = port
            log_event("metrics_server_started", port=port)
        except OSError as e:
            log_event("metrics_server_failed", port=port, exc=str(e))

    def _enqueue_sync(self, name: str, body: str) -> None:
        try:
            self._sync_queue.put_nowait((name, body))
        except queue.Full:
            try:
                self._sync_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._sync_queue.put_nowait((name, body))
            except queue.Full:
                pass
            log_event("sync_turn", captured=False, reason="queue_full")
        self._ensure_sync_worker()
        self._metrics.record_queue_depth(self._sync_queue.qsize())

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: list[dict] | None = None) -> None:
        if not self._ensure_client():
            return
        if self._agent_context != "primary":
            return
        user = strip_envelopes(user_content)
        if is_synthetic(user):
            return
        # Salience filter: skip trivial turns so the graph stays focused
        # on decisions, lessons, and procedures rather than greetings/filler.
        if not is_salient(user):
            log_event("sync_salience_filtered", reason="low_signal", chars=len(user))
            return
        body = f"User: {user}\nAssistant: {assistant_content}"
        if len(body) > MAX_EPISODE_CHARS:
            body = body[:MAX_EPISODE_CHARS]

        self._turn_counter += 1
        self._turn_buffer.append(body)

        if not self._turn_buffer:
            return

        elapsed = time.monotonic() - self._last_flush_time
        should_flush_by_turns = self._turn_counter % self._sync_batch_every == 0
        should_flush_by_time = elapsed >= 3600
        should_flush_by_priority = bool(PRIORITY_PATTERNS.search(body))

        if should_flush_by_turns or should_flush_by_time or should_flush_by_priority:
            self._flush_buffer(session_id)

    def _flush_buffer(self, session_id: str) -> None:
        if not self._turn_buffer:
            return
        combined = "\n---\n".join(self._turn_buffer)
        self._turn_buffer.clear()
        self._turn_counter = 0
        self._last_flush_time = time.monotonic()
        self._metrics.flushes += 1

        # Sub-chunk: split long combined bodies on paragraph boundaries so
        # each graphiti add_memory call is small. Issue #1516.
        chunks = chunk_episode(combined)
        if len(chunks) > 1:
            log_event("sync_subchunked", chunks=len(chunks), chars=len(combined))

        # Naming: pick a Category prefix from the combined first line, then
        # suffix :p0, :p1 when sub-chunked. Falls back to timestamp.
        category = category_for_turn(combined)
        base_ts = int(time.time() * 1000)
        for i, chunk_body in enumerate(chunks):
            if len(chunks) > 1:
                name = f"{category}turn-{base_ts}:p{i}" if category else f"turn-{base_ts}:p{i}"
            else:
                name = f"{category}turn-{base_ts}" if category else f"turn-{base_ts}"
            self._enqueue_sync(name, chunk_body)

    def get_tool_schemas(self):
        return [
            SEARCH_SCHEMA,
            REMEMBER_SCHEMA,
            FORGET_SCHEMA,
            RECALL_EPISODE_SCHEMA,
            LIST_EPISODES_SCHEMA,
            STATUS_SCHEMA,
        ]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        try:
            start = time.monotonic()
            if tool_name == "graphiti_search":
                result = self._graphiti_search(**args)
            elif tool_name == "graphiti_remember":
                result = self._graphiti_remember(**args)
            elif tool_name == "graphiti_forget":
                result = self._graphiti_forget(**args)
            elif tool_name == "graphiti_recall_episode":
                result = self._graphiti_recall_episode(**args)
            elif tool_name == "graphiti_list_episodes":
                result = self._graphiti_list_episodes(**args)
            elif tool_name == "graphiti_status":
                result = self._graphiti_status()
            else:
                return tool_error(f"Unknown tool: {tool_name}")
            elapsed = time.monotonic() - start
            self._metrics.record_latency(elapsed * 1000)
            log_event("tool_call", tool=tool_name, ms=round(elapsed * 1000))
            return result
        except Exception as e:
            log_event("tool_call_error", tool=tool_name, exc=str(e))
            return tool_error(str(e))

    def _graphiti_search(
        self, query: str, limit: int = 10, group_ids: list[str] | None = None,
    ) -> str:
        if group_ids is None:
            group_ids = cascading_scopes(self._scope)
        nodes = self._client.search_nodes(query, group_ids, max_nodes=limit)
        facts = self._client.search_memory_facts(query, group_ids, max_facts=limit)
        formatted = self._format_results(nodes, facts)
        if formatted:
            self._metrics.search_ok += 1
        else:
            self._metrics.search_empty += 1
        return json.dumps({
            "results": formatted,
            "scopes_searched": group_ids,
            "node_count": len(nodes.get("nodes", []) or []),
            "fact_count": len(facts.get("facts", []) or []),
        })

    def _graphiti_remember(
        self, content: str, group_id: str | None = None,
    ) -> str:
        episode_name = f"remember-{uuid4().hex[:8]}"
        target_scope = group_id if group_id else self._scope
        try:
            self._client.add_memory(
                name=episode_name,
                body=content,
                group_id=target_scope,
                source="text",
                source_description="explicit_remember",
                reference_time=datetime.now(timezone.utc).isoformat(),
            )
            self._metrics.write_ok += 1
        except Exception:
            self._metrics.write_error += 1
            raise
        return json.dumps({
            "message": f"Saved: {content[:80]}...",
            "uuid": episode_name,
            "group_id": target_scope,
        })

    def _graphiti_forget(self, uuid: str) -> str:
        self._client.delete_episode(uuid)
        return json.dumps({"message": f"Forgot: {uuid}"})

    def _graphiti_recall_episode(self, uuid: str) -> str:
        # get_episodes returns recent ones; if uuid not in window, fall back to
        # no result. Graphiti MCP doesn't expose a direct "get_episode(uuid)"
        # endpoint, so the practical workaround is search by content or list.
        result = self._client.get_episodes(limit=100)
        episodes = result.get("episodes", [])
        for ep in episodes:
            if ep.get("uuid") == uuid:
                return json.dumps({"episode": ep})
        # Not found in recent window — caller should use graphiti_search instead.
        return json.dumps({
            "error": "not_found_in_recent",
            "uuid": uuid,
            "hint": "episode not in last 100; use graphiti_search to find older ones",
            "recent_count": len(episodes),
        })

    def _graphiti_list_episodes(
        self, limit: int = 10, group_ids: list[str] | None = None,
    ) -> str:
        if group_ids is None:
            group_ids = cascading_scopes(self._scope)
        result = self._client.get_episodes(group_ids, limit=min(limit, 100))
        episodes = result.get("episodes", [])
        # Trim content for list view
        trimmed = []
        for ep in episodes:
            trimmed.append({
                "uuid": ep.get("uuid"),
                "name": ep.get("name"),
                "group_id": ep.get("group_id"),
                "created_at": ep.get("created_at"),
                "source_description": ep.get("source_description"),
                "content_preview": (ep.get("content", "") or "")[:200],
            })
        return json.dumps({
            "count": len(trimmed),
            "scopes_searched": group_ids,
            "episodes": trimmed,
        })

    def _graphiti_status(self) -> str:
        # Cheap: just plugin metrics. Graph counts are available via
        # /var/lib/hermes/.hermes/scripts/graphiti-inspect.py if needed.
        return json.dumps({
            "plugin": {
                "prefetch_ok": self._metrics.prefetch_ok,
                "prefetch_empty": self._metrics.prefetch_empty,
                "prefetch_error": self._metrics.prefetch_error,
                "search_ok": self._metrics.search_ok,
                "search_empty": self._metrics.search_empty,
                "write_ok": self._metrics.write_ok,
                "write_error": self._metrics.write_error,
                "flushes": self._metrics.flushes,
                "session_reinits": self._metrics.session_reinits,
                "max_queue_depth": self._metrics.max_queue_depth,
                "queue_depth_now": self._sync_queue.qsize() if self._sync_worker else 0,
            },
            "scope": self._scope,
            "metrics_endpoint": f"http://127.0.0.1:{getattr(self, '_metrics_port', 8765)}/metrics",
        })

    def shutdown(self) -> None:
        if self._client:
            self._client.close()


# ── Registration ───────────────────────────────────────────────────────

def register(ctx) -> None:
    ctx.register_memory_provider(GraphitiMemoryProvider())
