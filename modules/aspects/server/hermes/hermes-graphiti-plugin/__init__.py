"""Graphiti memory provider plugin for Hermes Agent."""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import urllib.error
import urllib.request
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

def current_scope(agent_context: str = "", project: str = "", sub: str = "") -> str:
    """Scope hierarchy: likivik → likivik_{project} → likivik_{project}_{sub}
    Default: likivik (user-level, where existing data lives)."""
    if project and sub:
        return f"likivik_{project}_{sub}"
    if project:
        return f"likivik_{project}"
    return "likivik"


def cascading_scopes(scope: str) -> list[str]:
    parts = scope.split("_")
    return ["_".join(parts[:i]) for i in range(len(parts), 0, -1)]


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

    def record_latency(self, ms: float) -> None:
        self.latencies.append(ms)
        if len(self.latencies) > 50:
            self.latencies.pop(0)

    def summary(self) -> str:
        total_prefetch = self.prefetch_ok + self.prefetch_error + self.prefetch_empty
        avg_lat = sum(self.latencies) / len(self.latencies) if self.latencies else 0
        return (
            f"prefetch: {self.prefetch_ok}/{total_prefetch} ok, "
            f"{self.prefetch_empty} empty, {self.prefetch_error} errors | "
            f"search: {self.search_ok} ok, {self.search_empty} empty | "
            f"writes: {self.write_ok} ok, {self.write_error} errors | "
            f"flushes: {self.flushes} | reinits: {self.session_reinits} | "
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
        if key not in self._data:
            return None
        now = time.monotonic()
        if now > self._expires.get(key, 0):
            del self._data[key]
            self._expires.pop(key, None)
            return None
        self._data.move_to_end(key)
        return self._data[key]

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


# ── Graphiti MCP Client (stdlib only) ──────────────────────────────────

class GraphitiClient:
    """Sync MCP client for graphiti-mcp via HTTP streamable transport."""

    BASE_URL = "http://127.0.0.1:8000/mcp"
    TIMEOUT = 30.0

    def __init__(self) -> None:
        self._session_id: str | None = None
        self._initialize()

    def _post(self, body: dict, *, session: bool = False) -> str:
        data = json.dumps(body).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session and self._session_id:
            headers["mcp-session-id"] = self._session_id
        req = urllib.request.Request(self.BASE_URL, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                sid = resp.headers.get("mcp-session-id")
                if sid:
                    self._session_id = sid
                return resp.read().decode()
        except urllib.error.HTTPError as e:
            body_text = e.read().decode()[:200]
            raise RuntimeError(f"graphiti-mcp HTTP {e.code}: {body_text}")

    def _call(self, method: str, params: dict) -> dict:
        body = {
            "jsonrpc": "2.0",
            "id": uuid4().int % 100000,
            "method": method,
            "params": params,
        }
        try:
            text = self._post(body, session=(method != "initialize"))
        except RuntimeError as e:
            if "Session not found" in str(e) or "404" in str(e):
                log_event("session_expired_reinit", method=method)
                self._session_id = None
                self._initialize()
                text = self._post(body, session=(method != "initialize"))
            else:
                raise
        match = re.search(r"data: (.+)", text, re.DOTALL)
        if not match:
            raise RuntimeError(f"graphiti-mcp non-SSE response: {text[:200]}")
        result = json.loads(match.group(1))
        # Unwrap MCP tool call responses: extract content[0].text
        # The MCP server returns: {"result": {"content": [{"type": "text", "text": "{...}"}]}}
        # Callers expect the inner data dict directly.
        if method == "tools/call" and "result" in result:
            content = result["result"].get("content", [])
            if content and isinstance(content[0], dict) and "text" in content[0]:
                try:
                    result = json.loads(content[0]["text"])
                except (json.JSONDecodeError, IndexError):
                    pass
        return result

    def _initialize(self) -> None:
        self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "hermes-graphiti", "version": "0.1.0"},
        })
        self._post({
            "jsonrpc": "2.0", "method": "notifications/initialized",
        }, session=True)

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
        return self._call("tools/call", {"name": "add_memory", "arguments": args})

    def search_nodes(
        self, query: str, group_ids: list[str] | None = None, max_nodes: int = 10,
    ) -> dict:
        args: dict[str, object] = {"query": query, "max_nodes": max_nodes}
        if group_ids:
            args["group_ids"] = group_ids
        return self._call("tools/call", {"name": "search_nodes", "arguments": args})

    def search_memory_facts(
        self, query: str, group_ids: list[str] | None = None, max_facts: int = 10,
    ) -> dict:
        args: dict[str, object] = {"query": query, "max_facts": max_facts}
        if group_ids:
            args["group_ids"] = group_ids
        return self._call("tools/call", {"name": "search_memory_facts", "arguments": args})

    def delete_episode(self, uuid: str) -> dict:
        return self._call("tools/call", {"name": "delete_episode", "arguments": {"uuid": uuid}})

    def close(self) -> None:
        pass


