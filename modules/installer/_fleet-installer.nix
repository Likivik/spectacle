# Fleet installer ISO — reusable for all bare-metal deploys
# Build: nix build .#packages.x86_64-linux.installer
{ config, lib, pkgs, modulesPath, ... }:
{
  imports = [
    (modulesPath + "/installer/cd-dvd/installation-cd-minimal.nix")
  ];

  # --- Console access ---
  # Password for the live user (login at physical console)
  users.users.nixos = {
    initialPassword = "nixos";
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" ];
  };

  # Allow wheel group to sudo without password (for nixos-anywhere bootstrap)
  security.sudo.wheelNeedsPassword = false;

  # --- SSH access ---
  services.openssh = {
    enable = true;
    settings = {
      PermitRootLogin = "yes";
      PasswordAuthentication = true;   # allow SSH with password
    };
  };

  # Authorized keys for the nixos user (SSH key auth also works)
  users.users.nixos.openssh.authorizedKeys.keys = [
    # traversal-likivik-2024-07-rsa
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
    # serenity ed25519
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
  ];

  # --- Networking ---
  # Ensure network is up on boot (DHCP on all wired interfaces)
  networking.networkmanager.enable = true;
  networking.useDHCP = lib.mkDefault true;

  # --- Fleet deployment tools ---
  environment.systemPackages = with pkgs; [
    nixos-anywhere    # remote deployment
    nixos-facter      # hardware detection
    disko             # declarative disk partitioning
    git               # clone spectacle
    curl              # general purpose
  ];

  # --- ISO image settings ---
  # Compression: keep ISO reasonably small
  isoImage.squashfsCompression = "lz4";
}
