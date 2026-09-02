"""SSH reachability of all fleet hosts.

Two layers:

1. Config-contract (hermetic, runs in CI): every host in the fleet must
   either (a) not enable a per-interface firewall lockout, or (b) open
   port 22 on tailscale0 (and/or globally). This prevents a repeat of
   the 2026-09-02 poweredge lockout, where a8cafce closed all
   tailscale0 ports with mkForce [] and forgot to re-open 22.

2. Live check (@pytest.mark.live): actually `ssh -o BatchMode=yes`
   each host and assert the command succeeds.
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

from conftest import read_text

REPO_ROOT = Path(__file__).resolve().parents[2]

# Host -> (tailscale magic DNS name, ssh user)
FLEET = {
    "erebus": "erebus.oryx-galaxy.ts.net",
    "serenity": "serenity.oryx-galaxy.ts.net",
    "traversal": "traversal.oryx-galaxy.ts.net",
    "poweredge": "poweredge.oryx-galaxy.ts.net",
}
SSH_USER = os.environ.get("FLEET_SSH_USER", "likivik")
SSH_TIMEOUT = int(os.environ.get("FLEET_SSH_TIMEOUT", "15"))


def _host_src(host: str) -> str:
    """Read the host's main nix file."""
    for cand in [f"modules/hosts/{host}/{host}.nix"]:
        p = REPO_ROOT / cand
        if p.exists():
            return p.read_text()
    return ""


def _extract_iface_ports(src: str, iface: str):
    """Pull the port list(s) from `networking.firewall.interfaces.<iface>.allowedTCPPorts`.

    Returns a list of *all* port lists found (attrs-overrides can define the
    same interface twice, e.g. erebus's `lockSshToTailscale` if/else). SSH
    counts as open if ANY branch includes 22.
    """
    lists = re.findall(
        rf"interfaces\.{iface}\.allowedTCPPorts\s*=\s*(?:lib\.)?mkForce\s*\[([^\]]*)\]",
        src,
    )
    lists += re.findall(
        rf"interfaces\.{iface}\.allowedTCPPorts\s*=\s*\[([^\]]*)\]",
        src,
    )
    if not lists:
        return None  # no per-interface rule at all
    ports = []
    for l in lists:
        ports.append([int(x) for x in re.findall(r"\d+", l)])
    return ports


@pytest.mark.parametrize("host", sorted(FLEET))
def test_host_opens_ssh_on_tailscale0(host):
    """Config contract: tailscale0 must be open (no lockout) or explicitly allow 22."""
    src = _host_src(host)
    if not src:
        pytest.skip(f"no source file for {host}")

    ports = _extract_iface_ports(src, "tailscale0")
    if ports is None:
        # No tailscale0-specific rule: global default applies. If the global
        # list is mkForce [] too, that's a lockout; otherwise SSH's
        # openFirewall (default true) covers it.
        g = re.search(
            r"allowedTCPPorts\s*=\s*(?:lib\.)?mkForce\s*\[\s*\]",
            src,
        )
        assert not g, (
            f"{host}: global firewall allowedTCPPorts is mkForce [] AND no "
            f"tailscale0 exception exists — all remote access is locked out "
            f"(poweredge 2026-09-02 incident). Open 22 on tailscale0."
        )
        return

    assert any(22 in p for p in ports), (
        f"{host}: tailscale0.allowedTCPPorts = {ports} does not include 22 in "
        f"any branch. SSH over Tailscale will be blocked. "
        f"Add 22 (poweredge 2026-09-02 incident)."
    )


@pytest.mark.live
@pytest.mark.parametrize("host", sorted(FLEET))
def test_host_sshable_live(host):
    """Live: ssh into each fleet host with BatchMode (key auth, no prompts)."""
    addr = FLEET[host]
    r = subprocess.run(
        [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={SSH_TIMEOUT}",
            "-o", "StrictHostKeyChecking=accept-new",
            f"{SSH_USER}@{addr}",
            "echo ok",
        ],
        capture_output=True,
        text=True,
        timeout=SSH_TIMEOUT + 10,
    )
    assert r.returncode == 0 and r.stdout.strip() == "ok", (
        f"{host} ({addr}): ssh failed rc={r.returncode}\n"
        f"stderr: {r.stderr.strip()[:300]}"
    )
