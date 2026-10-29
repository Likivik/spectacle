{ lib, ... }:
# Services declare the ports they need; hosts declare their wires and grant a
# service onto them. Nothing is ever opened globally: `allowedTCPPorts` is
# forced empty so a module's own `openFirewall = true` cannot reintroduce a
# wildcard accept rule. See docs/firewall-interface-options-2026.md.
{
  den.aspects.core.firewall = {
    nixos =
      { config, lib, ... }:
      let
        cfg = config.networkFirewall;
        services = lib.attrNames cfg.services;
        portsOf = svc: cfg.services.${svc}.ports or [ ];
        udpOf = svc: cfg.services.${svc}.udp or [ ];
        grantsOf = svc: cfg.grants.${svc} or [ ];
        wires = lib.unique (lib.concatMap grantsOf (lib.attrNames cfg.grants));
        on = wire: svc: lib.elem wire (grantsOf svc);

        # "tcp/22" -> services claiming it, for the collision assertion.
        # UDP is included: a udp/tcp pair on one number is not a collision, but
        # two services on the same protocol+port with different grants is.
        claims = lib.concatMap (
          svc:
          map (p: { inherit svc; key = "tcp/${toString p}"; }) (portsOf svc)
          ++ map (p: { inherit svc; key = "udp/${toString p}"; }) (udpOf svc)
        ) services;
        owners = lib.foldl' (a: c: a // { ${c.key} = (a.${c.key} or [ ]) ++ [ c.svc ]; }) { } claims;
        collisions = lib.filterAttrs (_: svcs: lib.length (lib.unique svcs) > 1) owners;
      in
      {
        options.networkFirewall = {
          enable = lib.mkEnableOption "grant-based per-interface firewall";
          services = lib.mkOption {
            type = lib.types.attrsOf (
              lib.types.submodule {
                options = {
                  ports = lib.mkOption {
                    type = lib.types.listOf lib.types.port;
                    default = [ ];
                    description = "TCP ports this service needs.";
                  };
                  udp = lib.mkOption {
                    type = lib.types.listOf lib.types.port;
                    default = [ ];
                    description = "UDP ports this service needs.";
                  };
                };
              }
            );
            default = { };
            description = "Ports declared by services. Nothing is opened until a host grants it.";
          };
          ifaces = lib.mkOption {
            type = lib.types.attrsOf lib.types.str;
            default = { };
            description = "Wire name -> network device on this host.";
          };
          grants = lib.mkOption {
            type = lib.types.attrsOf (lib.types.listOf lib.types.str);
            default = { };
            description = "Service name -> wires it may be reached on. Empty means closed.";
          };
        };

        config = lib.mkIf cfg.enable {
          # Backstop: outranks every module's `openFirewall = true` (priority 1000 vs 100).
          networking.firewall.allowedTCPPorts = lib.mkForce [ ];
          networking.firewall.allowedUDPPorts = lib.mkForce [ ];

          # Caveat for hosts mid-migration: a wire whose device is also pinned by a
          # host-level `interfaces.<dev>.allowedTCPPorts = lib.mkForce [...]` loses the
          # granted ports silently (mkForce priority beats this assignment). Keep the
          # granted port inside that host list until the line is moved into grants.
          # A wire is a name; the rule needs the device it resolves to.
          networking.firewall.interfaces = lib.listToAttrs (
            map (wire: {
              name = cfg.ifaces.${wire};
              # mkForce: on a wire this model governs, it is the only writer. A module
              # that opens a port on that device itself (nextcloud/n8n do exactly this
              # for tailscale0 80/443) would otherwise merge in silently. It declares
              # `networkFirewall.services.<name>` instead.
              value = {
                allowedTCPPorts = lib.mkForce (lib.unique (
                  lib.concatMap (svc: if on wire svc then portsOf svc else [ ]) services
                ));
                allowedUDPPorts = lib.mkForce (lib.unique (
                  lib.concatMap (svc: if on wire svc then udpOf svc else [ ]) services
                ));
              };
            }) wires
          );

          assertions = [
            {
              assertion = lib.all (svcs: lib.length (lib.unique (map grantsOf svcs)) == 1) (
                lib.attrValues collisions
              );
              message = "two services claim the same port with different grants: "
                + lib.concatStringsSep ", "
                  (lib.mapAttrsToList (k: svcs: "${k}: ${lib.concatStringsSep "/" (lib.unique svcs)}") collisions);
            }
            {
              assertion = lib.all (w: cfg.ifaces ? ${w}) (lib.concatLists (lib.attrValues cfg.grants));
              message = "networkFirewall.grants names a wire this host does not declare in networkFirewall.ifaces";
            }
            {
              assertion = lib.all (svc: cfg.services ? ${svc}) (lib.attrNames cfg.grants);
              message = "networkFirewall.grants names a service that declares no ports";
            }
            {
              assertion = lib.length (lib.unique (lib.attrValues cfg.ifaces)) == lib.length (lib.attrValues cfg.ifaces);
              message = "networkFirewall.ifaces maps two wire names to one device: "
                + lib.concatStringsSep ", "
                  (lib.mapAttrsToList (w: d: "${w}=${d}") cfg.ifaces);
            }
          ];
        };
      };
  };
}
