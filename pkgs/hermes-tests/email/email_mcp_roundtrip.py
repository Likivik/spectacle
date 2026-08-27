"""MCP roundtrip for mcp-email-server (hermetic — no live IMAP/SMTP).

Boots the REAL Wh1isper mcp-email-server over streamable-HTTP, runs MCP
`initialize` + `list_tools`, asserts the full tool surface (read / draft / send
/ attachments / policy) is present, and does an auth-free
`list_available_accounts` call (exercises config load + account registration).
Proves: the package builds, the service starts, the HTTP transport + MCP
handshake work, and the tool registry loads.

The live IMAP/SMTP roundtrip (send a real mail, read it back) is intentionally
NOT here — it needs a live mailbox + a Gmail app password and is gated as a
`@pytest.mark.live` test elsewhere.

Usage: python email_mcp_roundtrip.py <mcp-url>
"""

from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# The 15 @mcp.tool()-decorated tools in 1.5.1 (verified against app.py).
EXPECTED = {
    # read
    "list_available_accounts",
    "list_emails_metadata",
    "get_emails_content",
    "list_mailboxes",
    "download_attachment",
    # draft / send
    "save_to_mailbox",
    "send_email",
    "forward_email",
    # organize / mutate
    "delete_emails",
    "set_email_flags",
    "mark_emails_as_read",
    "move_emails",
    "archive_emails",
    # policy surface
    "list_allowed_recipients",
    "list_allowed_senders",
}


async def main() -> int:
    if len(sys.argv) < 2:
        print("FAIL: usage email_mcp_roundtrip.py <mcp-url>")
        return 2
    url = sys.argv[1]

    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            missing = EXPECTED - names
            if missing:
                print(f"FAIL: missing tools {sorted(missing)}")
                print("got:", sorted(names))
                return 1
            await session.call_tool("list_available_accounts", {})
            print(f"EMAIL MCP ROUNDTRIP OK: {len(names)} tools, {len(missing)} missing, account discovery responded")
            return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
