{ inputs, den, ... }:
{
  den.aspects.core.tailscale = {
    nixos = { config, pkgs, lib, ... }: {
      services.tailscale.enable = true;
      services.tailscale.useRoutingFeatures = "both";
      services.tailscale.extraUpFlags = [
        "--operator=likivik"
        "--accept-routes=true"
      ];

      # Tailscale control channel: force the "noise" dialer onto port 443.
      #
      # Tailscale's control client prefers plaintext HTTP on port 80 for the
      # control-plane upgrade (the Noise handshake rides along in the HTTP
      # upgrade request, saving a round trip) and only falls back to HTTPS:443
      # when port 80 fails *fast*. On this network's ISP path, port 80 is
      # interfered with after that upgrade: registration succeeds, then the
      # /machine/map long-poll is killed every 2 minutes, forever, so the node
      # never holds a netmap. Symptom: the tailnet shows the host offline and
      # every peer sees rx 0, while the host itself has working internet. DNS
      # dies with it — MagicDNS forwards through the tailnet, so every external
      # lookup fails and consumers like cloudflared never resolve their SRV
      # records (their tunnels then never come up).
      #
      #   control: map response long-poll timed out!            (every ~2m)
      #   control: lite map update error after 2m0.001s: Post
      #     "https://controlplane.tailscale.com/machine/map": context canceled
      #   health(warnable=not-in-map-poll): error: Unable to connect to the
      #     Tailscale coordination server ...
      #
      # Verified 2026-09-12 on serenity, and again 2026-10-16 on poweredge —
      # the latter booted with "loaded netmap from disk cache; 0 peers", logged
      # 230 long-poll timeouts across 9.5h and accepted no inbound connection
      # the whole night; the following boot, with no config change, logged zero:
      #   http://controlplane.tailscale.com/health   -> times out
      #   https://controlplane.tailscale.com/health  -> immediate response
      #
      # Upstream knob: TS_FORCE_NOISE_443 in control/controlhttp/client.go —
      # "necessary when networks or middle boxes are messing with port 80",
      # cf. tailscale#13597 and hassio-addons#688.
      systemd.services.tailscaled.serviceConfig.Environment = lib.mkAfter [
        "TS_FORCE_NOISE_443=true"
      ];

      # Netmap guard — runs on every host.
      #
      # When the long-poll above is killed, tailscaled keeps reporting Running
      # while holding an empty netmap. The host is up and healthy at the console
      # but invisible to the tailnet: peers see rx 0, and `open-conn-track:
      # timeout opening ... no associated peer node` repeats for every outbound
      # connection. On a host that exits through a tailnode (RouteAll) the blast
      # radius is total — no peer list means no exit node, so all internet and
      # DNS die with it and any tunnel never comes up. Observed 2026-10-16 on
      # poweredge: 9.5h dark, ended only by a manual power cycle.
      #
      # A tailscaled restart clears it (the state is in memory, not on disk), so
      # recover automatically instead of waiting for someone to notice.
      #
      # Deliberately conservative: two consecutive bad checks before acting, and
      # at most one restart per 30 minutes, so a persistent network condition
      # cannot become a restart loop. A node that is genuinely offline
      # (Self.Online = false) is left alone — that is a real network outage, not
      # a lost netmap, and restarting tailscaled would not help.
      #
      # Caveat: the zero-peer trigger assumes this node expects peers. A
      # single-node tailnet would flap (restart every 30 min) — set
      # `systemd.timers.tailscale-netmap-guard.enable = false` on such a host.
      systemd.services.tailscale-netmap-guard = {
        description = "Restart tailscaled if it is Running but has lost its netmap";
        serviceConfig = {
          Type = "oneshot";
          # The guard reports through the journal; a non-zero exit would only add
          # noise to `systemctl --failed`.
          SuccessExitStatus = "0 1";
        };
        path = [ pkgs.jq pkgs.coreutils pkgs.gnugrep pkgs.systemd ];
        script = ''
          set -uo pipefail
          FAILS=/run/tailscale-netmap-guard.fails
          STAMP=/run/tailscale-netmap-guard.last

          json=$(timeout 20 tailscale status --json 2>/dev/null) || {
            echo "guard: 'tailscale status' failed or timed out; leaving it alone"
            exit 0
          }

          state=$(printf '%s' "$json" | jq -r '.BackendState // "unknown"')
          health=$(printf '%s' "$json" | jq -r '(.Health // []) | join(",")')
          online=$(printf '%s' "$json" | jq -r '.Self.Online // false')
          peers=$(printf '%s' "$json" | jq -r '(.Peer // {}) | length')

          # Only judge a node that claims to be up and online. A deliberately
          # stopped node, or one that is offline because the network is down, is
          # not our business.
          bad=""
          if [ "$state" = "Running" ] && [ "$online" = "true" ]; then
            case "$health" in
              *not-in-map-poll*) bad="not-in-map-poll" ;;
            esac
            if [ "$peers" -eq 0 ]; then
              bad="''${bad:+$bad,}zero-peers"
            fi
          fi

          if [ -z "$bad" ]; then
            echo 0 > "$FAILS"
            exit 0
          fi

          n=$(( $(cat "$FAILS" 2>/dev/null || echo 0) + 1 ))
          echo "$n" > "$FAILS"
          echo "guard: netmap unhealthy ($bad; state=$state online=$online peers=$peers) consecutive=$n"

          [ "$n" -ge 2 ] || exit 0

          now=$(date +%s)
          last=$(cat "$STAMP" 2>/dev/null || echo 0)
          if [ $(( now - last )) -lt 1800 ]; then
            echo "guard: within 30min cooldown of the last restart; not restarting"
            exit 0
          fi

          echo "$now" > "$STAMP"
          echo 0 > "$FAILS"
          echo "guard: restarting tailscaled to recover the netmap"
          systemctl restart tailscaled.service
        '';
      };

      systemd.timers.tailscale-netmap-guard = {
        description = "Check tailscale netmap health every 5 minutes";
        wantedBy = [ "timers.target" ];
        timerConfig = {
          OnBootSec = "5min";
          OnUnitActiveSec = "5min";
          Unit = "tailscale-netmap-guard.service";
        };
      };
    };
  };
}
