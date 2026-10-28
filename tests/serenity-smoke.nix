# Full-host boot smoke test for serenity.
#
# Extends the ENTIRE `nixosConfigurations.serenity` (via extendModules) into a
# QEMU VM and boots it. The point is breadth: this host carries the agent, the
# dev/build/CI load, forgejo and the local AI services, so "the toplevel
# evaluates" says nothing about whether the system actually comes up.
#
# Only things PHYSICALLY IMPOSSIBLE in a guest are neutralised. Everything else
# is left exactly as deployed, and the gate is:
#
#   * no FAILED system unit outside an explicit allowlist
#   * every `systemd.user.services` entry the config declares exists for hermes
#   * the declarative linger file is present
#   * `systemd-run --user --scope` SUCCEEDS as hermes — the primitive the
#     restart-safe cron worker needs. This is the assertion that would have
#     caught upstream #111484 (cron dispatch failing on every tick), which is
#     why it is here even though it looks like a systemd detail.
#   * the secrets pipeline actually DELIVERS: the sops template renders with
#     real values, every key in it is non-empty, and the gateway process holds
#     a non-empty TELEGRAM_BOT_TOKEN. No unit env file anywhere contains a
#     present-but-empty assignment (the 2026-10-14 incident's exact signature).
#
# Neutralised, with the fidelity actually lost:
#   - TPM-bound sops: no TPM in QEMU. The host's TPM identity is swapped for a
#     throwaway age identity generated at BUILD time and never committed, and every
#     secret is pointed at a dummy encrypted file generated at BUILD TIME from the
#     host's own sops.secrets declarations. Secret VALUES are dummy, but the rendering
#     path is the real one — that is the difference between testing delivery
#     and stubbing the file (a stub is non-empty by construction, so asserting
#     on it proves nothing).
#   - Networking: the host's static networkd config leaves eth0 routeless under
#     QEMU SLIRP, so DHCP with useNetworkd=false (same as tests/erebus-telegram.nix).
#   - Tailscale: no tailnet, and it holds network-online.target hostage.
#
# Run:  nix run .#serenity-smoke
# The probe is tests/serenity-smoke-probe.sh; it runs as an in-guest oneshot,
# reports on the serial console and ends with SERENITY_SMOKE_PASS/FAIL, which
# `nix run .#serenity-smoke` greps to decide its exit code.
{ config, pkgs, lib, base, ... }:
let
  # --- a real (but worthless) sops round-trip ------------------------------
  # `base` is the UN-extended serenity config, so reading its sops.secrets here
  # is not self-referential.
  dummyValue = "vm-smoke-dummy-secret-value";

  # "a/b/c" -> { a = { b = { c = v; }; }; }
  nest = paths: v: lib.foldr (p: acc: { ${p} = acc; }) v paths;

  # Every secret the host declares, so a new secret is covered automatically.
  dummyPlain = lib.foldl'
    (acc: n: lib.recursiveUpdate acc (nest (lib.splitString "/" n) dummyValue))
    { }
    (lib.attrNames base.config.sops.secrets);

  # The age identity is generated HERE, at build time, and never committed.
  #
  # It used to be a checked-in private key (tests/smoke-age-key.txt). That key
  # protected nothing real — every value below is the literal dummy — but a real
  # private key in a PUBLIC repository is a bad pattern to keep around: it
  # normalises private keys in the tree, it leaks permanently through git history
  # and forks, and a keypair reused for anything real would decrypt every secret
  # encrypted to that recipient. Generating it per build removes the artefact.
  #
  # $out/identity.txt is a store path, so it is world-readable on the machine
  # running the smoke. That is bounded and acceptable: the identity is fresh per
  # build and decrypts only dummy values. sops-nix's own guard — sops.age.keyFile
  # must not be a store path — still holds, because the path DECLARED to sops is
  # /run/smoke-age-key.txt; this derivation's output is installed there at boot by
  # the smoke-age-key unit below.
  smokeSecrets = pkgs.runCommand "serenity-smoke-secrets" {
    nativeBuildInputs = [ pkgs.sops pkgs.age ];
    # sops wants a HOME for its age plugin/config cache.
    HOME = "$TMPDIR";
  } ''
    mkdir -p $out
    age-keygen -o identity.txt 2> keygen.err
    RECIPIENT=$(grep -oE 'age1[0-9a-z]+' keygen.err | head -1)
    # Fail loudly rather than encrypting to an empty recipient.
    test -n "$RECIPIENT"

    cat > plain.yaml <<'YAML'
