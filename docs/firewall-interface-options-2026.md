# Declaring firewall ports per interface, declaratively

Status: shape **chosen** 2026-10-29. Not yet implemented.
Repos involved: `spectacle` (NixOS fleet, den aspects), `ocrflow` (unaffected).

## The issue

NixOS gives you two ways to open a port, and both are global:

- `networking.firewall.allowedTCPPorts = [ 22 ];` → generates `-A nixos-fw -p tcp --dport 22 -j ACCEPT`
  with **no `-i`**, so it accepts on every interface, LAN included.
- A module's own `openFirewall = true` (openssh, nginx, and many others) does exactly that:
  `networking.firewall.allowedTCPPorts = lib.optionals cfg.openFirewall cfg.ports;`
  (nixpkgs `nixos/modules/services/networking/ssh/sshd.nix:312`, `:874`).

Per-interface lists (`networking.firewall.interfaces.<if>.allowedTCPPorts`) are **additive only**.
They cannot subtract from the global list, so this — which is what `poweredge.nix:331` does today —
does nothing at all:

```nix
networking.firewall.interfaces.eno1.allowedTCPPorts = lib.mkForce [ ];   # no-op
```

Upstream agrees this is a gap: nixpkgs [#41459](https://github.com/NixOS/nixpkgs/issues/41459)
"firewall module doesn't support per interface port opening", and the older
[#23181](https://github.com/NixOS/nixpkgs/issues/23181) "[RFC] Modularize the firewall".
There is no option-level facility for "open this port on these interfaces"; the only in-tree
example of the *pattern* is `moonshine.nix` (lines 103–145), which defines its own
`firewallInterfaces` list and maps it with `lib.genAttrs`.

### Measured, 2026-10-29, on poweredge

```
$ iptables -S nixos-fw | grep dport
-A nixos-fw -p tcp -m tcp --dport 22 -j nixos-fw-accept          ← no -i: every interface
-A nixos-fw -i tailscale0 -p tcp -m tcp --dport 22 -j nixos-fw-accept
-A nixos-fw -i lo … 2000/6333/6334/8000
```

No `eno1` rule exists. LAN SSH works because of the wildcard rule, not because of any
statement of intent. The comment above `poweredge.nix:331` claims the opposite.

## What we actually want

1. SSH reachable from the LAN and from the tailnet — and provably nowhere else.
2. A service declares **what** it needs; the host declares **where** its wires are; neither knows
   the other's business.
3. `openFirewall = true` must not be able to sneak a wildcard rule past that.
4. A machine with no LAN exposure statement should end up with no LAN exposure, not with the default.

## Chosen shape (2026-10-29)

**The port is a service fact; the wire is a host fact.** Neither side can know the other's
business, so each declares only its own, and the host *grants* a service onto wires.

```nix
# service aspect — what it needs
firewall = { name = "ssh"; ports = [ 22 ]; };

# host — where it may appear
network.ifaces = { lan = "eno1"; tailnet = config.services.tailscale.interfaceName; };
network.grants.ssh = [ "lan" "tailnet" ];     # erebus: [ "tailnet" ]
```

No wires in services, no exclusion list anywhere. One consumer resolves grants to devices:

```nix
den.aspects.core.firewall = {
  nixos = { firewall, lib, config, ... }:
    let
      ifaces = config.network.ifaces;
      grants = config.network.grants;
      on = wire: f: lib.elem wire (grants.${f.name} or [ ]);
    in
    lib.mkMerge [
      # Backstop: outranks every module's openFirewall = true (priority 1000 vs 100).
      { networking.firewall.allowedTCPPorts = lib.mkForce [ ];
        networking.firewall.allowedUDPPorts = lib.mkForce [ ]; }

      { networking.firewall.interfaces =
          lib.genAttrs (lib.attrNames ifaces) (wire: {
            allowedTCPPorts = lib.unique (lib.concatMap
              (f: if on wire f then f.ports or [ ] else [ ]) firewall);
            allowedUDPPorts = lib.unique (lib.concatMap
              (f: if on wire f then f.udp or [ ] else [ ]) firewall);
          });
        assertions = [
          { assertion = lib.all (w: ifaces ? ${w}) (lib.concatLists (lib.attrValues grants));
            message = "network.grants names a wire this host does not declare"; }
          { assertion = lib.all (svc: lib.any (f: f.name == svc) firewall)
              (lib.attrNames grants);
            message = "network.grants names a service that produces no firewall entry"; }
        ];
      }
    ];
};
```

### Shortcomings, closed one by one

- **Additive-only per-interface semantics** → the global lists are `mkForce []`, so there is
  nothing to subtract from; only per-interface rules exist.
- **`openFirewall = true` re-opening wildcards** → outranked by the `mkForce` backstop. A module
  that still sets it ends up closed, which is visible immediately and fixed by a grant.
- **Device names leaking into services** → services carry `ports` only; devices live in
  `network.ifaces`, wires in `network.grants`.
- **Default-deny ambiguity** → no grant means closed; an unknown service or wire is an eval error,
  not an empty rule.
- **Per-host exceptions** → one grant line per host; no `mkForce`, no exclusion list, no aspect
  splitting.
- **Recovery path** → LAN SSH survives as an explicit grant on poweredge. It becomes a decision
  instead of today's accident.
- **Testability** → the poweredge smoke probe asserts the resulting ruleset (see below).

### Closing the two remaining gaps

Both were listed as accepted limitations. They are closable; the cost is honest, not zero.

#### Step 1 — Den-native, no new firewall machinery

Den already gives everything needed; none of it is firewall-specific.

- **The pool is the check.** Every service's entries reach the consumer as one list, so a duplicate
  port is a `throw` while iterating it. `pipe.withProvenance` attaches *who declared it*, so the
  error names both services instead of reporting "conflict".
- **A policy is lint that runs at eval.** `den.policies` are functions applied per host at build
  time. "Any podman publish without a `127.0.0.1:` prefix → throw" is one pipe stage, and the
  mistake fails `nix eval` instead of a review.
- **Capabilities (auscyber's shape), if we ever want the deep version.** A service declares "I need
  ingress"; a firewall aspect derives the rules from that. Port numbers then live in a single place,
  so collisions cannot arise — at the cost of the most machinery of anything surveyed.

The escalation paths below are for when step 1 stops being enough, not the starting point.


#### Step 2 — escalation: **port collisions** (grants are per service, rules are per port)

- **Collision assertion at eval** — build `port → [ service ]` from the pool and fail when two
  services claim the same port with *different* grant sets. Same port + same grants is harmless and
  allowed. Ten lines, and it converts a silent union into a named error.
- **Per-unit L3 filtering (the real fix)** — `systemd.services.<name>.ipAddressAllow` attaches an
  eBPF access list to the unit's cgroup, so even two services on the same port accept only from the
  addresses they are allowed. Isolation then rests on the unit, not the port number. Limits: filters
  by address, not by interface; needs cgroup-BPF; a service behind nginx sees nginx's address.
- **NixOS nftables** (`networking.nftables.enable`, `networking.nftables.tables.<name>.{family,content}`)
  allows named per-service tables with comments, so rules are attributable and duplicates show up in
  a diff. Cost: migrating the whole firewall off the iptables-compatible module, and the module's own
  docs warn it disables the `ip_tables` kernel modules that docker/podman use internally.

Recommendation: ship the assertion now; keep `ipAddressAllow` and nftables tables as the escalation
path when a real collision appears.

#### Step 2 — escalation: **layers this model does not govern**

- **Podman published ports** — publish to loopback only: `-p 127.0.0.1:8080:9000` (the shape
  `oci-containers.nix:183-189` documents). A container then never appears on a wire at all, and the
  wire policy only ever concerns the reverse proxy in front of it. This is a rule we can lint for:
  any `-p` without a `127.0.0.1` prefix is a finding.
- **`tailscale serve`** — not an INPUT port and not a hole: tailscaled terminates TLS in userspace
  and proxies to loopback (its own output shows `-- / proxy http://127.0.0.1:3000`), and reachability
  is decided by tailnet ACLs. Correctly out of scope — but it must be written down, because "nothing
  is listening" is not the same statement as "only the tailnet can reach it".
- **IP-level belt and braces** — `tailscale up --shields-up` blocks inbound traffic from outside the
  tailnet at the packet level. It would also block the LAN SSH grant, so it is not compatible with
  our break-glass requirement. Noted and rejected, not forgotten.

Nothing above makes the model airtight against a module writing `extraInputRules` directly. The
`mkForce` backstop covers `allowedTCPPorts`, which is the path modules actually use; raw
`extraInputRules` remains a review-level concern.

### Where each rule lives: grants vs policies

Two kinds of rule, two homes. The test is one question: **does it vary per host?**

- **Varies → grants (data).** "SSH on LAN: yes on poweredge, no on erebus" is a decision only the
  operator can make, so it is host config: one visible line, changed by a normal edit.
- **Never varies → policy (lint).** "No container may publish on `0.0.0.0`" is not a decision, it is
  a law. Per host it would be repeated ten times and forgotten on the eleventh, so it is written
  once as code that throws at eval.

Flipping them breaks both ways: SSH-on-LAN in a policy turns every exception into a code change;
the `0.0.0.0` rule in grants means a new host arrives without it and nobody notices.

Laws we would actually encode, from the current tree:

1. **No podman `-p` publish without a `127.0.0.1:` prefix** — poweredge.nix:329
   already documents the footgun in a comment; a comment is not enforcement.
2. **Same port, two services, different grants → throw.** Same port with identical grants is
   legitimate and allowed.
3. **A grant naming a service that produces no firewall entry → throw** (typo protection).

Everything else stays data.

### Open questions, resolved

- **Q1 trustedInterfaces?** No. The tailnet wire is granted per service; trusting the whole
  interface contradicts the goal.
- **Q2 break-glass CIDR rule?** No. The LAN grant *is* the break-glass path.
- **Q3 assertion against `openFirewall`?** Superseded by the `mkForce` backstop; an assertion
  would be optional polish.

### Testability

The poweredge smoke probe gains three assertions on `iptables -S nixos-fw`:
`-i eno1 --dport 22 … accept` exists, `-i tailscale0 --dport 22 … accept` exists, and **no bare
`--dport 22 … accept`** (no `-i`) exists. That is how today's false restriction was caught; it
belongs in the gate, not in a review.

### Migration, step one

Delete `poweredge.nix:331` (`interfaces.eno1.allowedTCPPorts = lib.mkForce [ ]`) and the comment
above it that claims LAN isolation. It is a no-op that documents a property the config does not have.

## Options

### 1. sini (den's author) — quirk carries whole NixOS fragments

```nix
# quirk declaration
den.quirks.firewall.description = "Firewall rules collected from aspects";

# producer (any service aspect) — a plain NixOS fragment
firewall = { networking.firewall.allowedTCPPorts = [ 7654 ]; };

# the only consumer, entire file
den.aspects.core.network.firewall-collector = {
  nixos = { firewall, lib, ... }: lib.mkMerge firewall;
};
```

Interfaces are never parameterised:
- tailnet → `${config.services.tailscale.interfaceName}` (derived from config, correct on every host),
  plus `tailscale0` in `trustedInterfaces`;
- LAN → not an interface rule at all, but a CIDR rule:
  `networking.firewall.extraInputRules = "ip saddr ${environment.networks.default.cidr} tcp dport 22 accept";`
- per-host behaviour → a setting, e.g. `host.settings.core.security.openssh.exposure == "tailnet"`,
  which gates whether the LAN break-glass rule exists.

*Strengths:* minimal code; consumer is one line; interface names never appear; host variation is a setting.
*Weaknesses:* the payload is untyped — a producer can emit anything, including `allowedTCPPorts`
(global), so the "no wildcard" property is a convention, not an enforced one.

### 2. tomwrw/megadots — LAN-scoped quirk, interface declared per host

```nix
den.quirks.firewall = { description = "LAN-scoped ports: { tcp = [ ]; udp = [ ]; }"; };
den.policies.firewall = _: [ (den.lib.policy.pipe.from "firewall" [ den.lib.policy.pipe.expose ]) ];

# consumer
firewall.interfaces.${host.network.lanInterface} = {
  allowedTCPPorts = lib.unique (lib.concatMap (f: f.tcp or [ ]) firewall);
  allowedUDPPorts = lib.unique (lib.concatMap (f: f.udp or [ ]) firewall);
};
```

Host declares `network.lanInterface = "enp8s0"` in `den.hosts`; an eval assertion rejects `""` /
`REPLACE_ME`. The `pipe.expose` policy is required or user-scope declarations are silently dropped.
Stated rationale: *"An aspect should never set `networking.firewall.*` itself, or a module's own
`openFirewall` option, which opens the port everywhere."*

*Strengths:* LAN-only by construction, typed-ish payload, assertion catches a missing interface.
*Weaknesses:* one wire per host (LAN); tailnet needs a second quirk; device name lives in host data.

### 3. nifoc/dotfiles — service aspect names the interfaces directly

```nix
networking.firewall.interfaces = {
  "eth0".allowedTCPPorts = [ 9920 ];
  "tailscale0".allowedTCPPorts = [ 9920 ];
};
```

Variant: read the names from host metadata (`den.aspects.${config.networking.hostName}.meta.networking`).

*Strengths:* obvious, no machinery.
*Weaknesses:* device names duplicated per service; wrong the moment a host renames its NIC
(which happens — `eno1` vs `enp2s0` vs `eth0` across our own fleet).

### 4. Wires/roles payload (our extension of #2)

```nix
firewall = { ports = [ 22 ]; wires = [ "lan" "tailnet" ]; };
den.hosts.<sys>.<host>.network.ifaces = { lan = "eno1"; tailnet = "tailscale0"; };
```

Consumer groups ports per wire with `concatMap` + `genAttrs`; `allowedTCPPorts` (global) stays empty.

*Strengths:* per-service **and** per-wire granularity; device names only in host data.
*Weaknesses:* most code of the four; the grouping logic is ours, not endorsed by any prior art.

### 5. No quirk — host file only

```nix
services.openssh.openFirewall = false;
networking.firewall.interfaces.eno1.allowedTCPPorts = [ 22 ];
networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 22 6333 6334 8000 ];
```

*Strengths:* smallest possible change; no new mechanism; provably closes the wildcard.
*Weaknesses:* per-host duplication; a service added later that sets `openFirewall = true`
re-opens a wildcard silently.

### 6. Status quo — global allow (do nothing)

Every port any module opens is reachable from the LAN. Documented as if it were not.

## Comparison

| | interface names | per-service? | per-wire? | new code | prior art | wildcard-proof |
|---|---|---|---|---|---|---|
| 1 sini | from `config` / CIDR | yes | tailnet+CIDR only | ~1 line | den author | no (convention) |
| 2 megadots | `host.network.lanInterface` | yes | LAN only | ~10 lines | yes | mostly |
| 3 nifoc | hardcoded in service | yes | yes | ~6 lines/service | yes | no |
| 4 wires/roles | `host.network.ifaces` | yes | yes | ~20 lines | no | yes |
| 5 host file | per host, literal | no | yes | ~3 lines/host | common | until next service |
| 6 status quo | — | no | no | 0 | — | n/a |

## Re-scoring the options against the proposed shape

Four properties, in the order they matter. A capital F means the option gives it for free;
"by hand" means you get it only if you remember to write it that way.

| option | services wire-free | fails closed | include-list | eval-validated |
|---|---|---|---|---|
| **proposed** (grants) | yes | yes (no grant = closed) | yes | yes (unknown service/wire = error) |
| 1 sini | yes | no — a fragment can open globally | no — fragments are per-host ad hoc | no — payload untyped |
| 2 megadots | no — LAN is the only wire | yes, for LAN | yes | partly — asserts `lanInterface` set |
| 3 nifoc | no — names devices | yes, if names are right | yes | no — a bad device name never matches |
| 4 wires/roles | no — `wires` in the service | yes | yes | partly — wires must be validated |
| 5 host file | yes | yes | yes | no — literals, nothing to validate |
| 6 status quo | n/a | no | n/a | n/a |

What each one really is, in one line:

- **1 sini** — maximum freedom, zero guarantees. Its own author's shape works because he never
  needs the guarantee; the type system is `mkMerge`.
- **2 megadots** — the only prior art that enforces "LAN only" structurally. Its limitation is
  the product decision, not the implementation: one wire.
- **3 nifoc** — the honest simple version, and the one that breaks first (device names in services).
- **4 wires/roles** — megadots generalised, at the cost of inventing a wire vocabulary.
- **5 host file** — exactly right for one host, exactly the duplication that rots at five.
- **6 status quo** — what we have, and it is not what the config says we have.

Verdict: no repo out there implements the proposed shape. The closest combination is
**megadots' fail-closed-by-construction payload** plus **sini's wire-free services**, with the
missing half being validation — which is the part nobody writes because it needs the service
names to be a closed set.

## Open questions

1. Is `trustedInterfaces = [ "tailscale0" ]` acceptable as the tailnet side of every service,
   instead of enumerating ports per interface? (sini does this; it trusts the whole interface.)
2. Does the break-glass LAN SSH rule matter enough to justify a CIDR rule that duplicates
   what the LAN interface rule would say?
3. Do we want an eval assertion that fails when a module's `openFirewall` is true for a port we
   did not declare? (That is the only way to make "wildcard-proof" real.)

## References

- nixpkgs `sshd.nix:312`, `:874`; `moonshine.nix:103-145`
- issues [#41459](https://github.com/NixOS/nixpkgs/issues/41459), [#23181](https://github.com/NixOS/nixpkgs/issues/23181)
- den docs: `guides/quirks.mdx` ("Quick start: firewall ports"), `reference/quirks.mdx`
- prior art: sini/nix-config, tomwrw/megadots, nifoc/dotfiles, lorenzorapetti/nix,
  muhammadtalha-quant/nixden, auscyber/dotfiles, icebluerabbit/denful-networks
