# AMD GPU freezes & RADV_PERFTEST=cswt

## The `nh os switch` failure

`home-manager-likivik.service` failed during `nh os switch`. Logs showed:

```
ln: failed to create symbolic link '/home/likivik/.config/systemd/user/tray.target': Read-only file system
```

Reason: the target dir `~/.config/systemd/user` was a symlink to `/nix/store/...-user-units` —
the Nix store is read-only, so `ln` fails with EROFS.

## How that symlink got there

NixOS creates `~/.config/systemd/user` as a store link when any `systemd.user.*` option is
set at NixOS level. `modules/hosts/traversal/traversal.nix` had:

```nix
systemd.user.services.dms.environment.RADV_PERFTEST =
  lib.mkIf config.programs.dms-shell.enable "cswt";
```

This single override triggers the entire user-units derivation (which has nothing else — it
produces an empty directory), and the activation script symlinks `~/.config/systemd/user`
to that store path.

## Root cause: AMD GPU + DMS compositor

The env var is needed because DMS compositor uses Vulkan via RADV (Mesa's AMD Vulkan driver).
On AMD GPUs, the compositor freezes on login without it.

### How `cswt` was discovered

1. The commit (`ff49882`) message said: `"cswt enables the compute-shader-with-triangle path in
   RADV, required for proper Vulkan rendering in DMS compositor on AMD GPUs."`
2. Searched the niri upstream issue tracker for similar AMD freeze reports.
3. Found issue #2339 where someone set `RADV_PERFTEST "video_decode"` inside niri's
   `environment {}` KDL config block — this is the idiomatic way to pass env vars to the
   compositor session in niri.
4. The existing `modules/users/likivik/dotfiles/niri/config.kdl` already had an
   `environment {}` block for `XDG_CURRENT_DESKTOP`, `QT_QPA_PLATFORM`, etc.
5. DMS runs as a child of niri, so env vars set by niri's `environment {}` block are
   inherited by DMS automatically. This avoids the `systemd.user.*` NixOS path entirely.

## Related upstream issues

### niri#684 — Severe freeze on session re-entry

**Status**: open since Sep 2024, last comment Jun 2026.  
**Bug**: Compositor freezes after logging out and back in, or switching TTYs and returning.
TTYs become unresponsive, requires hard reboot.  
**Affects**: AMD (RX 590, Radeon 6600, Radeon HD 6730M) and NVIDIA.  
**Root cause**: DRM device returns `Permission denied` after session restore — the compositor
loses access to `/dev/dri/card1`. Not display-manager-specific (happens with LightDM, GDM,
SDDM, and no-DM setups).  
**Workaround**: `video` group membership helps some users.  
**Upstream**: maintainer (@YaLTeR) needs help from someone experienced with DRM — no fix in
sight. Link: https://github.com/niri-wm/niri/issues/684

### niri#3719 — Laptop monitor freeze after lid close/open

**Status**: open since Mar 2026.  
**Bug**: Turn monitor off (lid close) and back on → screen frozen. Only visible on the same
GPU as traversal (AMD Radeon 890M). Recovery: switch refresh rate or restart session.  
**Root cause**: missing surface in vblank callback after reconnecting.  
**Upstream**: no fix yet. Link: https://github.com/niri-wm/niri/issues/3719

### niri#2344 — Random compositor freeze + crash on AMD

**Status**: closed as "not niri:hardware" (Mesa/AMDGPU driver issue).  
**Bug**: Compositor crashes randomly with `GL_INVALID_VALUE` errors on AMD RX 6800 XT + Mesa.  
**Upstream**: marked as driver bug, no fix in niri. Link: https://github.com/niri-wm/niri/issues/2344

## The fix

Moved `RADV_PERFTEST=cswt` from `systemd.user.services.dms.environment` (NixOS-level,
triggers read-only symlink) to niri's `environment {}` block (session-level, no side
effects). NixOS no longer creates `~/.config/systemd/user`, so home-manager can write
`tray.target` freely.
