"""LIVE graphiti LLM-contract test — the MiniMax-M3 extraction round-trip.

graphiti-core's ingestion calls LiteLLM (127.0.0.1:4000) with
model=graphiti-primary + response_format=json_schema. This is the exact
link that must not break: if MiniMax-M3 stops returning schema-valid JSON,
episodes get extracted wrong / dropped. This test pinches that link directly
(stdlib only — no graphiti-core / mcp / falkordb dependency).

Gated behind @pytest.mark.live; needs the running litellm proxy + real
MiniMax key (both present on erebus).
"""
from __future__ import annotations

import json
import os
import urllib.request

import pytest

pytestmark = pytest.mark.live

LITELLM_URL = "http://127.0.0.1:4000/v1/chat/completions"
MASTER_KEY_PATHS = ["/var/lib/litellm/master-key.txt"]
# graphiti-mcp itself authenticates to litellm with a key baked into its config;
# /var/lib/litellm/ is root-only, so read the same key from the generated config.
GRAPHITI_CONFIG = "/var/lib/hermes/.config/graphiti-mcp/config.yaml"


def _master_key() -> str:
    tok = os.environ.get("LITELLM_MASTER_KEY", "").strip()
    if tok:
        return tok
    for p in MASTER_KEY_PATHS:
        if os.path.exists(p):
            tok = open(p, encoding="utf-8").read().strip()
            if tok:
                return tok
    # fall back to the key graphiti-mcp uses (hermes-readable generated config)
    if os.path.exists(GRAPHITI_CONFIG):
        import re

        for line in open(GRAPHITI_CONFIG, encoding="utf-8"):
            m = re.search(r'api_key:\s*"([^"]+)"', line)
            if m and m.group(1) not in ("sk-missing", ""):
                return m.group(1)
    pytest.skip("no litellm master key available")


# A graphiti-shaped extraction schema (entities + edges). Real graphiti uses a
# richer schema; this is a faithful-enough subset to prove strict json_schema
# enforcement is honoured end-to-end.
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "entity_type": {"type": "string"},
                },
                "required": ["name", "entity_type"],
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "fact": {"type": "string"},
                },
                "required": ["source", "target", "fact"],
            },
        },
    },
    "required": ["entities", "edges"],
}


def _extract(text: str) -> dict:
    key = _master_key()
    body = json.dumps(
        {
            "model": "graphiti-primary",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Extract entities and their relationships from the text. "
                        "Return JSON with 'entities' and 'edges'.\n\nTEXT:\n" + text
                    ),
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "extraction", "schema": EXTRACTION_SCHEMA},
            },
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        LITELLM_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def test_litellm_routes_graphiti_primary_to_minimax():
    resp = _extract("Alice is the CTO of Acme Corp. Bob reports to Alice.")
    assert resp.get("model", ""), "no model echoed — response malformed"
    msg = resp["choices"][0]["message"]
    content = msg.get("content")
    assert content, f"empty content: {resp!r}"

    data = json.loads(content)  # raises if the model emitted invalid/fenced JSON
    assert "entities" in data and "edges" in data, (
        f"schema keys missing — MiniMax did not honour json_schema: {content!r}"
    )
    # The CTO relationship must be captured as an entity + edge.
    names = [e["name"] for e in data["entities"]]
    assert any("Alice" in n for n in names), f"Alice not extracted: {names!r}"
    assert any(e.get("fact") and "Alice" in json.dumps(e) for e in data["edges"]), (
        f"no Alice relationship extracted: {data['edges']!r}"
    )
