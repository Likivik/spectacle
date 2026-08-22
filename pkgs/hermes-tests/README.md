# hermes-tests

End-to-end test suite for the Hermes deployment on erebus. Covers two axes:

| Suite | What it guards |
|---|---|
| `gateway/` | the mitmproxy credential-proxy removal didn't break outbound TLS / Telegram connectivity |
| `graphiti/` | the LLM wiring (MiniMax-M3 primary + throttled free fallbacks) stays correct — no re-introduced episode-drop storm |

## Tiers

- **Config-contract (hermetic)** — assert on committed Nix source (`graphiti-primary`,
  `allowed_fails=4`/`cooldown_time=30`, the `.profile` proxy-strip). Fast, no network, CI-safe.
- **Live (`@pytest.mark.live`)** — real TLS to `api.telegram.org` + `getMe`; skipped by default.

## Run

```bash
# hermetic only
make test

# live (needs the bot token at /run/secrets/hermes/telegram-bot-token)
make test-live
# or
../nc-ocr-flow/.venv/bin/python smoke.py
```

## Layout

```
conftest.py                      # fixtures + repo-root helpers
gateway/test_proxy_removed.py    # mitmproxy-removal regression guard (hermetic)
gateway/test_connectivity.py     # TLS + bot token (live)
graphiti/test_config.py          # litellm/graphiti wiring contract (hermetic)
graphiti/test_litellm_extraction.py  # litellm graphiti-primary -> MiniMax json_schema (live)
smoke.py                         # host smoke entrypoint (runs @live subset)
```

## Not yet implemented

- `graphiti/test_mcp_roundtrip.py` — full `add_memory` → poll `get_episodes` →
  `search`, speaking MCP streamable-HTTP to `127.0.0.1:8000/mcp`. Blocked on the
  `mcp` client lib in the test venv (present in the hermes agent env, not here).
  `test_litellm_extraction.py` covers the LLM-contract half of that pipeline.
- `checks.erebus-boot` nixosTest — boot the full config and assert units/configs/activation.
