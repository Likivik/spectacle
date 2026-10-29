# Full-host boot smoke test for poweredge.
#
# Extends the ENTIRE `nixosConfigurations.poweredge` (via extendModules) into a
# QEMU VM and boots it. poweredge carries Nextcloud, the ocrflow app + worker and
# the Google OCR credentials, and until this file existed its only guard was
# `nix run .#host-eval -- poweredge`, which evaluates the toplevel drvPath and
# boots nothing. The cutover from the old `nc-ocr-webhook` unit to the ocrflow
# flake app passed that gate while the worker would have crash-looped on a
# missing module (fastapi) — this test is the answer to that class of defect.
#
# The gate, all runtime-only:
#   * system reaches running/degraded and NO failed unit sits outside the
#     allowlist in tests/poweredge-smoke-probe.sh
#   * every secret the host declares rendered NON-EMPTY through the real sops
#     path (a present-but-empty file is the 2026-10-14 incident signature)
#   * Nextcloud serves, `occ status` works, the ocrflow app is enabled, and the
#     personal settings panel renders for an authenticated user
#   * the app ACCEPTS the worker secret over OCS — one assertion that catches an
#     empty secret, a rotated-but-not-reloaded secret, and a broken
#     LoadCredential
#   * ocrflow-worker is active with both LoadCredential entries and no secret in
#     its Environment
#   * nothing listens on :8095 (the retired listener)
#
# Neutralised, with the fidelity actually lost:
#   - TPM-bound sops: no TPM in QEMU. The host's identity is swapped for a
#     throwaway age identity generated at BUILD time and never committed, and
#     every secret is re-pointed at a dummy encrypted file generated at BUILD
#     TIME from the host's own sops.secrets declarations. Secret VALUES are
#     dummy; the rendering and LoadCredential path is the real one. Lost: the
#     TPM-bound decryption itself, which is asserted on the host, not here.
#   - Networking: poweredge's static networkd config leaves eth0 routeless under
#     QEMU SLIRP, so DHCP with useNetworkd=false.
#   - Tailscale: no tailnet, and it holds network-online.target hostage.
#   - disko/disk layout: the guest boots the generated image filesystem, not the
#     real disks. Lost: anything about partitioning, impermanence and rollback.
#
# Secret hygiene — this repo is private, which is not a licence to be careless:
#
#   * every secret VALUE in the guest is the dummy below; the real ones are never
#     read, never copied, never in the store;
#   * the age identity that decrypts them is GENERATED PER BUILD (age-keygen) and
#     never committed, so it can decrypt nothing outside this VM. A checked-in key
#     would normalise private keys in the tree and leak through history;
#   * no assertion may print a secret. The probe reports paths, unit names,
#     variable NAMES and HTTP status codes only. Credentials reach curl through
#     0600 files (netrc / curl -K), never argv, because argv is ps-visible and the
#     serial log gets pasted into PRs;
#   * `services.ocrflow.secretFile` is pointed at a sops-rendered path, and sops in
#     this VM only ever opens the build-time dummy file. Pointing this module at a
#     real sops file would fail to decrypt (wrong identity) rather than succeed
#     quietly — that is the property that makes the substitution safe.
#
# Run:  nix run .#poweredge-smoke
# The probe is tests/poweredge-smoke-probe.sh; it runs as an in-guest oneshot,
# reports on the serial console, and ends with POWEREDGE_SMOKE_PASS/FAILED.
{ config, pkgs, lib, base, ... }:
let
  # --- a real (but worthless) sops round-trip ------------------------------
  # `base` is the UN-extended poweredge config, so reading its sops.secrets here
  # is not self-referential.
  dummyValue = "vm-smoke-dummy-secret-value";

  # "a/b/c" -> { a = { b = { c = v; }; }; }
  nest = paths: v: lib.foldr (p: acc: { ${p} = acc; }) v paths;

  # Every secret the host declares, so a new secret is covered automatically.
  dummyPlain = lib.foldl'
    (acc: n: lib.recursiveUpdate acc (nest (lib.splitString "/" n) dummyValue))
    { }
    (lib.attrNames base.config.sops.secrets);

  # The age identity is generated HERE, at build time, and never committed. A
  # checked-in private key would normalise private keys in the tree and leak
  # through history; this identity is fresh per build and decrypts dummies only.
  smokeSecrets = pkgs.runCommand "poweredge-smoke-secrets" {
    nativeBuildInputs = [ pkgs.sops pkgs.age ];
    HOME = "$TMPDIR";
  } ''
    mkdir -p $out
    age-keygen -o identity.txt 2> keygen.err
    RECIPIENT=$(grep -oE 'age1[0-9a-z]+' keygen.err | head -1)
    test -n "$RECIPIENT"

    cat > plain.yaml <<'YAML'