${lib.generators.toYAML { } dummyPlain}
YAML
    sops --encrypt --age "$RECIPIENT" \
      --input-type yaml --output-type yaml plain.yaml > $out/secrets.yaml

    install -m 0400 identity.txt $out/identity.txt
  '';

  dummySopsFile = "${smokeSecrets}/secrets.yaml";

  # Every EnvironmentFile path any system or user unit in THIS host references.
  # Generated rather than hand-listed on purpose: a hand-list rots silently the
  # moment an aspect adds a secret, and the test would then quietly stop
  # covering that unit.
  envFilesOf = units:
    lib.concatMap
      (u:
        map (f: if builtins.isString f then f else (f.path or ""))
          (lib.toList (u.serviceConfig.EnvironmentFile or [ ])))
      (lib.attrValues units);

  # `/run/secrets/rendered/<name>` is where sops-nix puts a rendered template,
  # so it is discovered like any other secret-backed env file.
  allEnvFiles = lib.unique (lib.filter
    (p: p != "" && lib.hasPrefix "/run/secrets/" p)
    (envFilesOf config.systemd.services ++ envFilesOf config.systemd.user.services));

  # The rendered env file the gateway/webui/dashboard load. Path comes from the
  # template itself, not a literal, so renaming the template cannot silently
  # stop this gate from covering it.
  renderedEnv = config.sops.templates."hermes/sops-env".path;

  # Every KEY the template defines — literal settings and sops-backed ones
  # alike — derived from the evaluated content. A key that renders empty is a
  # regression whether or not its value came from a secret.
  templateKeys = lib.filter (k: k != "")
    (map (l: lib.head (lib.splitString "=" l))
      (lib.splitString "\n" config.sops.templates."hermes/sops-env".content));

  allEnvFilesFile = pkgs.writeText "serenity-smoke-env-files"
    (lib.concatStringsSep "\n" allEnvFiles + "\n");
  expectedKeysFile = pkgs.writeText "serenity-smoke-expected-keys"
    (lib.concatStringsSep "\n" templateKeys + "\n");

  # The probe checks, as a store path. Kept in its own file so editing it is a
  # change in one obvious place rather than inside a Nix string.
  probe = pkgs.writeShellScript "serenity-smoke-probe"
    (builtins.readFile ./serenity-smoke-probe.sh);
