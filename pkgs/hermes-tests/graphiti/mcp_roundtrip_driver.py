"""Full-stack MCP roundtrip (hermetic, no LLM/embedder).

Regresses the integration seam that broke with the mcp 1.x -> 2.0 migration:
the Hermes/plugin MCP client no longer speaks the server's streamable-HTTP
transport. This boots the REAL graphiti-mcp-server against a fresh FalkorDB,
seeds an episode directly via graphiti-core (FalkorDriver, no model), then reads
it back through the MCP streamable-HTTP endpoint (initialize + list_tools +
get_episodes) — proving the transport, config load, FalkorDB wiring, and the
group_id/database tenant scoping all work end-to-end.

Usage: python mcp_roundtrip_driver.py <falkordb-host> <port> <database> <mcp-url>
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.nodes import EpisodicNode, EpisodeType
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PROBE = "mcp-roundtrip-probe-episode"


async def main() -> int:
    if len(sys.argv) < 5:
        print("FAIL: usage mcp_roundtrip_driver.py <host> <port> <database> <mcp-url>")
        return 1
    fhost, fport, db, url = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]

    # --- seed (direct write, no LLM/embedder) ---
    driver = FalkorDriver(host=fhost, port=fport, database=db)
    node = EpisodicNode(
        name="mcp-roundtrip-probe",
        group_id=db,
        source=EpisodeType.message,
        source_description="hermes-tests mcp roundtrip",
        content=PROBE,
        valid_at=datetime.now(timezone.utc),
    )
    await node.save(driver)

    # --- read back through the MCP streamable-HTTP transport ---
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            if "get_episodes" not in names:
                print(f"FAIL: get_episodes missing from {sorted(names)}")
                return 1

            result = await session.call_tool("get_episodes", {"max_episodes": 50})
            text = "\n".join(getattr(c, "text", "") for c in result.content)
            if PROBE not in text:
                print(f"FAIL: seeded episode {PROBE!r} not returned by MCP get_episodes")
                print(text[:800])
                return 1

    print("MCP ROUNDTRIP OK: seeded episode read back over streamable-HTTP")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
