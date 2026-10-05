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
#
# Neutralised, with the fidelity actually lost:
#   - TPM-bound sops: no TPM in QEMU. `sops.secrets` is emptied so activation
#     does not abort, and every EnvironmentFile path the config references is
#     re-created with dummy contents, so units still start and can be judged.
#     Secret VALUES are therefore not tested — only that units come up without
#     them crashing.
#   - Networking: the host's static networkd config leaves eth0 routeless under
#     QEMU SLIRP, so DHCP with useNetworkd=false (same as tests/erebus-telegram.nix).
#   - Tailscale: no tailnet, and it holds network-online.target hostage.
#
# Run:  nix run .#serenity-smoke
# The probe is tests/serenity-smoke-probe.sh; it is piped into the guest over
# the forwarded port and its report ends with SERENITY_SMOKE_PASS/FAIL.
{ config, pkgs, lib, ... }:
let
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

  envPaths = lib.unique (lib.filter
    (p: p != "" && lib.hasPrefix "/run/secrets/" p)
    (envFilesOf config.systemd.services ++ envFilesOf config.systemd.user.services));

  # The gateway's second EnvironmentFile is written by an activation script from
  # the (now empty) secret set, so it must be re-created too.
  extraEnvPaths = [ "/var/lib/hermes/.hermes/sops-env" ];

  # User units the deployed config expects to exist for `hermes`. Generated, so
  # a new aspect unit is covered automatically.
  expectedUserUnits = lib.attrNames config.systemd.user.services;

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

  # --- no TPM: empty the secret set, then stub every referenced env file ---
  sops.secrets = lib.mkForce { };
  systemd.tmpfiles.rules = map
    (p: "f ${p} 0600 hermes hermes - DUMMY=vm-smoke-not-a-credential")
    (envPaths ++ extraEnvPaths);

  # --- tailscale needs a tailnet + auth key ---
  services.tailscale.enable = lib.mkForce false;

  users.users.root.initialPassword = "test";

  # Guest RAM comes from den.default.nixos.virtualisation.vmVariant in
  # modules/defaults/defaults.nix (8 GiB / 4 cores). At qemu-vm's 1024 MiB
  # default the kernel OOM-killed hermes, python3.13 and the compositor
  # mid-boot, which would make this test report noise instead of regressions.

  # The probe is driven from the HOST, not from an in-guest oneshot:
  # a CONNECT on the forwarded port runs `bash -s` as root, the host pipes the
  # probe in and reads the report back. Two reasons:
  #   1. an in-guest probe's output dies on the serial console the moment agetty
  #      takes ttyS0, so its failures were unobservable;
  #   2. probe edits then cost seconds instead of a full VM rebuild.
  # Port 9999 is deliberate - the guest's own sshd owns 22.
  # The guest ttyS0 is ours: agetty was resetting the tty underneath the probe,
  # so its output silently vanished after a few lines while the script kept
  # running (and a probe that hung looked identical to one that had not started).
  systemd.services."serial-getty@ttyS0".enable = false;

  # The probe runs as an in-guest oneshot and reports to the serial console, then
  # powers the VM off - which is what makes `nix run .#serenity-smoke` terminate
  # on its own. The checks live in tests/serenity-smoke-probe.sh; EXPECTED_UNITS
  # is passed as an environment variable because the probe is a plain script.
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
      Environment = [ "EXPECTED_UNITS=${lib.concatStringsSep " " expectedUserUnits}" ];
      ExecStart = pkgs.writeShellScript "serenity-smoke-run" ''
        exec > /dev/ttyS0 2>&1
        exec ${probe}
      '';
    };
  };
}
