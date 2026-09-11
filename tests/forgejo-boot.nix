# Forgejo aspect boot test.
#
# Boots a fresh VM running the actual `den.aspects.server.forgejo` module and
# asserts the deployable contract — the exact failures we hit on first deploy
# are encoded as assertions:
#   - forgejo.service reaches active (was: start-limit-hit)
#   - /Storage/forgejo/{repositories,lfs} exist owned by forgejo
#     (was: ReadWritePaths NAMESPACE fail -> No such file or directory)
#   - forgejo can traverse /Storage (was: `mkdir /Storage/forgejo: permission
#     denied` because the ZFS pool dir is 0770 likivik:users and forgejo wasn't
#     in `users`)
#   - ReadWritePaths includes the parent /Storage/forgejo (protect-system
#     sandbox), so MkdirAll doesn't EPERM on the parent
#   - HTTP answers on 127.0.0.1:3000
#   - /var/backup/forgejo backup dir is created
{ inputs, pkgs, ... }:
let
  aspect = import ../modules/aspects/server/forgejo/forgejo.nix {
    inherit inputs;
    den = { };
  };
in
pkgs.testers.nixosTest {
  name = "forgejo-boot";

  nodes.machine = { lib, ... }: {
    imports = [ aspect.den.aspects.server.forgejo.nixos ];

    # The aspect keys off the den user/group defaults (forgejo:forgejo), which
    # the module creates. Keep the test hermetic: no tailnet, no secrets.
    system.stateVersion = "25.11";
  };

  testScript = ''
    start_all()

    # 1. Service must come up (guards the namespace + group + sandbox regressions)
    machine.wait_for_unit("forgejo.service")

    # 2. Data dirs created by the activation script, owned by forgejo
    machine.succeed("test -d /Storage/forgejo/repositories")
    machine.succeed("test -d /Storage/forgejo/lfs")
    machine.succeed("test -d /var/backup/forgejo")
    machine.succeed("[ \"$(stat -c %U /Storage/forgejo/repositories)\" = forgejo ]")

    # 3. forgejo must be able to traverse its parent (group membership)
    machine.succeed("id forgejo | grep -q '\\busers\\b'")

    # 4. The protected-sandbox unit must expose the parent dir as writable
    machine.succeed(
      "systemctl show forgejo -p ReadWritePaths | grep -q /Storage/forgejo"
    )

    # 5. Actually serves
    machine.wait_until_succeeds("curl -sf -o /dev/null http://127.0.0.1:3000/")

    # 6. Loopback-only binding (not exposed to the network)
    machine.succeed(
      "ss -tlnp | grep ':3000' | grep -q '127.0.0.1' && ! ss -tlnp | grep ':3000' | grep -q '0.0.0.0:3000'"
    )
  '';
}
