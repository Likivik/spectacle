"""Config-contract tests for the graphiti LLM wiring.

Pin the LiteLLM + graphiti-mcp config so a revert (graphiti-primary back to
the free Groq chain, or cooldown tuning undone) fails CI rather than silently
re-introducing the RouterRateLimitError storm that dropped episodes.
"""


def test_primary_is_minimax_m3(litellm_nix):
    assert 'model_name = "graphiti-primary"' in litellm_nix
    assert 'model = "openai/MiniMax-M3"' in litellm_nix
    assert 'api_base = "https://api.minimax.io/v1"' in litellm_nix


def test_minimax_key_env_used(litellm_nix):
    assert 'api_key = "os.environ/MINIMAX_KEY"' in litellm_nix
    assert "MINIMAX_KEY" in litellm_nix  # the key is exported in the env seed


def test_fallback_chain_order(litellm_nix):
    # MiniMax primary -> free providers chained as fallbacks.
    expected = '"graphiti-primary"'
    assert expected in litellm_nix
    for fb in ["graphiti-free", "mistral-small-latest", "hf-gpt-oss-20b", "openrouter-free"]:
        assert fb in litellm_nix, f"fallback {fb} missing from chain"


def test_cooldown_tuning_not_reverted(litellm_nix):
    # The Aug 15-22 storm was caused by allowed_fails=1 + cooldown_time=300.
    assert "allowed_fails = 4" in litellm_nix
    assert "cooldown_time = 30" in litellm_nix
    assert "num_retries = 1" in litellm_nix


def test_graphiti_mcp_model_is_graphiti_primary(graphiti_nix):
    assert 'model: "graphiti-primary"' in graphiti_nix
    assert 'model: "graphiti-free"' not in graphiti_nix
