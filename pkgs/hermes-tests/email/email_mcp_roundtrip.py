"""MCP handshake roundtrip for himalaya-mcp (hermetic — stdio, no IMAP dial-out).

Spawns the REAL himalaya-mcp (`node dist/index.js`) over the MCP stdio transport,
runs `initialize` + `list_tools`, and asserts the confirm-gated surface
(send/compose/draft + read + attachments + health). `list_tools` is static — it
registers schemas without invoking himalaya, so this is hermetic (himalaya is
referenced, never dialed). Regresses: the TS bundle builds, node runs it, stdio
MCP handshake works, and the email tool registry loads.

Usage: python email_mcp_roundtrip.py <mcp-bundle-js> <himalaya-binary>
"""

from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Confirm-gated send + draft + read + attachments + health (verified against the
# 1.7.0 bundle's registered tool names).
EXPECTED = {
    "send_email",
    "compose_email",
    "draft_reply",
    "list_emails",
    "search_emails",
    "read_email",
    "list_attachments",
    "download_attachment",
    "health_check",
}

# The outbound verbs MUST expose a `confirm` parameter — that is the
# confirm-before-send safety gate the agent relies on. `draft_reply` creates a
# draft (no send) so it correctly has none.
CONFIRM_REQUIRED = {"send_email", "compose_email"}


async def main() -> int:
    if len(sys.argv) < 3:
        print("FAIL: usage email_mcp_roundtrip.py <mcp-bundle-js> <himalaya-binary>")
        return 2
    bundle, himalaya = sys.argv[1], sys.argv[2]

    params = StdioServerParameters(
        command="node",
        args=[bundle],
        env={
            "HIMALAYA_BINARY": himalaya,
            "HIMALAYA_ACCOUNT": "default",
        },
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            by_name = {t.name: t for t in tools.tools}
            missing = EXPECTED - set(by_name)
            if missing:
                print(f"FAIL: missing tools {sorted(missing)}")
                print("got:", sorted(by_name))
                return 1
            for name in CONFIRM_REQUIRED:
                props = (by_name[name].inputSchema or {}).get("properties", {})
                if "confirm" not in props:
                    print(f"FAIL: {name} missing `confirm` param (got {sorted(props)})")
                    return 1
            print(
                f"HIMALAYA-MCP ROUNDTRIP OK: {len(by_name)} tools, "
                f"all {len(EXPECTED)} key ones present, "
                f"confirm-gate on {sorted(CONFIRM_REQUIRED)}"
            )
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
