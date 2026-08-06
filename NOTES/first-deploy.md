# First-deploy checklist

One-time setup for adding a new host to the fleet. Run these **on the new host itself** (or via SSH from another host with admin access) before the first `nixos-rebuild switch`.

## SSH key auth

`nixos-rebuild --target-host` needs the **calling** host's `~/.ssh/id_*` in the new host's `authorized_keys`.

- Agent key: `/var/lib/hermes/.ssh/id_ed25519` (comment `hermes@erebus`, label only — same key on every host).
- Add it to `modules/hosts/<new-host>/<new-host>.nix` under `users.users.likivik.openssh.authorizedKeys.keys`, then deploy.
- Or route the first deploy through a 3rd host where both halves of the auth chain already work.

## Other first-deploy items

- (Add more as they come up — Tailscale ACL tags, sops keyring, ZFS import, etc.)
