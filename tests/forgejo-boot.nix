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
#   - Self-contained CI deps (the aspect carries its own builder requirements):
#     podman is enabled, the forgejo-runner-nix image oneshot imports the runner
#     image, nixuser exists, gitea-runner is in the podman group, and the runner
#     unit is generated ordered after the image import (so jobs can never run
#     before the image is present).
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

    # 3b. Persistent Rust cargo cache dirs created + owned by the job user
    machine.succeed("test -d /Storage/forgejo/rust-cache")
    machine.succeed("test -d /Storage/forgejo/rust-target")
    machine.succeed("[ \"$(stat -c %U /Storage/forgejo/rust-cache)\" = nixuser ]")
    machine.succeed("[ \"$(stat -c %U /Storage/forgejo/rust-target)\" = nixuser ]")

    # 3c. Runner config.yaml declares the cargo env + writable volumes
    # (container options compile into the generated config.yaml, referenced by
    # the daemon's ExecStart --config <storePath>.)
    machine.succeed(
      "cfg=$(systemctl cat gitea-runner-serenity.service "
      + "| grep -o '/nix/store/[^ ]*config.yaml' | head -1); "
      + "grep -q 'CARGO_HOME=/opt/cargo' \"$cfg\" && "
      + "grep -q 'CARGO_TARGET_DIR=/opt/target' \"$cfg\" && "
      + "grep -q '/Storage/forgejo/rust-cache:/opt/cargo' \"$cfg\" && "
      + "grep -q '/Storage/forgejo/rust-target:/opt/target' \"$cfg\""
    )

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

    # ── Self-contained builder requirements (own CI deps in the aspect) ──────

    # 7. Podman is enabled by the aspect (the job runtime). Daemonless: the
    #    runner drives the root socket (DOCKER_HOST=unix:///run/podman/podman.sock),
    #    so assert the socket unit, not a long-running podman.service.
    machine.wait_for_unit("podman.socket")

    # 8. The runner image oneshot runs and imports the minimal image
    machine.wait_for_unit("forgejo-runner-nix-image.service")
    machine.succeed("${pkgs.podman}/bin/podman image exists forgejo-runner-nix")

    # 9. An unprivileged nixuser is defined (the container --user target)
    machine.succeed("id nixuser")

    # 10. The runner user can drive the root podman socket (group scoping)
    machine.succeed("id gitea-runner | grep -q '\\bpodman\\b'")

    # 11. The runner unit is declared (config valid) ...
    machine.succeed("systemctl cat gitea-runner-serenity.service >/dev/null")

    # 12. ... and ordered after the image import, so it never runs jobs first
    machine.succeed(
      "systemctl show gitea-runner-serenity -p After | grep -q forgejo-runner-nix-image"
    )
  '';
}
