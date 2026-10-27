# OCR: the ocrflow Nextcloud app (PHP) + the ocrflow worker (Python), both from
# github:Likivik/ocrflow.
#
# Cutover 2026-10-27 — the app became the control plane (it owns the job queue,
# the per-file state and the admin panel in the Nextcloud DB) and the worker
# became a stateless HTTP client of the app's own OCS queue endpoints. See
# docs/adr/0001 and 0002 in that repository. What that means for this file:
#
#   * no `nc-ocr-webhook` unit, no FastAPI listener on 127.0.0.1:8095, no uv
#     venv in /var/lib/nc-ocr — the unit is owned by the flake's NixOS module,
#     which also owns its two LoadCredential secrets;
#   * no WebhookListeners registration: the queue replaced file events, so
#     register-webhook.php, the `occ workflows:list` report and the background
#     job dispatch loop are all gone with it;
#   * no `ocrflow_url` / `ocrflow_secret` system config: the worker
#     authenticates against the queue with the shared secret that
#     `occ ocrflow:worker:secret` prints, delivered through LoadCredential;
#   * the single-owner invariant (exactly one OCR writer per instance) is the
#     module's own evaluation-time `throw` + `appstoreEnable = mkForce false`,
#     so the second copy that used to live here is deliberately gone — one
#     guard, not two that can drift apart.
{ den, inputs, ... }:

