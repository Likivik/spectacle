# Den Framework — 3 Global Patterns

Three ways to think about Den. Pick the one that fits your use case.

---

## Pattern 1: Feature Aspect

Wrap a piece of functionality into a self-contained aspect. Declare system config, user config, or both. Anyone can include it by name.

```nix
{ den, ... }: {
  den.aspects.direnv = {
    nixos = { pkgs, ... }: {
      programs.direnv.enable = true;
    };
    homeManager = { pkgs, ... }: {
      programs.direnv = {
        enable = true;
        enableBashIntegration = true;
      };
    };
  };
}
```

Consumer adds it to their includes:

```nix
den.aspects.my-feature.includes = [ den.aspects.direnv ];
```

**When to use**: you have a self-contained tool/setting that belongs on multiple hosts or for multiple users. Write once, include anywhere.

---

## Pattern 2: Host Assembly

Build a host by composing aspects. The host aspect is a shopping list of features + local hardware config.

```nix
den.aspects.serenity = {
  includes = [
    den.aspects.core._               # auto-collects bootloader + locale + nix + determinate
    den.aspects.desktop.common-core._ # auto-collects networking + peripherals + printers + ...
    den.aspects.desktop.desktopManagers.kde
    den.aspects.firefox
  ];
  nixos = {
    # host-local only: disks, GPU, kernel modules
    fileSystems."/" = { device = "/dev/sda1"; fsType = "ext4"; };
    hardware.cpu.intel.updateMicrocode = true;
  };
};
```

The `_` wildcard auto-collects every child aspect in that namespace — no need to list them one by one. You can also be selective and pick individual aspects instead.

**When to use**: you're defining a host. Its aspect is where you list features and add machine-specific details.

---

## Pattern 3: Global Project Config

One file (`defaults.nix`) for project-wide settings: state version, batteries, class assignment, shared NixOS options.

```nix
{ lib, den, ... }: {
  # system-wide defaults
  den.default.nixos.system.stateVersion = "25.11";
  den.default.nixos.networking.firewall.enable = true;
  den.default.homeManager.home.stateVersion = "25.11";

  # batteries: auto-injected into all host/user entity resolutions
  den.default.includes = [
    den.provides.define-user     # auto-creates OS users from host declarations
    den.provides.hostname        # auto-sets hostname from entity name
    den.provides.mutual-provider # enables user↔host cross-referencing
  ];

  # class assignment: all users get homeManager by default
  den.schema.user.classes = lib.mkDefault [ "homeManager" ];

  # host-level HM config: applies to every host with HM users
  den.schema.hm-host.includes = [{
    nixos = {
      home-manager.useGlobalPkgs = true;
      home-manager.useUserPackages = true;
    };
  }];
}
```

**When to use**: you want a setting to apply everywhere, avoid repeating yourself, or change the default class assignment for users.