${lib.generators.toYAML { } dummyPlain}
YAML
    sops --encrypt --age "$RECIPIENT" \
      --input-type yaml --output-type yaml plain.yaml > $out/secrets.yaml

    install -m 0400 identity.txt $out/identity.txt
  '';

  dummySopsFile = "${smokeSecrets}/secrets.yaml";

  # Tripwire: the dummy file must always be the build-time artefact above. If
  # anyone re-points it at a real sops file, evaluation fails instead of booting a
  # VM wired to production secrets.
  _dummyIsBuildArtefact =
    if lib.hasPrefix builtins.storeDir dummySopsFile then true
    else throw "poweredge-smoke: dummySopsFile is not a build-time artefact - refusing to boot with what may be a real sops file";

  # The rendered path of every declared secret. Passed as a FILE: serviceConfig
  # Environment values are unquoted and word-split, so a space-joined list
  # silently arrives as its first element only.
  secretPaths = map
    (n: base.config.sops.secrets.${n}.path or ("/run/secrets/" + n))
    (lib.attrNames base.config.sops.secrets);
  secretPathsFile = pkgs.writeText "poweredge-smoke-secrets-list"
    (lib.concatStringsSep "\n" secretPaths + "\n");

  adminPassFile = config.sops.secrets."nextcloud/admin-password".path;
  adminUser = config.services.nextcloud.config.adminuser or "admin";

  # Nextcloud's password_policy app forbids "simple" passwords, so the shared dummy
  # (no digit, no uppercase) is rejected and the admin login is a 401. nixpkgs' own
  # nextcloud tests use a policy-compliant value and say why
  # (nixos/tests/nextcloud/default.nix: adminpass = "+CVpTwaOEktxsFc6").
  smokeAdminPassFile = pkgs.writeText "poweredge-smoke-admin-pass" "+CVpTwaOEktxsFc6";

  probe = pkgs.writeShellScript "poweredge-smoke-probe"
    (builtins.readFile ./poweredge-smoke-probe.sh);