{
  # Declared next to the aspect that uses it (same pattern as torrserver and
  # hermes-webui). flake.nix is GENERATED from these declarations by
  # `nix run .#write-flake` — hand edits there are reverted by check-flake-file.
  flake-file.inputs = {
    ocrflow = {
      url = "github:Likivik/ocrflow";
      # One nixpkgs in the closure. The app tree is PHP + a prebuilt JS bundle,
      # so nothing in it is tied to the nixpkgs the flake pins for itself.
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.server.workflow-ocr = {
    nixos =
      { config, lib, pkgs, ... }:
      let
        # ── Assets the worker still needs, which the module does not set ──────
        # Both paths are env-driven in the worker and both have defaults that are
        # wrong here:
        #   * NC_OCR_FONT_PATH defaults to /run/current-system/sw/share/X11/
        #     fonts/DejaVuSans.ttf, which does not exist without
        #     fonts.fontDir.enable; ocr.py then writes the invisible text layer
        #     with Latin-only Helvetica, so a Cyrillic scan looks perfect and is
        #     unsearchable — the exact failure this pipeline exists to prevent.
        #   * the two ONNX models (doc/photo gate, page orientation) have no
        #     default at all: without them the gate is skipped and orientation
        #     falls back to the 4-rotation OCR vote.
        # Symlinks, not copies, so tessdata's ~200 languages are not duplicated
        # into a second store path. Asserted at BUILD time: a missing file here
        # is a silent quality regression, not an error, unless we make it one.
        ocrAssets = pkgs.runCommand "ocrflow-assets" { } ''
          mkdir -p $out
          ln -s ${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSans.ttf $out/DejaVuSans.ttf
          ln -s ${pkgs.tesseract5}/share/tessdata $out/tessdata
          test -s $out/DejaVuSans.ttf
          test -s $out/tessdata/rus.traineddata
          test -s $out/tessdata/eng.traineddata
        '';
      in
      {
        # Owns systemd.services.ocrflow-worker (hardened, Restart=always,
        # LoadCredential ocrflow-worker-secret + ocrflow-dav-password), the
        # `ocrflow` system user, the secrets-exist assertions and the
        # competing-OCR-app throw.
        imports = [ inputs.ocrflow.nixosModules.ocrflow ];

        services.ocrflow = {
          enable = true;
          # nginx on this host is the only thing in front of Nextcloud.
          url = "http://127.0.0.1";
          # Recorded on claimed jobs, so a stuck claim names its owner.
          workerName = config.networking.hostName;
          # Parity with the retired unit (NC_OCR_ENGINE=google). `null` would
          # let the app's own setting decide.
          engine = "google";

          # Worker shared secret. The app keeps the value in its own app config
          # (`worker_secret`) and `occ ocrflow:worker:secret` normally generates
          # it; sops stays the single source of truth instead, and the oneshot
          # below copies this same file into the app config. So the value the
          # worker presents and the value the app compares are one file, not two
          # that have to be kept in sync by hand.
          secretFile = config.sops.secrets."nextcloud/ocr-webhook-secret".path;
          # WebDAV identity the worker downloads files with. Still likivik's app
          # password — a dedicated `ocrflow-worker` account (ADR 0002, option A)
          # does not exist yet; see the TODO in modules/hosts/poweredge.
          davPasswordFile = config.sops.secrets."nextcloud/ocr-webdav-password".path;
        };

        # ── Seed the app's worker_secret from sops ────────────────────────────
        # Same shape as nextcloud-configure-richdocuments: an idempotent oneshot
        # running `occ config:app:set`. The secret arrives via LoadCredential, so
        # it is not in the unit's command line (where `systemctl show` and
        # /proc/*/cmdline would expose it) and not in the store.
        #
        # TODO(cutover): the module has no option for this, because upstream
        # assumes the operator runs `occ ocrflow:worker:secret` once and copies
        # the printed value out. Fold this into services.ocrflow when it grows a
        # `secretFromAppConfig` (or accept it as the permanent shape).
        #
        # Ordering: the app value must exist before the worker's first claim, and
        # php-fpm caches app config — a rotation therefore also needs
        # `phpfpm-nextcloud.service` restarted, which is what the sops
        # restartUnits entry in modules/hosts/poweredge arranges.
        systemd.services.ocrflow-worker-secret = {
          description = "Seed the ocrflow worker secret (sops → app config)";
          after = [ "nextcloud-setup.service" ];
          wants = [ "nextcloud-setup.service" ];
          wantedBy = [ "multi-user.target" ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
            LoadCredential =
              "ocrflow-worker-secret:${config.sops.secrets."nextcloud/ocr-webhook-secret".path}";
          };
          script = ''
            ${config.services.nextcloud.occ}/bin/nextcloud-occ \
              config:app:set ocrflow worker_secret \
              --value="$(cat "$CREDENTIALS_DIRECTORY/ocrflow-worker-secret")"
          '';
        };

        systemd.services.ocrflow-worker = {
          wants = [ "ocrflow-worker-secret.service" ];
          after = [ "ocrflow-worker-secret.service" ];
          # Asset paths only. Everything about identity, restart policy and
          # hardening stays the module's: overriding ExecStart or the credential
          # list here would recreate the hand-rolled unit this change removed.
          environment = {
            NC_OCR_FONT_PATH = "${ocrAssets}/DejaVuSans.ttf";
            TESSDATA_PREFIX = "${ocrAssets}/tessdata";
            NC_OCR_MOBILENET_MODEL = "/etc/static/ocrflow/mobilenet_v3_small_fp32.onnx";
            NC_OCR_ORIENTATION_MODEL = "/etc/static/ocrflow/pp_lcnet_x1_0_doc_ori.onnx";
          };
        };

        # Doc/photo gate: MobileNetV3-Small fp32 (0=document, 1=photo), read by
        # the worker's classifier. The int8 sibling is broken (logits collapse to
        # ~zero, real scans come back "photo"), so fp32 only. Measured on this
        # host: 6/6 text-bearing images caught, 53/54 text-free skipped, ~88
        # ms/image (tesseract text-density gives the same verdicts at 856 ms).
        environment.etc."ocrflow/mobilenet_v3_small_fp32.onnx".source =
          pkgs.fetchurl {
            url = "https://huggingface.co/vlad-m-dev/mobilenet_v3_small_onnx_photo_doc/resolve/main/mobilenet_v3_small.onnx";
            sha256 = "sha256-UpqXVXf5im68cG/r+YkEeGh08KuwXTjOacQMFA2OF18=";
          };

        # PP-LCNet_x1_0_doc_ori — 4-class document orientation (PaddleOCR),
        # margin-gated stage 1 of the orientation detector. 99.06% top-1 on the
        # PaddleOCR benchmark; Tesseract OSD routinely returns wrong angles on
        # real Russian scans.
        #
        # Both models live under /etc/ocrflow/ as separate per-file entries.
        # (They used to sit under nc-ocr/ and nc-ocr-flow/ — the names of the
        # retired packages. Do not turn /etc/ocrflow into a *merged* directory
        # option: a merged dir silently drops sibling files, which is how the
        # old layout lost one of these models.)
        environment.etc."ocrflow/pp_lcnet_x1_0_doc_ori.onnx".source =
          pkgs.fetchurl {
            url = "https://huggingface.co/PaddleOcrNet/PaddleOcrNet-models/resolve/main/PP-LCNet_x1_0_doc_ori.onnx";
            sha256 = "sha256-2FsxhQda/KGoMVf3PqwuUrWY1y6dR90ZzEovNgXiPj8=";
          };

        environment.etc."tessdata".source = "${pkgs.tesseract5}/share/tessdata";

        # The Nextcloud app itself: the flake's ocrflow-app package. Its store
        # root is `apps/ocrflow/` (a tarball-shaped layout, like the release
        # artifact), while services.nextcloud.extraApps is `attrsOf package` that
        # must be the app directory itself — the same thing fetchNextcloudApp
        # returns. Passing the package root would install an app directory
        # containing nothing but `apps/`, and Nextcloud would not find
        # appinfo/info.xml; passing `${pkg}/apps/ocrflow` as a string fails the
        # `package` type outright. Hence one symlink derivation.
        services.nextcloud.extraApps.ocrflow =
          pkgs.runCommand "ocrflow-app-dir" { } ''
            ln -s ${inputs.ocrflow.packages.${pkgs.system}.ocrflow-app}/apps/ocrflow $out
          '';
        services.nextcloud.extraAppsEnable = true;

        # appstoreEnable = mkForce false is NOT set here on purpose: the module's
        # single-owner block does it (services.ocrflow.forbidCompetingApps), and
        # it is the same guard that throws on a competing OCR app at evaluation
        # time. Two copies of that invariant is how they drift apart.

        # ── Still open, deliberately not "fixed" by guessing here ─────────────
        # 1. Google Vision credentials. The retired unit exported
        #    GOOGLE_APPLICATION_CREDENTIALS=$CREDENTIALS_DIRECTORY/google-ocr-key
        #    plus NC_OCR_GOOGLE_PROJECT/BUCKET/LOCATION. The module has no
        #    option for extra environment or extra LoadCredentials, and the
        #    Google client only honours a literal path, so this cannot be added
        #    without overriding ExecStart — which would put the whole unit back
        #    under this file's control. BLOCKING FOR DEPLOY: with engine=google
        #    and no key, every job fails at the Vision call.
        # 2. The nginx allow-list on the queue route. The module only WARNS with
        #    the snippet (it does not own the Nextcloud vhost), and this host is
        #    behind a Cloudflare tunnel, so the route is reachable from the
        #    internet with only the shared secret in front of it. The vhost's
        #    generic `~ \.php$` location sorts before a `^/ocs/...` regexp in
        #    NixOS's rendered config, and NixOS orders `locations` by attribute
        #    name, so dropping the snippet in blind would produce a location that
        #    never matches — this needs a real nginx test, not a guess.
        # 3. A dedicated `ocrflow-worker` DAV identity (ADR 0002 option A). The
        #    worker still authenticates as likivik, i.e. with authority over the
        #    whole instance instead of the folders OCR runs on.
      };
  };
}
