# Erebus Provisioning (Numtide flow)

**Host:** erebus  
**IP:** 148.253.214.185  
**Theme:** Chthonic — servers that live in the dark

## 1. Manual steps

### Step 1: Get age pubkey from VPS

```bash
ssh root@148.253.214.185 cat /etc/ssh/ssh_host_ed25519_key.pub | ssh-to-age
```

Outputs `age1...` — copy this for Step 2.

### Step 2: Edit `.sops.yaml`

```bash
micro secrets/.sops.yaml
```

Changes in the editor:
- Line 20: replace `&erebus age1...` with the value from Step 1 output (keep the `&erebus` anchor)

### Step 3: Commit `.sops.yaml`

```bash
git add secrets/.sops.yaml
git commit -m "feat(erebus): add age pubkey to sops config"
```

nixos-anywhere's sops-nix reads this config from the flake. If not committed, sops decrypt fails on first boot.

### Step 4: Re-encrypt secrets

```bash
sudo sops updatekeys -y secrets/erebus/secrets.yaml
sudo sops secrets/erebus/secrets.yaml
```



### Step 5: Pre-flight checklist

- [ ] `ssh root@148.253.214.185 lsblk` — disk device matches `_disko.nix`
- [ ] Age pubkey added to `secrets/.sops.yaml` (&erebus `age1...`)
- [ ] `git log -1` shows `.sops.yaml` commit
- [ ] Step 4 completed — secrets re-encrypted with real values
- [ ] `nix flake check --no-build --keep-going` — all hosts pass
- [ ] `ssh root@148.253.214.185 'uname -r'` — VPS runs kexec-compatible kernel (not OpenVZ/LXC)
- [ ] `ssh-keygen -R 148.253.214.185` — only if VPS was previously NixOS with a different key; Ubuntu key will be preserved

### Step 6: Run nixos-anywhere

`--copy-host-keys` preserves the VPS's existing SSH keys in the new NixOS install.
No `--extra-files` needed — authorized keys are declared in `erebus.nix`, age key is derived from the preserved SSH key at boot.

```bash
nixos-anywhere \
  --flake .#erebus \
  --copy-host-keys \
  --generate-hardware-config nixos-facter ./modules/hosts/erebus/facter.json \
  --target-host root@148.253.214.185
```

### Step 7: After reboot (verify)

Reboot takes 1-5 min. Retry SSH until it responds:

```bash
until ssh -o ConnectTimeout=10 likivik@148.253.214.185 true; do sleep 5; done
```

Once connected:

```bash
# Verify sops decrypted secrets
sudo systemctl status sops-nix --no-pager
ls /run/secrets/tailscale/auth-key
sudo journalctl -u sops-nix --no-pager | tail -20

# Verify Tailscale joined
tailscale status
```

**No cleanup needed** — nothing was generated locally (except `.sops.yaml` changes which are already committed).

### Step 8: Commit generated files

```bash
git add modules/hosts/erebus/facter.json
git add modules/hosts/erebus/_hardware-configuration.nix   # if updated
git commit -m "feat(erebus): add facter.json and hardware config"
git push
```

---

## Troubleshooting

### nixos-anywhere fails at build step (before disko)

If nixos-anywhere errors during the build phase (derivation evaluation), **the VPS is untouched** — no kexec, no disko, no changes. Fix the flake error locally, re-run nixos-anywhere. The VPS is still running its original OS, SSH still works.

```bash
# Verify VPS still reachable and unchanged
ssh root@148.253.214.185 hostnamectl
```

### nixos-anywhere fails mid-way

If disko destroys partitions but install/reboot fails (network drop, OOM):

1. **Don't reboot manually** — VPS is in kexec'd installer, no bootable OS
2. Try `ssh root@148.253.214.185` (new temp SSH key in installer)
3. If unreachable: re-run nixos-anywhere — it re-kexecs and retries
4. Fix the cause (disk device, RAM, flake error), re-run

nixos-anywhere is idempotent. Provider rescue mode is last resort.

### disko phase fails (wrong disk device)

```bash
ssh root@148.253.214.185 lsblk -ndo NAME | grep -v loop | head -1
# Edit _disko.nix device path to match, re-run
```

---

## 2. Q&A

**Q: Can nixos-anywhere auto-detect the disk device?**  
A: No. It uses `_disko.nix` as-is. Wrong device → disko phase fails harmlessly. Check with `lsblk`, edit, re-run.

**Q: How does sops get its age key on the VPS?**  
A: sops-nix is configured with `sops.age.sshKeyPaths = [ "/etc/ssh/ssh_host_ed25519_key" ]`. On boot, it runs `ssh-to-age` internally to derive the age key from the SSH key. No age key file is stored.

**Q: How does the SSH key survive into NixOS?**  
A: `--copy-host-keys` in nixos-anywhere copies the VPS's existing `/etc/ssh/ssh_host_*` from Ubuntu into the new install. The key never changes, so no host key warning on first SSH.

**Q: What needs to be generated locally?**  
A: Nothing. The SSH key stays on the VPS. The age pubkey flows through your terminal as a pipe. The only file added to your repo is `.sops.yaml` (the pubkey line).

**Q: Why no `--extra-files`?**  
A: authorized_keys are declared in `erebus.nix` via `users.users.likivik.openssh.authorizedKeys.keys`. nixos-anywhere applies the Nix config during install — the keys are there on first boot.

**Q: What happens on each nixos-anywhere phase?**  
A: 1) kexec (reboot into NixOS installer). 2) disko (destroy partitions, create per `_disko.nix`). 3) install (copy closure, `--copy-host-keys` copies SSH keys, Nix config applied). 4) reboot into new NixOS.

**Q: How to verify the VPS is still alive after a build failure?**  
A: `ssh root@148.253.214.185 hostnamectl` — if it responds, VPS is unchanged (build errored before kexec). Fix flake, re-run.

**Q: What do Numtide themselves use?**  
A: This exact flow — they built `--copy-host-keys` and `ssh-to-age` to solve this exact problem. No local keygen, no extra-files, one command.

**Q: Is this reproducible for monthly re-creation?**  
A: Yes. Each new VPS has its own SSH host key. You SSH in once, pipe to ssh-to-age, add to `.sops.yaml`, re-encrypt secrets, run nixos-anywhere with `--copy-host-keys`. About 8 steps, all documented above.

**Q: What if the VPS's SSH key changes between now and nixos-anywhere?**  
A: Can't happen — nixos-anywhere runs immediately after getting the pubkey. The pubkey goes into `.sops.yaml` at the same moment the key is live.

**Q: 2FA for SSH?**  
A: Tailscale mesh VPN (`lockSshToTailscale = true`) — SSH only listens on `tailscale0`, unreachable from public internet.
