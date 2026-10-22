# Where git repositories live on a given host.
#
# Called from `maid` blocks with den's parametric `host` context:
#   maid = { user, host, ... }: let gitRoot = import ../../../lib/git-root.nix host; in ...
#
# Why here and not an option: nix-maid's NixOS integration only injects
# `pkgs` and `systemdUtils` into maid modules (src/nixos/default.nix), so
# `config`/`osConfig` are not available there — but den DOES inject the
# parametric entity context (`host`, `user`, ...). A plain function of `host`
# is therefore the only mechanism that reaches both the dotfile `source`
# strings and the host's own filesystem layout.
#
# Default is /Storage/Git so hosts that have not migrated keep working; a host
# opts into a different root by adding itself to the table below.
host:
let
  name = host.hostName or host.name or "";
in
{
  # serenity mounts the git pool at /Git (short path, no bind mounts).
  serenity = "/Git";
}.${name} or "/Storage/Git"
