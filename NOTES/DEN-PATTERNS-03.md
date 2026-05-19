Yes, while using `._` (the implicit "spread" or "all-children" accessor) is a fast way to grab everything under a namespace, it can sometimes become opaque—especially when you need to troubleshoot exactly which aspect broke an evaluation.

If you want alternative ways to bundle and include those common core aspects, here are three structural patterns you can use within Den that offer different levels of control.

### 1. The Explicit "Bundle" Aspect (Recommended)

Instead of relying on the implicit `._` wildcard, you can turn `common-core` itself into a meta-aspect that explicitly lists its dependencies using the `includes` array.

This is the most "Den-native" way to compose configurations because it acts as a self-documenting manifest.

```nix
# den/aspects/desktop/common-core/default.nix
{
  # explicitly declare what makes up the "common-core"
  includes = [
    den.aspects.desktop.common-core.audio
    den.aspects.desktop.common-core.fonts
    den.aspects.desktop.common-core.wayland
  ];

  # You can also add baseline configs directly here
  nixos.networking.networkmanager.enable = true;
}

```

**How to use it:**
When configuring your main machines, you just point to the parent aspect. Den will automatically resolve the tree.

```nix
den.hosts.x86_64-linux.serenity.includes = [ den.aspects.desktop.common-core ];
den.hosts.x86_64-linux.traversal.includes = [ den.aspects.desktop.common-core ];

```

### 2. The `den._.import-tree` Pattern

