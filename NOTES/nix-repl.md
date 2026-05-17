
---

### 1. Enter the REPL

From your project root (where your `flake.nix` lives), run:

```bash

nix repl .

# inside the repl (to load the flake):
:lf .
```

If you are degugging `den` - add `flake.den = den;` anywhere in the config. You will see `den` in the list when entering the `repl`

---

### 2. Locate your Host

Once inside the REPL, you can start typing to see what's available. Type this and hit **Tab** to auto-complete:

```nix
nixosConfigurations.
```
You should see your hostnames (e.g., `hostname1`, `hostname2`). Pick one and press Enter. You will see something like:
```
{
  _module = { ... };
  _type = "configuration";
  class = "nixos";
  config = { ... };
  extendModules = «lambda extendModules @ /nix/store/khpq2yy9vx39j534f1yd55z5y7b86adp-source/nixos/lib/eval-config.nix:141:23»;
  extraArgs = { ... };
  graph = [ ... ];
  lib = { ... };
  options = { ... };
  pkgs = { ... };
  type = { ... };
}
```

---

### 3. Inspect Specific Parts

```nix
nixosConfigurations.spectacle.config.users.users
```

---

### Quick Tips
*   **Exit REPL:** Type `:q` or press `Ctrl+D`.
*   **Reload:** If you change your code, type `:r` to reload the flake without exiting.
