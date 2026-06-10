{ inputs, den, ... }:
{
  # ncro - Nix Cache Route Optimizer
  # Proxies narinfo requests to the fastest upstream using EMA latency tracking.
  # Routes cached in SQLite; NARs streamed with zero disk storage.
  # https://github.com/feel-co/ncro
  den.aspects.core.ncro = {
    nixos = { pkgs, lib, ... }: {
      imports = [ inputs.ncro.nixosModules.ncro ];
      services.ncro = {
        enable = true;
        package = inputs.ncro.packages.${pkgs.system}.ncro;
        settings = {
          # Listen port - use non-standard to avoid conflicts
          server.listen = ":5496";
          server.read_timeout = "10s";
          server.write_timeout = "10s";

          # Sequential: try one upstream at a time by priority, don't race all
          cache.mass_query.max_concurrent_races = 1;
          # Faster recovery after failure
          cache.mass_query.upstream_cooldown = "5s";
          # Brief in-memory negative cache to avoid repeat failures
          cache.mass_query.in_memory_negative_ttl = "2s";

          upstreams = [
            # Primary upstream - lowest priority wins on latency ties
            {
              url = "https://cache.nixos.org";
              priority = 10;
              public_key = "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY=";
            }
            # Chinese mirrors - mirror same content as cache.nixos.org
            # No public_key needed - same signatures as upstream
            {
              url = "https://mirror.sjtu.edu.cn/nix-channels/store";
              priority = 21;
            }
            {
              url = "https://mirrors.ustc.edu.cn/nix-channels/store";
              priority = 22;
            }
            {
              url = "https://mirrors.tuna.tsinghua.edu.cn/nix-channels/store";
              priority = 23;
            }
            # Cachix caches - project-specific binary caches
            {
              url = "https://noctalia.cachix.org";
              priority = 30;
              public_key = "noctalia.cachix.org-1:pCOR47nnMEo5thcxNDtzWpOxNFQsBRglJzxWPp3dkU4=";
            }
            {
              url = "https://hyprland.cachix.org";
              priority = 40;
              public_key = "hyprland.cachix.org-1:a7pgxzMz7+chwVL3/pzj6jIBMioiJM7ypFP8PwtkuGc=";
            }
          ];
        };
      };
      # ncro must be the ONLY substituter for optimal routing
      nix.settings.substituters = lib.mkForce [ "http://localhost:5496" ];
    };
  };
}
