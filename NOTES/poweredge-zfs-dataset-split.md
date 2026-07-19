# Poweredge ZFS Dataset Split Plan

## Current State
- Single `tank/data` dataset mounted at `/tank/data`
- Used by:
  - Nextcloud: `/tank/data/nextcloud`
  - Immich: `/tank/data/immich`
- recordsize=1M, compression=lz4

## Proposed Datasets

### tank/nextcloud
- **Mountpoint**: `/tank/nextcloud`
- **recordsize**: 128K (mixed small/medium files)
- **compression**: lz4
- **Rationale**: Nextcloud has mixed workloads (documents, photos, some videos). 128K balances small file efficiency with large file performance.

### tank/immich
- **Mountpoint**: `/tank/immich`
- **recordsize**: 1M (large media files)
- **compression**: lz4
- **Rationale**: Immich stores large photos/videos with sequential read patterns. 1M optimizes for this.

### tank/backups
- **Mountpoint**: `/tank/backups`
- **recordsize**: 1M (backup streams)
- **compression**: zstd (better compression ratio)
- **Rationale**: Destination for syncoid replication and local backups. zstd provides better compression for backup data.

### tank/media
- **Mountpoint**: `/tank/media`
- **recordsize**: 1M (large video files)
- **compression**: lz4
- **Rationale**: For Plex/Jellyfin or shared media. Prepared for future expansion.

### tank/downloads
- **Mountpoint**: `/tank/downloads`
- **recordsize**: 1M (large sequential writes)
- **compression**: lz4
- **refquota**: 500G (prevent filling the pool)
- **Rationale**: For torrent/usenet downloads. Quota prevents accidental pool exhaustion.

### tank/containers
- **Mountpoint**: `/tank/containers`
- **recordsize**: 128K (mixed container workloads)
- **compression**: lz4
- **Rationale**: For Podman/Docker storage. Mixed workloads benefit from 128K.

### tank/logs
- **Mountpoint**: `/tank/logs`
- **recordsize**: 128K (log files)
- **compression**: zstd (excellent for text)
- **refquota**: 50G (prevent log explosion)
- **Rationale**: For centralized logging (journald, etc.). zstd provides excellent compression for text logs.

## Migration Steps

### 1. Reboot poweredge (ZFS kernel modules need to load)
```bash
ssh likivik@poweredge 'sudo reboot'
```

### 2. Verify ZFS pool imports
```bash
ssh likivik@poweredge 'sudo zpool list && sudo zfs list'
```

### 3. Destroy old tank/data (no useful data exists)
```bash
ssh likivik@poweredge 'sudo zfs destroy tank/data'
```

### 4. Create new datasets
```bash
ssh likivik@poweredge 'sudo zfs create -o recordsize=128K -o compression=lz4 -o atime=off -o xattr=sa -o acltype=posixacl tank/nextcloud'
ssh likivik@poweredge 'sudo zfs create -o recordsize=1M -o compression=lz4 -o atime=off -o xattr=sa -o acltype=posixacl tank/immich'
ssh likivik@poweredge 'sudo zfs create -o recordsize=1M -o compression=zstd -o atime=off -o xattr=sa -o acltype=posixacl tank/backups'
ssh likivik@poweredge 'sudo zfs create -o recordsize=1M -o compression=lz4 -o atime=off -o xattr=sa -o acltype=posixacl tank/media'
ssh likivik@poweredge 'sudo zfs create -o recordsize=1M -o compression=lz4 -o atime=off -o xattr=sa -o acltype=posixacl -o refquota=500G tank/downloads'
ssh likivik@poweredge 'sudo zfs create -o recordsize=128K -o compression=lz4 -o atime=off -o xattr=sa -o acltype=posixacl tank/containers'
ssh likivik@poweredge 'sudo zfs create -o recordsize=128K -o compression=zstd -o atime=off -o xattr=sa -o acltype=posixacl -o refquota=50G tank/logs'
```

### 5. Update service configs
- `modules/aspects/server/nextcloud/default.nix`: change `datadir = "/tank/nextcloud"`
- `modules/aspects/server/immich/default.nix`: change `mediaLocation = "/tank/immich"`

### 6. Update disko config
Replace single `data` dataset in `modules/hosts/poweredge/_disko.nix` with the 7 datasets above.

### 7. Rebuild and deploy
```bash
nix build .#nixosConfigurations.poweredge.config.system.build.toplevel
nix copy --to ssh://likivik@poweredge .#nixosConfigurations.poweredge.config.system.build.toplevel
ssh likivik@poweredge 'sudo /nix/store/<new-path>/bin/switch-to-configuration switch'
```

## Benefits
1. **Performance**: Each dataset optimized for its workload (recordsize, compression)
2. **Isolation**: Independent snapshots, quotas, and replication per service
3. **Flexibility**: Can replicate critical data (nextcloud) without bulk media (immich)
4. **Safety**: Quotas prevent runaway processes from filling the pool
5. **Future-proof**: Prepared for additional services (media server, download clients, etc.)

## Related ZFS Improvements (from flagship-consultant review)
- P0: Remove `services.zfs.autoScrub.enable` from nextcloud aspect (line 86)
- P0: Add `services.zfs.autoSnapshot.enable = true` on poweredge
- P0: Add `services.zfs.zed.enable` + email on poweredge
- P0: Add `services.smartd.enable` on poweredge
- P1: Add syncoid replication to erebus nightly
- P1: Uncomment ZFS kernel pinning on serenity + poweredge
- P2: Encrypt tank/nextcloud (sops-stored key)
- P2: Add ARC cap (`zfs_arc_max`) on poweredge
