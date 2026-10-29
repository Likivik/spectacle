# Per-host firewall target (agreed 2026-10-29)

What the config should *realize* after the grants model lands, host by host. Reviewed one
host at a time; each row is a decision, not an observation of today's config.

Status: **poweredge, erebus, serenity, afterglow-avia are migrated** in this PR and evaluate to
the tables below. **devbox01, nixosrouter, salembox** are already correct (nothing open).
**traversal** is pending: it has been offline for 13 days and its NIC name cannot be verified,
and a rule naming a device that does not exist stalls boot (measured). **spectacle** is untouched
because the host does not exist yet.

`lo` is in `trustedInterfaces` already, so a port listed on `lo` is documentation, not a rule
that changes anything.

## poweredge

| service | port | wires |
|---|---|---|
| sshd | 22 | lan, tailnet |
| qdrant (HTTP) | 6333 | tailnet, lo |
| qdrant (gRPC) | 6334 | tailnet, lo |
| nextcloud-mcp | 8000 | tailnet |

- `2000` is dropped: nothing listens on it and nothing in the tree declares it.
- 80/443 are not firewall ports — `tailscale serve` proxies to `127.0.0.1:80`.
- 6334 stays on the tailnet deliberately: no gRPC client exists today, the exposure is cheap
  and future clients get it for free.

## afterglow-avia

| service | port | wires |
|---|---|---|
| sshd | 22 | lan, tailnet |
| kkmserver | 5893, 5894 | lo, lan |
| avahi (mDNS) | 5353/udp | lan |

kkmserver's own comment says "local-only by default" while opening it everywhere; the target
is the comment, plus LAN because other devices open the KKM web UI.

## devbox01, nixosrouter, salembox

Nothing open, no sshd. Confirmed as the target, not an oversight.

## erebus

| service | port | wires |
|---|---|---|
| sshd | 22 | tailnet only (`lockSshToTailscale = true`) |
| tailscaled (WireGuard) | 41641/udp | global — NAT-punched peer traffic arrives before decapsulation |
| forgejo | 3443 | tailnet |
| sillytavern | 8001 | tailnet |
| hermes API | 8642 | tailnet |
| hermes dashboard | 9119 | tailnet |
| tts | 8880 | tailnet |
| fishaudio proxy | 8099 | tailnet, lo, podman0 |

Losing SSH over the tailnet on a VPS means falling back to the provider console — accepted.
`8003` is declared in the tailnet list but no module claims it; to be resolved or dropped.

## serenity

| service | port | wires |
|---|---|---|
| sshd | 22 | lan, tailnet |
| avahi (mDNS) | 5353/udp | lan |
| ollama | 11434 | lan, tailnet |
| tailscaled (WireGuard) | 41641/udp | global |
| container DNS | 53/udp | podman0 |

## spectacle

Untouched: the host does not exist yet.

## traversal

| service | port | wires |
|---|---|---|
| sshd | 22 | lan, tailnet |
| avahi (mDNS) | 5353/udp | lan |
| container DNS | 53/udp | podman0 |
