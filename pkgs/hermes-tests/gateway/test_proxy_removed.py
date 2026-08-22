"""Regression guard for the mitmproxy credential-proxy removal.

The "broke" removal (commit 8c3f298d) deleted the proxy module but left
`HTTPS_PROXY` / `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` still exported in
`~/.profile`, so every outbound HTTPS call went through a dead proxy and
Hermes lost connectivity. The "worked" removal (c236002a) added the
`hermes-profile-env` activation script that strips those vars.

These tests pin the *working* end state so the regression can't silently
return.
"""
from conftest import STALE_PROXY_VARS, REPO_ROOT

MITM_NIX = "modules/aspects/server/hermes/_mitmproxy.nix"


def test_mitmproxy_module_removed():
    assert not (REPO_ROOT / MITM_NIX).exists(), (
        f"{MITM_NIX} still exists — the credential proxy module was not fully removed"
    )


def test_profile_env_strip_script_present(agent_nix):
    assert "hermes-profile-env" in agent_nix, (
        "hermes-agent.nix must define the `hermes-profile-env` activation script "
        "that strips stale proxy exports from ~/.profile"
    )


def test_profile_env_strips_all_stale_vars(agent_nix):
    # The sed in hermes-profile-env must drop every var the proxy injected.
    for var in ["hermes-mitmproxy"] + STALE_PROXY_VARS:
        assert var in agent_nix, (
            f"hermes-profile-env sed must strip `{var}` (or a removed proxy export "
            f"will resurface)"
        )


def test_gateway_unit_does_not_set_proxy_env(agent_nix):
    # The systemd user unit for the gateway must not (re-)inject proxy/CA vars:
    # an Environment= of the form `HTTPS_PROXY=...` would defeat the strip.
    for var in STALE_PROXY_VARS:
        # matches `"HTTPS_PROXY=...` inside the Environment list
        assert f'{var}=' not in agent_nix, (
            f"gateway unit must not set {var} — env must stay proxy-free"
        )


def test_no_global_proxy_env_in_hermes_modules():
    # Belt-and-suspenders: no hermes module may export a system-wide proxy var
    # outside the .profile strip. False positives allowed only for the exact
    # strip lines (which contain 'HTTPS_PROXY/d' sed patterns, not assignments).
    bad = []
    for nix in (REPO_ROOT / "modules" / "aspects" / "server" / "hermes").glob("*.nix"):
        for i, line in enumerate(nix.read_text().splitlines(), 1):
            for var in STALE_PROXY_VARS:
                if f"{var}=" in line and "sed" not in line:
                    bad.append(f"{nix.name}:{i} {line.strip()}")
    assert not bad, "proxy env assignment outside the strip found:\n" + "\n".join(bad)
