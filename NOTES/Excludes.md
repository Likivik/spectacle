



#### The Attribute Removal Pattern (builtins.removeAttrs)

```nix
den.hosts.x86_64-linux.salembox.includes =
  builtins.attrValues (builtins.removeAttrs den.aspects.desktop.common-core [
    "heavy-greeter"
    "custom-keybinds"
  ]);
```

---

#### The List Filter Pattern (builtins.filter)

```nix
  den.hosts.x86_64-linux.salembox.includes = builtins.filter
  (aspect: !(builtins.elem aspect [
    den.aspects.desktop.common-core.heavy-greeter
    den.aspects.desktop.common-core.custom-keybinds
  ]))
  den.aspects.desktop.common-core._;
```

---

#### Guards inside the Aspect

```nix
# Inside den/aspects/desktop/common-core/bluetooth.nix
{
  # Only apply this aspect if the target host is NOT spectacle
  guard = { host, ... }: host.name != "spectacle";

  nixos.hardware.bluetooth.enable = true;
  nixos.services.blueman.enable = true;
}
```