# ── Tool schemas ───────────────────────────────────────────────────────

SEARCH_SCHEMA = {
    "name": "graphiti_search",
    "description": "Search the temporal knowledge graph for facts and entities related to a query.",
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
        try:
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
            log_event("late_init", ok=True)
            return True
        except Exception as e:
            log_event("late_init_failed", exc=str(e))
            return False

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
                if packed:
                    self._metrics.prefetch_ok += 1
                else:
                    self._metrics.prefetch_empty += 1
            except Exception as e:
                log_event("prefetch_error", exc=str(e))
                self._metrics.prefetch_error += 1
        threading.Thread(target=_work, daemon=True, name="graphiti-prefetch").start()

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not should_prefetch(query):
            return ""
        if not self._ensure_client():
            return ""
        cached = self._cache.get(query)
        if cached is not None:
            return cached
        with self._prefetch_lock:
            inflight = self._prefetch_result.get(query)
        if inflight is not None:
            return inflight
        self._start_prefetch(query)
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

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: list[dict] | None = None) -> None:
        if not self._ensure_client():
            return
        if self._agent_context != "primary":
            return
        user = strip_envelopes(user_content)
        if is_synthetic(user):
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
        name = f"turn-{(session_id or 'noctx')[-8:]}-{int(time.time() * 1000)}"
        combined = "\n---\n".join(self._turn_buffer)
        if len(combined) > MAX_EPISODE_CHARS:
            combined = combined[:MAX_EPISODE_CHARS]
        self._turn_buffer.clear()
        self._turn_counter = 0
        self._last_flush_time = time.monotonic()
        self._metrics.flushes += 1
        self._enqueue_sync(name, combined)

    def get_tool_schemas(self):
        return [SEARCH_SCHEMA, REMEMBER_SCHEMA, FORGET_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        try:
            start = time.monotonic()
            if tool_name == "graphiti_search":
                result = self._graphiti_search(**args)
            elif tool_name == "graphiti_remember":
                result = self._graphiti_remember(**args)
            elif tool_name == "graphiti_forget":
                result = self._graphiti_forget(**args)
            else:
                return tool_error(f"Unknown tool: {tool_name}")
            elapsed = time.monotonic() - start
            self._metrics.record_latency(elapsed * 1000)
            log_event("tool_call", tool=tool_name, ms=round(elapsed * 1000))
            return result
        except Exception as e:
            log_event("tool_call_error", tool=tool_name, exc=str(e))
            return tool_error(str(e))

    def _graphiti_search(self, query: str, limit: int = 10) -> str:
        group_ids = cascading_scopes(self._scope)
        nodes = self._client.search_nodes(query, group_ids, max_nodes=limit)
        facts = self._client.search_memory_facts(query, group_ids, max_facts=limit)
        formatted = self._format_results(nodes, facts)
        if formatted:
            self._metrics.search_ok += 1
        else:
            self._metrics.search_empty += 1
        return json.dumps({"results": formatted})

    def _graphiti_remember(self, content: str) -> str:
        episode_name = f"remember-{uuid4().hex[:8]}"
        try:
            self._client.add_memory(
                name=episode_name,
                body=content,
                group_id=self._scope,
                source="text",
                source_description="explicit_remember",
                reference_time=datetime.now(timezone.utc).isoformat(),
            )
            self._metrics.write_ok += 1
        except Exception:
            self._metrics.write_error += 1
            raise
        return json.dumps({"message": f"Saved: {content[:80]}...", "uuid": episode_name})

    def _graphiti_forget(self, uuid: str) -> str:
        self._client.delete_episode(uuid)
        return json.dumps({"message": f"Forgot: {uuid}"})

    def shutdown(self) -> None:
        if self._client:
            self._client.close()


# ── Registration ───────────────────────────────────────────────────────

def register(ctx) -> None:
    ctx.register_memory_provider(GraphitiMemoryProvider())
