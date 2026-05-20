### Kanidm Redundancy & Offline Architecture

#### 1\. Server Redundancy (Multi-Master Replication)

Kanidm features native **active-active replication** over your Local Area Network (LAN). No internet required.

-   **Setup:** Run the Kanidm server daemon on both `homelab01-poweredge` and `devbox01`.
-   **Resilience:** Both nodes process requests independently. If one goes offline, the other handles your LAN seamlessly. They auto-sync once connectivity restores.

#### 2\. Laptop Resilience (`traversal`)

You do not need the server daemon on your laptop. Kanidm handles flaky networks and offline logins via **Local Offline Caching**.

-   **The Mechanic:** The client service (`kanidm-unixd`) is a systemd daemon that starts at boot _before_ the login screen appears.
-   **Handshake:** If home servers are unreachable, the daemon safely times out and authenticates your password against an encrypted local credential cache.

#### 3\. The Emergency Safety Net

Always preserve a local fallback account. NixOS configures PAM to check local files (`/etc/passwd`) before querying Kanidm. If the network or cache completely fails, you can still log in locally to repair the system.

### Implementation Mapping in Den

```nix
# den/aspects/profiles/identity-server.nix
{
  # Target: homelab01 and devbox01
  services.kanidm = {
    enableServer = true;
    # (Configure database replication endpoints here)
  };
}
```


```nix
# den/aspects/profiles/identity-client.nix
{
  # Target: All hosts (including your laptop)
  services.kanidm = {
    enableClient = true;
    clientSettings.uri = "https://idm.homelab.internal";
  };

  # Local Safety Net: Hardcoded emergency backup user on the metal
  users.users.admin-rescue = {
    isNormalUser = true;
    extraGroups = [ "wheel" ];
    hashedPassword = "your-safely-encrypted-sops-nix-password-hash";
  };
}
```