in
{
  # See services.ocrflow.checkSecretFiles: the module's pathExists assertions
  # cannot hold here, because sops renders those files at BOOT and the builder
  # cannot see them. This is the module's own supported switch, added for exactly
  # this case — not an assertion bypass.
  # The guest's NIC is `eth0`; poweredge's is `eno1`. A firewall rule naming a
  # device that does not exist stalls the boot (measured 2026-10-29: system sat in
  # `starting` for the full 120s settle window, with no failed unit). Re-point the
  # wire at the device the guest actually has, so the gate exercises the model
  # instead of the host's NIC census.
  networkFirewall.ifaces.lan = lib.mkForce "eth0";

  services.ocrflow.checkSecretFiles = lib.mkForce false;
  # In the guest every dummy secret has the same value, which is exactly what makes
  # the worker's WebDAV login authenticatable: davPasswordFile renders the same dummy
  # Nextcloud installed its admin user with.
  services.ocrflow.davUser = lib.mkForce "admin";

  # Nextcloud's password_policy app (enabled right after install) forbids "simple"
  # passwords, so the shared dummy — no digit, no uppercase — is rejected and the
  # admin login is a 401. nixpkgs' own nextcloud tests use a policy-compliant value
  # (nixos/tests/nextcloud/default.nix: adminpass = "+CVpTwaOEktxsFc6") and say why.
  #
  # Honest cost: the DAV password now comes from this file, not from sops, so it no
  # longer proves the sops delivery path for THAT credential. The worker shared
  # secret still does (it is read from LoadCredential and must be accepted by the
  # app over OCS), and "every declared secret rendered non-empty" still covers the
  # sops pipeline itself.
  services.nextcloud.config.adminpassFile = lib.mkForce "${smokeAdminPassFile}";
  services.ocrflow.davPasswordFile = lib.mkForce "${smokeAdminPassFile}";

  # --- guest networking ---
  systemd.network.enable = lib.mkForce false;
  networking.useNetworkd = lib.mkForce false;
  networking.useDHCP = lib.mkForce true;
  networking.nameservers = lib.mkForce [ "1.1.1.1" "8.8.8.8" ];

  # --- no TPM: swap the identity and re-point every secret at dummy values ---
  # NOT `sops.secrets = mkForce {}`: that renders nothing, so every assertion
  # about the rendered files would be vacuous.
  sops = {
    age.keyFile = lib.mkForce "/run/smoke-age-key.txt";
    age.plugins = lib.mkForce [ ];
    secrets = lib.mapAttrs
      (n: _: { sopsFile = lib.mkForce dummySopsFile; })
      base.config.sops.secrets;
    # The dummy file is a build-time derivation, so sops-nix's pre-flight check
    # (which wants a real, present sops file) rejects it. The guest does not need
    # that check: the gate asserts the rendering RESULT at boot.
    validateSopsFiles = lib.mkForce false;
  };

  # The identity cannot be a store path (sops-nix rejects store paths for
  # sops.age.keyFile) and cannot come from tmpfiles (not ordered against
  # sops-install-secrets), so it is installed by a unit ordered before it.
  systemd.services."smoke-age-key" = {
    wantedBy = [ "sysinit.target" ];
    requiredBy = [ "sops-install-secrets.service" ];
    before = [ "sops-install-secrets.service" ];
    # REQUIRED, not cosmetic: with the default (yes) this unit inherits
    # After=basic.target, which is reached THROUGH sysinit.target while
    # sops-install-secrets must run BEFORE it — an ordering cycle that systemd
    # resolves by DELETING the sops job, with "no secrets installed" as the only
    # symptom. sops-nix sets the same flag on its own unit.
    unitConfig.DefaultDependencies = "no";
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    # Absolute paths: a unit gets systemd's minimal PATH, where install is absent
    # on NixOS, and a missing binary here leaves the consumer INACTIVE rather
    # than failed — a failure that looks nothing like a PATH problem.
    script = ''
      ${pkgs.coreutils}/bin/install -m 0400 -o root -g root ${smokeSecrets}/identity.txt /run/smoke-age-key.txt
    '';
  };

  # --- tailscale needs a tailnet + auth key ---
  # Forces the tripwire above at evaluation time, so it cannot rot into dead code.
  assertions = [
    {
      assertion = _dummyIsBuildArtefact;
      message = "poweredge-smoke: refusing to boot with a non-build-time sops file";
    }
  ];

  services.tailscale.enable = lib.mkForce false;

  # Units that cannot run without host hardware or a container image store. Disabling
  # them is better than allowlisting: an allowlist entry grants immunity to a name
  # forever, a disabled unit cannot fail at all. Whatever still fails gets an explicit
  # anchored entry in the probe, with the observation that earned it.
  # Also guest-impossible, and they block multi-user.target by sitting in
  # `activating`: cloudflared needs a real tunnel, nextcloud-mcp needs the network.
  systemd.services."cloudflared-poweredge".enable = lib.mkForce false;

  # Container-backed units (nextcloud-mcp, immich-server, qdrant, podman-collabora)
  # are NOT `systemd.services.<name>` — they come from virtualisation.oci-containers,
  # so `enable = false` on the service does nothing and they fail with
  # start-limit-hit while blocking multi-user. Remove the containers in the guest.
  #
  # Cost, stated plainly: the container definitions themselves are NOT exercised by
  # this smoke. That is a coverage hole, not a pass.
  virtualisation.oci-containers.containers = lib.mkForce { };

  # fail2ban drives nftables against a real WAN; in the guest it start-limit-hits and
  # its socket fails with it.
  services.fail2ban.enable = lib.mkForce false;

  systemd.services."zfs-import-tank".enable = lib.mkForce false;
  systemd.services."qdrant".enable = lib.mkForce false;
  systemd.services."podman-collabora-code".enable = lib.mkForce false;
  systemd.services."tailscale-serve".enable = lib.mkForce false;

  # The store optimiser hard-links store paths, which cannot work on the guest's
  # virtiofs mount ("Stale file handle"). It is timer-driven, so whether it fires
  # inside the boot window is pure timing — an intermittent unexpected failure.
  nix.optimise.automatic = lib.mkForce false;

  # The guest image defaults to 1 GiB, and Nextcloud + PostgreSQL + nine apps blow
  # through it during nextcloud-setup: "SQLSTATE[53100]: Disk full: could not extend
  # file base/16384/17186" — which surfaced as a *failed nextcloud-setup* and as
  # `I/O error, dev vda` lines, and made the container units appear intermittently.
  # A full disk in the guest looks exactly like a broken app; it is neither.
  virtualisation.diskSize = 16 * 1024;

  users.users.root.initialPassword = "test";

  # The guest ttyS0 is ours: agetty resets the tty underneath a running probe, so
  # its output silently vanishes while the script keeps running.
  systemd.services."serial-getty@ttyS0".enable = false;

  # The probe is a TIMER job, not a multi-user.target job. `wantedBy =
  # multi-user.target` makes the target wait for the probe, so the probe can never
  # observe "multi-user reached" — a self-deadlock one level up from the
  # `is-system-running --wait` one, and the reason two runs asserted against a
  # half-booted host. OnBootSec lets the boot finish, then measures it.
  systemd.services.vmcheck-poweredge = {
    description = "poweredge full-host boot smoke test (see tests/poweredge-smoke-probe.sh)";
    wants = [ "network-online.target" ];
    # After=multi-user.target WITHOUT being wanted by it: the job is held until the
    # target completes, but the target does not wait for the probe (which is the
    # deadlock that `wantedBy = multi-user.target` creates). A bare OnBootSec timer
    # fired 90s into a boot that had not finished — the probe got HTTP 500 from
    # Nextcloud, "sudo: unknown user www-data", and even `cut` failing to load libc.
    requires = [ "multi-user.target" ];
    after = [ "multi-user.target" "network-online.target" ];
    # occ and php-fpm can take a while on a cold guest.
    serviceConfig.TimeoutStartSec = "15min";
    # sudo/dbus are needed for `systemctl` to answer at all; without gawk the
    # unit-name parsing silently returns nothing and the gate passes vacuously.
    path = with pkgs; [ systemd coreutils gnugrep gnused gawk iproute2 getent sudo sqlite curl postgresql ];
    serviceConfig = {
      Type = "oneshot";
      Environment = [
        "SMOKE_SECRETS=${secretPathsFile}"
        "SMOKE_ADMIN_USER=${adminUser}"
        "SMOKE_ADMIN_PASS_FILE=${smokeAdminPassFile}"
      ];
      ExecStart = pkgs.writeShellScript "poweredge-smoke-run" ''
        exec > /dev/ttyS0 2>&1
        exec ${probe}
      '';
    };
  };

  systemd.timers.vmcheck-poweredge = {
    description = "start the poweredge smoke probe once the box has settled";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "90s";
      Unit = "vmcheck-poweredge.service";
    };
  };
}
