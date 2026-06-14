# PAM, Display Managers, and GNOME Keyring

## Problem

After rebooting, NetworkManager sometimes forgot WiFi passwords. The
passwords were stored in GNOME Keyring, but the keyring was not
auto-unlocked at login because `dms-greeter` (traversal's display
manager) lacked the necessary PAM configuration.

## What is PAM?

**P**luggable **A**uthentication **M**odules — a framework for
authentication in Linux. Each service (login, sudo, sshd, etc.) has a
PAM config file in `/etc/pam.d/<service>` defining a chain of modules
run on:
- `auth` — verify credentials
- `account` — check account validity
- `password` — handle password changes
- `session` — setup/teardown per session

## How greeters use PAM

- `dms-greeter` creates a PAM service at `/etc/pam.d/dms-greeter`
- On login via dms-greeter, PAM runs through the chain
- `pam_gnome_keyring.so` is a PAM module that:
  - `auth`: starts the gnome-keyring daemon
  - `session`: unlocks the login keyring using the user's login
    password (requires matching passwords)
- Without `pam_gnome_keyring.so`, gnome-keyring starts but stays
  locked → applications (NetworkManager, Chromium, etc.) can't read
  stored secrets

## Does screen lock lock the keyring?

No. The keyring unlocks once at login and stays unlocked until logout
or reboot. This is the standard behavior across all desktop
environments.

To manually lock: `dbus-send --session --dest=org.freedesktop.secrets
--type=method_call /org/freedesktop/secrets
org.freedesktop.Secret.Service.Lock
array:objpath:/org/freedesktop/secrets/collection/login`

## The fix

### 1. PAM — `dank-material-shell.nix`

```nix
security.pam.services.dms-greeter = {
  gnomeKeyring = true;
};
```

Tells NixOS to add `pam_gnome_keyring.so` to dms-greeter's PAM session
stack. On next login via dms-greeter, PAM runs the module → unlocks
the login keyring → NetworkManager can read WiFi passwords.

### 2. Secrets Portal — `package-sources.nix`

```nix
"org.freedesktop.impl.portal.Secret" = [ "gnome-keyring" ];
```

Ensures D-Bus secret service requests (from flatpaks, sandboxed apps)
use gnome-keyring as the backend. `xdg-desktop-portal-gnome` is
already pulled in by the niri aspect's `extraPortals`.
