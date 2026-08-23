"""Driver-level graphiti roundtrip (no LLM/embedder) — regresses the count:0 bug.

The Aug-24 `count:0` regression: graphiti-mcp connected to FalkorDB `default_db`
(empty) while episodes were written to the per-group `likivik` graph, so `get_episodes`
queried the empty base and returned nothing. The fix points the base database at the
tenant graph and pins `group_id: likivik`.

This exercises that exact path hermetically — write an EpisodicNode, read it back via
`EpisodicNode.get_by_group_ids`, assert it's present. Runs inside a nixosTest VM with a
fresh FalkorDB, no network / no model credentials.

Usage: python roundtrip_driver.py [host] [port] [database]
"""

import asyncio
import sys
from datetime import datetime, timezone

from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.nodes import EpisodicNode, EpisodeType


async def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 6379
    database = sys.argv[3] if len(sys.argv) > 3 else "likivik"

    # Base database == tenant graph (the fix). Before the fix the base was
    # `default_db`; a read against that empty graph reproduced count:0.
    driver = FalkorDriver(host=host, port=port, database=database)

    # --- write path ---
    node = EpisodicNode(
        name="roundtrip-probe",
        group_id=database,
        source=EpisodeType.message,
        source_description="hermes-tests roundtrip",
        content="roundtrip probe episode",
        valid_at=datetime.now(timezone.utc),
    )
    await node.save(driver)

    # --- read path (this is what count:0 broke) ---
    eps = await EpisodicNode.get_by_group_ids(driver, [database], limit=10)

    found = any("roundtrip probe" in (e.content or "") for e in eps)
    if not found:
        print(
            f"FAIL: saved episode not found via get_by_group_ids "
            f"(database={database}, got {len(eps)} episodes)"
        )
        return 1

    print(f"ROUNDTRIP OK: saved+read episode in graph '{database}'")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
