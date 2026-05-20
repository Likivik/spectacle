### Deterministic UIDs/GIDs

-   **The Problem:** NixOS default IDs are "first-come, first-served." If you rebuild or migrate, IDs can shift, breaking file permissions on your ZFS pools, backups, and shared storage.
-   **The Strategy:** Use a **Hybrid Approach**.

    -   **Manual Assignment:** For your primary human users (e.g., `likivik`, `salem`), hardcode fixed IDs (e.g., `1000`, `1001`) in your config. They never change.
    -   **Automated Hashing:** For service/system users (e.g., `nextcloud`, `torrent-server`), use a small Nix module that hashes the service name to generate a stable, fixed ID.
-   **The Goal:** Every machine in your infrastructure sees the exact same UID for the same user or service, ensuring your permissions stay intact regardless of the host.
-   **Avoid `DynamicUser`:** It is convenient for ephemeral services, but it creates "black box" IDs that make backups, debugging, and cross-host data sharing difficult. Stick to predictable, fixed IDs for anything with persistent state.