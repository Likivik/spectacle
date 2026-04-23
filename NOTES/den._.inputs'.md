> Caution: AI Slop - Status: Unverified


# Explain `den._.inputs'`

## 🛠 Example: Installing a Package from Unstable

In a standard NixOS configuration, you might want to pull one specific app from an "unstable" flake input while the rest of your system stays on "stable."

### 1. Define the inputs in `flake.nix`
```nix
{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-24.11"; # Stable
    unstable.url = "github:nixos/nixpkgs/nixos-unstable"; # Unstable
  };
}
```

### 2. Use `den._.inputs'` in your NixOS module 

Using the `den._.inputs'` aspect allows you to reference `unstable` directly without worrying about whether the current machine is `x86_64-linux` or `aarch64-linux`. 

```nix
{ den, ... }: # The 'den' argument is injected by the framework
{
  # We "include" the inputs' aspect to make it available
  den.default.includes = [ den._.inputs' ];

  den.aspects.gaming.nixos = { pkgs, inputs', ... }: {
    environment.systemPackages = [
      # Standard package from the host's nixpkgs
      pkgs.steam 
      
      # Specific package from the 'unstable' input
      # 'inputs'' automatically points to the correct system architecture
      inputs'.unstable.legacyPackages.discord
    ];
  };
}
```

### Why it is useful

-   **No "system" Boilerplate:** You don't have to write `${pkgs.system}` or `x86_64-linux` everywhere. This makes your modules **portable** across different hardware (like a Mac laptop and an Intel server).
  
-   **Cleaner Code:** Instead of deep nested paths like `inputs.hyprland.packages.${system}.default`, you can simply use `inputs'.hyprland.default`.





