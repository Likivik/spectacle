let
  flake = builtins.getFlake (toString ../.);
  den = flake.nixosConfigurations.spectacle.config.den;
  inherit (den.lib.aspects) resolve adapters;
  aspect = den.hosts.x86_64-linux.resolved;
in
{
  traceResult = resolve.withAdapter adapters.trace "nixos" aspect;
}
