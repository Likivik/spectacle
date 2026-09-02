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


def test_falkordb_database_is_likivik(graphiti_nix):
    # The count:0 regression: graphiti-mcp connected to FalkorDB `default_db`
    # (empty) while episodes live in the `likivik` graph. Read tools queried
    # the empty base and returned nothing. Pinned so a revert re-fails CI.
    assert 'database: "likivik"' in graphiti_nix
    assert 'group_id: "likivik"' in graphiti_nix


def test_plugin_passes_max_episodes(hermes_dir):
    # get_episodes server tool takes `max_episodes`; the plugin client sent
    # `limit`, which the server silently ignored (always returned 10).
    plugin = (hermes_dir / "hermes-graphiti-plugin" / "__init__.py").read_text()
    assert '"max_episodes": limit' in plugin, "plugin must send max_episodes (not limit)"


def test_no_hardcoded_tenant_name(hermes_dir):
    # group_id must resolve from the profile identity + defer to the MCP
    # server's config default. A hardcoded "likivik" in the plugin would pin
    # every profile to one tenant and silently cross-read memory.
    plugin = (hermes_dir / "hermes-graphiti-plugin" / "__init__.py").read_text()
    assert "likivik" not in plugin, "tenant name must come from config, not the plugin"


def test_scope_defers_for_default_profile(hermes_dir):
    # Named profile -> pass <name>; default profile -> None -> server default.
    plugin = (hermes_dir / "hermes-graphiti-plugin" / "__init__.py").read_text()
    assert "def resolve_scope(" in plugin
    assert "HERMES_PROFILE" in plugin, "must read HERMES_PROFILE env"
    assert "return None" in plugin, "default profile must defer (return None)"
    assert "group_id: str | None = None" in plugin, "add_memory must accept deferral"
    assert "if group_id:" in plugin, "write must omit group_id when scope is None"


def test_litellm_service_uses_patched_package(litellm_nix):
    # nixpkgs 56c02bc bumped litellm 1.89->1.97 without the new `expression`
    # dep, so litellm.service crashed at import and dropped graphiti episodes.
    # The service must swap in the patched derivation.
    assert "package = litellm" in litellm_nix


def test_litellm_override_adds_expression_and_import_check(litellm_pkg_nix):
    assert "expression" in litellm_pkg_nix
    assert "overridePythonAttrs" in litellm_pkg_nix
    # The exact chain that crashed must be import-checked at build time.
    assert "litellm.proxy._experimental.mcp_server.outbound_credentials" in litellm_pkg_nix


def test_expression_pinned_5_7_0(expression_pkg_nix):
    assert "5.7.0" in expression_pkg_nix
    assert "typing-extensions" in expression_pkg_nix


def test_litellm_lazy_logger_patch_wired(litellm_pkg_nix):
    # litellm 1.97.0 unconditionally imports ~50 optional observability SDKs
    # (boto3, agentops, datadog, galileo, opik, ...) at module level; nixpkgs
    # ships none of them. The postPatch must lazy-guard the registry or the
    # proxy crashes at import. A revert here re-fails the litellm-imports check.
    assert "make_lazy.py" in litellm_pkg_nix
    assert "postPatch" in litellm_pkg_nix
    assert "custom_logger_registry.py" in litellm_pkg_nix