in
{
  # --- guest networking ---
  systemd.network.enable = lib.mkForce false;
  networking.useNetworkd = lib.mkForce false;
  networking.useDHCP = lib.mkForce true;
  networking.nameservers = lib.mkForce [ "1.1.1.1" "8.8.8.8" ];

  # --- no TPM: swap the identity and re-point every secret at dummy values ---
  # NOT `sops.secrets = mkForce {}`: that would leave sops.placeholder empty
  # (an eval error, since the templates reference it) and, worse, would mean
  # nothing is rendered — so any assertion about the rendered file would be
  # vacuous.
  #
  # The identity cannot be a store path: sops.age.keyFile is type-checked to
  # REJECT store paths (sops-nix modules/sops/default.nix:23), because a private
  # key in the world-readable store would be a leak. So it is installed to /run
  # at boot.
  #
  # It also cannot come from tmpfiles: tmpfiles-setup is not ordered against
  # sops-install-secrets, so the key could be placed too late. It is placed by a
  # unit of our own ordered Before=sops-install-secrets.service instead.
  # Before the host switched to systemd activation this had to be an activation
  # script appended to setupSecrets' deps — nothing else ran early enough to
  # order against. That hack disappearing is the payoff of the switch.
  sops = {
    age.keyFile = lib.mkForce "/run/smoke-age-key.txt";
    age.plugins = lib.mkForce [ ];
    # Force only `sopsFile`, per secret. Replacing the whole attrset would
    # clobber sops-nix's computed `sopsFileHash` (read-only) and collide with
    # the copy build-vm.nix carries into virtualisation.vmVariant.
    secrets = lib.mapAttrs
      (n: _: { sopsFile = lib.mkForce dummySopsFile; })
      base.config.sops.secrets;
    # The dummy file is produced by a build-time derivation, so sops-nix's
    # pre-flight validation (which wants to inspect a real, already-present
    # sops file) rejects it. The guest does not need that check — the whole
    # point of the gate is that the file IS decrypted and rendered at boot, and
    # the probe asserts on the result.
    validateSopsFiles = lib.mkForce false;
  };

  # Placed by a unit ordered before sops-install-secrets.service. `before` alone
  # is not enough — a unit that is only `before` something can be skipped
  # entirely if nothing pulls it in, so it is also wantedBy sysinit.target and
  # requiredBy the consumer.
  systemd.services."smoke-age-key" = {
    wantedBy = [ "sysinit.target" ];
    requiredBy = [ "sops-install-secrets.service" ];
    before = [ "sops-install-secrets.service" ];
    # REQUIRED, not cosmetic. With the default (yes) this unit inherits
    # After=basic.target, and basic.target is reached THROUGH sysinit.target,
    # while sops-install-secrets must run BEFORE sysinit.target. That is an
    # ordering cycle, and systemd breaks it by DELETING the sops job — so no
    # secrets are installed and the only symptom is a unit that never ran.
    # sops-nix sets the same flag on its own unit for exactly this reason.
    unitConfig.DefaultDependencies = "no";
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    # Absolute path: a unit gets systemd's minimal PATH, where coreutils is NOT
    # present on NixOS. `install` would fail, and because
    # sops-install-secrets.service Requires this unit, that leaves the consumer
    # INACTIVE (not failed) — so no secrets are installed at all and the failure
    # looks nothing like a PATH problem.
    script = ''
      ${pkgs.coreutils}/bin/install -m 0400 -o root -g root ${smokeSecrets}/identity.txt /run/smoke-age-key.txt
    '';
  };

  # --- tailscale needs a tailnet + auth key ---
  services.tailscale.enable = lib.mkForce false;

  # The store optimiser hard-links store paths, which CANNOT work on the guest's
  # virtiofs mount: it dies with "renaming ...: Stale file handle" and lands in a
  # failed state. It is timer-triggered and takes ~3 minutes, so whether it fires
  # inside the smoke's boot window is pure timing — which is why this surfaced as
  # an intermittent UNEXPECTED_FAILED_UNITS. Disabling it in the guest removes the
  # noise at the source instead of widening the allowlist, which would have
  # started hiding real failures alongside it.
  nix.optimise.automatic = lib.mkForce false;

  users.users.root.initialPassword = "test";

  # Guest RAM comes from den.default.nixos.virtualisation.vmVariant in
  # modules/defaults/defaults.nix (8 GiB / 4 cores). At qemu-vm's 1024 MiB
  # default the kernel OOM-killed hermes, python3.13 and the compositor
  # mid-boot, which would make this test report noise instead of regressions.

  # The guest's ttyS0 belongs to the probe. agetty was resetting the tty
  # underneath it, so its output silently vanished after a few lines while the
  # script kept running - a hung probe looked identical to one that had not
  # started. ExecStart below redirects the probe's output there, so disabling
  # the getty is load-bearing, not cosmetic.
  systemd.services."serial-getty@ttyS0".enable = false;

  # The probe runs as an in-guest oneshot, reports to the serial console and
  # powers the VM off - which is what makes `nix run .#serenity-smoke` terminate
  # on its own. The checks live in tests/serenity-smoke-probe.sh.
  #
  # The expected user-unit set is NOT passed in: the probe reads the INSTALLED
  # set from /etc/systemd/user, so an aspect that adds a unit is covered
  # automatically and an unquoted list cannot silently shrink the assertion.
  systemd.services.vmcheck-serenity = {
    description = "serenity full-host boot smoke test (see tests/serenity-smoke-probe.sh)";
    wantedBy = [ "multi-user.target" ];
    wants = [ "network-online.target" ];
    after = [ "network-online.target" "systemd-user-sessions.service" ];
    # gawk and sudo MUST be here: without sudo every `systemctl --user` check
    # reports failure, which looks like a genuine host defect.
    path = with pkgs; [ systemd coreutils gnugrep gnused gawk iproute2 getent sudo ];
    serviceConfig = {
      Type = "oneshot";
      Environment = [
        # Secret-pipeline assertions. SMOKE_ENV_FILES and SMOKE_EXPECTED_KEYS are
        # FILE paths: NixOS renders serviceConfig.Environment entries unquoted
        # and systemd word-splits such a value, so a space-joined list silently
        # arrives as its first element only.
        "SMOKE_ENV_FILES=${allEnvFilesFile}"
        "SMOKE_EXPECTED_KEYS=${expectedKeysFile}"
        "SMOKE_RENDERED_ENV=${renderedEnv}"
        "SMOKE_DUMMY_VALUE=${dummyValue}"
      ];
      ExecStart = pkgs.writeShellScript "serenity-smoke-run" ''
        exec > /dev/ttyS0 2>&1
        exec ${probe}
      '';
    };
  };
}