If your `common-core` aspects are physically organized in a dedicated directory and you strictly want a data-driven pipeline (like Adda's config), you can use Den's tree importer. This reads the filesystem directory and loads all `.nix` files as aspects automatically.

```nix
# In your main flake.nix or entrypoint
den.aspects.desktop.common-core = den._.import-tree ./aspects/desktop/common-core;

```

You can then combine this with `includes` at the host level. It functionally achieves the same thing as `._` but happens explicitly at the pipeline's ingestion phase, meaning you can easily pipe or filter the imported tree before it applies to the host.

### 3. Contextual Injection via Policies (The "Targeted" Pattern)

If your `common-core` contains aspects that should *only* apply if certain conditions are met, you can move away from direct inclusion entirely and use Policies to map the aspects dynamically.

Instead of saying "serenity includes common-core," you write a policy that says, "If a machine is classified as a desktop, inject the common-core aspects."

```nix
# Define a policy that targets specific hosts
den.policies.desktop-core = {
  # Apply this only to specific machines in your inventory
  targets = [
    den.hosts.x86_64-linux.serenity
    den.hosts.x86_64-linux.traversal
    den.hosts.x86_64-linux.salembox
  ];

  # What to inject into those targets
  aspects = [
    den.aspects.desktop.common-core.audio
    den.aspects.desktop.common-core.fonts
  ];
};

```

### Which should you choose?

* Use the **Explicit Bundle (`includes`)** if you want maximum readability and want to know exactly what comprises your desktop environment at a glance.
* Stick to your current **`._` or `import-tree**` if you are rapidly prototyping and just want to drop a new `.nix` file into the `common-core` folder and have it instantly apply everywhere without touching an index file.
* Use **Policies** if you want to decouple the aspects from the hosts entirely and manage the relationships from a top-down view.




---


Here is a concrete structural blueprint mapping your specific fleet—combining your daily drivers, servers, and HTPC appliances—into a multi-file layout using Den's modern API design patterns.

---

### 1. The Fleet Directory Structure

To keep your configuration clean, isolate your structural data from your functional configuration modules:

```text
.
├── flake.nix
└── aspects/
    ├── hardware/
    │   ├── serenity.nix
    │   └── poweredge.nix
    ├── profiles/
    │   ├── workstation.nix
    │   └── storage-server.nix
    └── identities/
        ├── likivik.nix
        └── watcher.nix

```

---

### 2. `flake.nix`: The Central Inventory & Policy Registry

This serves as your pure inventory dataset. You define your hosts and users, then group them into operational environments using **Policies**.

```nix
{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    home-manager.url = "github:nix-community/home-manager";

    # Target Den Framework
    den.url = "github:denful/den";
  };

  outputs = { self, nixpkgs, den, ... }@inputs:
    den.lib.engine {
      inherit inputs;

      # Define your machine inventory
      den.hosts.x86_64-linux = {
        serenity            = { includes = [ ./aspects/hardware/serenity.nix ./aspects/profiles/workstation.nix ]; };
        traversal           = { includes = [ ./aspects/profiles/workstation.nix ]; };
        spectacle           = { includes = [ ./aspects/profiles/htpc.nix ]; };
        homelab01-poweredge = { includes = [ ./aspects/hardware/poweredge.nix ./aspects/profiles/storage-server.nix ]; };
        devbox01            = { includes = [ ./aspects/profiles/sandbox.nix ]; };
        nixosrouter         = { includes = [ ./aspects/profiles/router.nix ]; };
        salembox            = { includes = [ ./aspects/profiles/workstation.nix ]; };
      };

      # Define human/appliance identities
      den.users = {
        likivik = { includes = [ ./aspects/identities/likivik.nix ]; };
        salem   = { includes = [ ./aspects/identities/salem.nix ]; };
        watcher = { includes = [ ./aspects/identities/watcher.nix ]; };
      };

      # Policies bind infrastructure configurations together dynamically
      den.policies = {
        daily-drivers = {
          hosts = [ "serenity" "traversal" ];
          users = [ "likivik" ];
        };
        server-fleet = {
          hosts = [ "homelab01-poweredge" "devbox01" "nixosrouter" ];
          users = [ "likivik" ]; # Single user profile used for server management
        };
        kiosk-appliances = {
          hosts = [ "spectacle" ];
          users = [ "watcher" "likivik" ]; # watcher handles media, likivik can SSH
        };
        shared-desktops = {
          hosts = [ "salembox" ];
          users = [ "salem" "likivik" ];
        };
      };
    };
}

```

---

### 3. `aspects/identities/likivik.nix`: The Polymorphic User

Instead of duplicating yourself into a `likiviks` profile for servers, use Den's `perUser` runtime context evaluation. Your user profile dynamically sheds or adds configurations depending on the underlying machine class.

```nix
{ den, lib, ... }: {
  den.aspects.user-likivik = {
    # System-level configurations across ALL targets
    nixos = { pkgs, ... }: {
      users.users.likivik = {
        isNormalUser = true;
        extraGroups = [ "wheel" "networkmanager" ];
        shell = pkgs.zsh;
        openssh.authorizedKeys.keys = [ "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5..." ];
      };
    };

    # Context-driven Home Manager: Mutates based on target host metadata
    homeManager = den.lib.aspects.perUser ({ host, user }:
      let
        # Flag hosts requiring a desktop graphical interface
        isGraphical = lib.elem host.name [ "serenity" "traversal" "salembox" ];
      in {
        # Headless baseline configurations (Applied everywhere, even servers)
        programs.zsh.enable = true;
        programs.git = {
          enable = true;
          userName = "likivik";
        };

        # Graphical-only overrides (Omitted on homelab01, devbox01, nixosrouter)
        home.packages = lib.optionals isGraphical [
          pkgs.vscode
          pkgs.firefox
          pkgs.mpv
        ];

        # Conditionally load desktop configuration modules
        imports = lib.optionals isGraphical [
          ../../modules/desktop/hyprland.nix
        ];
      }
    );
  };
}

```

---

### 4. `aspects/profiles/htpc.nix`: Forwarding Cross-Class "Batteries"

This demonstrates how an appliance configuration manages both system overrides (`nixos`) and user behaviors (`homeManager`) for an isolated target machine within a single definition file.

```nix
{ den, lib, ... }: {
  den.aspects.htpc = {
    # System layer: Force automatic login to the kiosk space
    nixos = { ... }: {
      services.displayManager.autoLogin = {
        enable = true;
        user = "watcher";
      };

      # Audio and low-power hardware tweaks for media playback
      services.pipewire.enable = true;
      powerManagement.cpuFreqGovernor = "powersave";
    };

    # Provision the targeted home user configuration right inside the host aspect
    homeManager = den.lib.aspects.perUser ({ host, user }:
      lib.mkIf (user.userName == "watcher") {
        # Boot direct-to-kiosk media manager environment
        wayland.windowManager.sway = {
          enable = true;
          config = {
            terminal = "foot";
            startup = [
              { command = "stremio --fullscreen"; }
            ];
          };
        };
      }
    );
  };
}

```



