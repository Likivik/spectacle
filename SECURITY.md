# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** — do not open a public
issue. Use GitHub's private vulnerability reporting: **Security → Report a
vulnerability** on this repository.

Include what you found, the path or file involved, and how to reproduce it.

## Assume everything here is public

This is a NixOS fleet configuration and the repository is public, so treat every
tracked file as public knowledge. That shapes what is safe to commit:

- `secrets/**` holds sops-encrypted (age) values. Ciphertext is safe to publish
  **only** because the private identities never leave the hosts.
- Age private identities live on the hosts — `/var/lib/sops-nix/...`, or sealed to
  the local TPM. They must never appear in the repository, in a Nix store path, or
  in a build artefact.
- A plaintext credential in any tracked file is a bug. Please report it rather
  than assuming it is a test fixture.

## Hardening in place

- **`main` is protected**: no direct pushes and no bypass actors (not even
  admins), linear history, squash-only merges, and three required status checks.
- **Every GitHub Action is pinned to a full commit SHA**, with Dependabot keeping
  them current. The repository's Actions policy allows only GitHub-owned and
  verified publishers, plus an explicit allowlist for anything else.
- **Secret scanning and push protection are enabled**, so a credential is caught
  before it is pushed rather than after.
- **Dependabot alerts and security updates, CodeQL code scanning, and private
  vulnerability reporting are enabled.**
- The VM smoke gate is a deliberate manual step rather than a CI check, and its
  dummy secrets are encrypted to an identity generated at build time — no private
  key is committed for it.
