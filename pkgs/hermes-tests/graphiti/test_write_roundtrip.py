"""LIVE graphiti write-path roundtrip: remember → search → find.

This is the test that would have caught the Aug 27-30 incident: litellm was
down, every `graphiti_remember` returned "Saved" but nothing landed in FalkorDB.

Gated behind @pytest.mark.live; needs:
  - graphiti-mcp running on 127.0.0.1:8000
  - litellm running on 127.0.0.1:4000
  - FalkorDB running on 127.0.0.1:6379
  - graphiti-mcp config with group_id=likivik

The test writes a unique marker via the MCP `add_memory` tool, waits for
async extraction, then searches for it via `search_memory_facts`. If the
episode never lands (extraction LLM down, FalkorDB unreachable, etc.), the
search returns nothing and the test fails.

Stdlib only — no graphiti-core/mcp SDK dependency. Uses raw JSON-RPC over
HTTP to the graphiti-mcp streamable-http endpoint.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid

import pytest

pytestmark = pytest.mark.live

MCP_URL = os.environ.get("GRAPHITI_MCP_URL", "http://127.0.0.1:8000/mcp")
SEARCH_TIMEOUT = 120  # seconds to wait for async extraction
POLL_INTERVAL = 5


def _mcp_call(method: str, params: dict | None = None) -> dict:
    """Single JSON-RPC call to graphiti-mcp's streamable-http endpoint."""
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }).encode()
    req = urllib.request.Request(
        MCP_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()

    # graphiti-mcp may return SSE-framed JSON; extract the data payload.
    if raw.startswith("event:") or "data:" in raw:
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                raw = line[5:].strip()
                break

    resp = json.loads(raw)
    if "error" in resp:
        raise RuntimeError(f"MCP error: {resp['error']}")
    return resp.get("result", {})


def test_remember_then_search_finds_it():
    """Write a unique marker episode, then search for it.

    This is the exact failure mode from Aug 27-30: `add_memory` returned
    success but the episode never landed because litellm (extraction LLM)
    was down. If this test passes, the full chain works:
    MCP → graphiti-core → litellm → MiniMax-M3 → FalkorDB.
    """
    marker = f"TEST_ROUNDTRIP_{uuid.uuid4().hex[:12]}"
    content = (
        f"Write-path test marker {marker}: Kirill's test verified that "
        f"the graphiti remember→search roundtrip works end-to-end."
    )

    # Write
    result = _mcp_call("add_memory", {"name": f"roundtrip-test-{marker}", "episode_body": content})
    # add_memory returns immediately (async); we just need the MCP call to succeed
    assert result is not None, "add_memory returned None — MCP call failed"

    # Poll search until the marker appears or timeout
    deadline = time.time() + SEARCH_TIMEOUT
    while time.time() < deadline:
        try:
            facts = _mcp_call("search_memory_facts", {"query": marker, "max_results": 5})
        except Exception:
            pass
        else:
            # facts is a list of fact strings (or dict with 'facts' key)
            fact_text = json.dumps(facts)
            if marker in fact_text:
                return  # success
        time.sleep(POLL_INTERVAL)

    pytest.fail(
        f"marker {marker} not found in graphiti after {SEARCH_TIMEOUT}s — "
        f"write-path is broken (extraction LLM down? FalkorDB unreachable?)"
    )
