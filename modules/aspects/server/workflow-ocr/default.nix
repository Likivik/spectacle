{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.workflow-ocr = {
    nixos = { config, lib, pkgs, ... }:

    let
      # ── Single-owner invariant ────────────────────────────────────────────
      # Exactly ONE OCR pipeline may own PDFs in this Nextcloud.
      #
      # A second writer that OCRs on the same postCreate/postWrite events does
      # not "add" anything: it overwrites the first one's text layer a couple
      # of minutes later, silently, and the XMP stamp survives the rewrite — so
      # the victim's own skip logic still records the file as
      # ``stamped_good_by_us`` and its results are lost while its API spend is
      # already paid. That is not hypothetical: the third-party ``workflow_ocr``
      # app (R0Wi-DEV) was installed here alongside this service and did exactly
      # that on every file it saw (measured 2026-10-17: our 7,671,434-byte
      # Google layer replaced by a 6,354,148-byte OCRmyPDF one that extracts
      # 0 Cyrillic / 4,069 orphan combining marks).
      #
      # Guards, in order of defence:
      #   1. The ``throw`` guard below — fails EVALUATION (nix eval, nix build,
      #      nixos-rebuild, the CI eval job) if a known competing OCR app is
      #      configured again. Deliberately a throw and not a NixOS
      #      ``assertions`` entry, which only fails once the system is really
      #      built. Curated list: extend ``competingOcrApps`` when another OCR
      #      app is found.
      #   2. ``appstoreEnable = lib.mkForce false`` further down — the app store
      #      is the only way a rival could appear at runtime (the throw can only
      #      see what nix configures).
      #   3. ``enforce-single-owner.php``, run from the nc-ocr-register-webhook
      #      oneshot: disables a competing app that is still enabled, and
      #      REPORTS (never deletes) its leftover Flow rule — every deletion
      #      path needs an interactive password confirmation, and a rule whose
      #      app is disabled is skipped silently anyway. Covers an app enabled
      #      by hand, and the
      #      transition itself — nixpkgs never disables an app dropped from
      #      ``extraApps`` (nextcloud.nix only ever runs ``app:enable``), and
      #      Nextcloud's Updater only disables apps whose files vanished when it
      #      actually runs an upgrade, so neither can be relied on here.
      #   4. Runtime, in the service itself: it re-checks the file fingerprint
      #      it wrote before trusting its stamp and reports foreign rewrites
      #      via /stats (see nc_ocr_flow.webhook_server).
      competingOcrApps = [ "workflow_ocr" ];

      # ── OCS access for the webhook-registration oneshot ───────────────────
      # Listeners are registered through the documented OCS API as a dedicated
      # service account whose group holds only
      # OCA\WebhookListeners\Settings\Admin. ``ocsBaseUrl`` MUST be an address
      # Nextcloud's ``allowed_admin_ranges`` permits — here the Tailscale
      # ranges — because the admin-action IP check runs AFTER authorisation and
      # rejects loopback and the LAN address with AdminIpNotAllowed
      # (SecurityMiddleware -> RemoteAddress::allowsAdminActions). See
      # register-webhook.php for the full rationale.
      # Derived from the host, so this aspect cannot silently point at
      # another machine's Nextcloud if it is ever reused. The tailnet domain
      # is the fleet-wide constant. poweredge -> http://poweredge.oryx-galaxy.ts.net
      ocsBaseUrl = "http://${config.networking.hostName}.oryx-galaxy.ts.net";
      ocsServiceUser = "ocr-svc";

      ncRoot = config.services.nextcloud.finalPackage;
      ncPhp = config.services.phpfpm.pools.nextcloud.phpPackage;

      # nc-ocr-flow source — Python deps installed via uv venv
      ncOcrFlowSrc = ../../../../pkgs/nc-ocr-flow;
      ocrVenv = "/var/lib/nc-ocr/venv-v4";

      # Files whose content change MUST trigger a venv reinstall.
      # We track hashes (see ``webhookStartScript`` below) instead of
      # mtimes because every file inside ``/nix/store`` has a synthetic
      # mtime of 1970-01-01, so a `-ot` comparison against the venv
      # marker is always false — the mtime guard never fired and any
      # Python fix landed after 2026-09-27 never reached the deployed
      # venv copy.
      ncOcrFlowSrcFiles = [
        "${ncOcrFlowSrc}/src/nc_ocr_flow/webhook_server.py"
        "${ncOcrFlowSrc}/src/nc_ocr_flow/ocr.py"
        "${ncOcrFlowSrc}/src/nc_ocr_flow/jobstore.py"
      ];

      # Start script: create venv with pip if missing, then run webhook server
      webhookStartScript = pkgs.writeShellScript "nc-ocr-webhook-start" ''
        set -eu
        export NC_OCR_NC_PASSWORD_FILE="$CREDENTIALS_DIRECTORY/nc-ocr-password"
        export NC_OCR_WEBHOOK_SECRET_FILE="$CREDENTIALS_DIRECTORY/nc-ocr-webhook-secret"
        export GOOGLE_APPLICATION_CREDENTIALS="$CREDENTIALS_DIRECTORY/google-ocr-key"
        export NC_OCR_MINIMAX_KEY_FILE="$CREDENTIALS_DIRECTORY/nc-ocr-minimax-key"

        # Content-based staleness check. ${ocrVenv}/.installed carries
        # one "<source-path>=<sha256>" line per file in
        # ncOcrFlowSrcFiles; if any line disagrees with the current
        # hash (or any file is missing from the manifest) we rebuild.
        #
        # Why not just compare mtimes? Every file under ${"$"}{NIX_STORE:-/nix/store}
        # has a synthetic mtime of 1970-01-01, which is older than any
        # ``touch`` a systemd ExecStart can produce. The old
        # ``[ ".installed" -ot "$src" ]`` test was therefore always
        # false, and venv rebuilds never happened after the first run.
        rebuild=0
        manifest="${ocrVenv}/.installed"
        if [ ! -d "${ocrVenv}" ] || [ ! -f "$manifest" ]; then
          rebuild=1
        else
          for f in ${lib.concatStringsSep " " ncOcrFlowSrcFiles}; do
            current=$(sha256sum "$f" 2>/dev/null | awk '{print $1}')
            expected=$(grep -F "$f=" "$manifest" 2>/dev/null \
                       | head -n 1 | sed 's/.*=//')
            if [ -z "$current" ] || [ "$current" != "$expected" ]; then
              rebuild=1
              break
            fi
          done
        fi

        if [ "$rebuild" -eq 1 ]; then
          echo "Creating OCR venv (python3.12)..."
          rm -rf "${ocrVenv}"
          ${pkgs.python312}/bin/python3.12 -m venv ${ocrVenv}
          ${ocrVenv}/bin/pip install --no-cache-dir pymupdf pillow requests img2pdf numpy onnxruntime fastapi uvicorn pydantic
          ${ocrVenv}/bin/pip install --no-cache-dir google-cloud-vision google-cloud-storage
          ${ocrVenv}/bin/pip install --no-cache-dir pdf-inspector
          ${ocrVenv}/bin/pip install --no-cache-dir --no-deps ${ncOcrFlowSrc}

          # Write the manifest of current content hashes so the next
          # start can tell at a glance whether the venv is fresh.
          : > "$manifest"
          for f in ${lib.concatStringsSep " " ncOcrFlowSrcFiles}; do
            h=$(sha256sum "$f" | awk '{print $1}')
            printf '%s=%s\n' "$f" "$h" >> "$manifest"
          done
        fi
        export PYTHONPATH="${ncOcrFlowSrc}/src:''${PYTHONPATH:-}"
        exec ${ocrVenv}/bin/python -m nc_ocr_flow.webhook_server
      '';

      # PHP script registering the listeners through the documented OCS API
      registerWebhookPhp = ./register-webhook.php;
      # PHP script enforcing the single-OCR-owner invariant (guard #3 above)
      enforceSingleOwnerPhp = ./enforce-single-owner.php;
    in {
      # ── Guard #1: single-owner block (eval-time) ──────────────────────────
      # Deliberately a ``throw`` and NOT a NixOS ``assertions`` entry: assertions
      # are folded into the baseSystem derivation by ``lib.asserts.checkAssertWarn``
      # (nixpkgs nixos/modules/system/activation/top-level.nix), so a false
      # assertion does NOT fail ``nix eval`` or ``nix build --dry-run`` — it only
      # fails once the system is really built. Verified 2026-10-17: with a
      # competing app configured, the toplevel still evaluated to the same
      # drvPath and the dry-run happily listed 36 derivations. Too late and too
      # quiet for a "never run two OCR writers" invariant.
      #
      # It is attached to an option VALUE rather than computed in the module's
      # ``let``: referencing ``config`` at the top level of a module body is
      # infinite recursion, because the module argument depends on this module's
      # own definitions (that is what an earlier version of this guard did).
      # Inside an option value it is forced only once all definitions have been
      # collected — the same reason the ``config.sops.secrets`` references below
      # are safe.
      environment.systemPackages = [
        pkgs.ocrmypdf
        pkgs.tesseract5
        pkgs.poppler-utils
      ] ++ lib.optionals
        (lib.any (app: config.services.nextcloud.extraApps ? ${app}) competingOcrApps)
        (throw ''
          Two OCR pipelines are configured for the same Nextcloud.

          den.aspects.server.workflow-ocr runs nc-ocr-flow (Google Vision) as the single
          OCR owner, but these competing OCR apps are also configured:
            ${lib.concatStringsSep ", " (lib.filter (app: config.services.nextcloud.extraApps ? ${app}) competingOcrApps)}

          A second OCR writer reacts to the same postCreate/postWrite events and overwrites
          the first one's text layer minutes later, while leaving its XMP stamp in place.
          The other pipeline therefore keeps recording those files as already-processed and
          its results are silently lost, with its API spend already paid.

          Fix it one of two ways:
            * drop the competing app from services.nextcloud.extraApps, or
            * stop including den.aspects.server.workflow-ocr and let the other pipeline
              own PDFs.
          Do not run both.
        '');

      # Tesseract language data
      environment.etc."tessdata".source = "${pkgs.tesseract5}/share/tessdata";

      # MobileNetV3-Small fp32 doc/photo classifier (0=document, 1=photo),
      # read by nc_ocr_flow.classifier from /etc/static/nc-ocr/.
      # The int8 sibling of this model is broken (logits collapse to ~zero and
      # real scans come back "photo"), so fp32 only. Measured on this host:
      # 6/6 text-bearing images caught, 53/54 text-free skipped, ~88 ms/image
      # (tesseract text-density gives the same verdicts at 856 ms).
      environment.etc."nc-ocr/mobilenet_v3_small_fp32.onnx".source =
        pkgs.fetchurl {
          url = "https://huggingface.co/vlad-m-dev/mobilenet_v3_small_onnx_photo_doc/resolve/main/mobilenet_v3_small.onnx";
          sha256 = "sha256-UpqXVXf5im68cG/r+YkEeGh08KuwXTjOacQMFA2OF18=";
        };

      # PP-LCNet_x1_0_doc_ori — 4-class document-orientation classifier
      # (PaddleOCR). Used by nc_ocr_flow.doc_ori as stage-1 of the
      # orientation detector (margin-gated; falls through to the
      # 4-rotation OCR vote when the margin < 0.15). Picked for
      # its 99.06% top-1 on the PaddleOCR benchmark; Tesseract OSD
      # routinely returns wrong angles on real Russian scans.
      # Source URL picked from the PaddleOcrNet HF repo (the
      # official PaddlePaddle/PP-LCNet_x1_0_doc_ori release).
      # Model size ~6.4 MB, sha256 verified against the local
      # copy in /var/lib/hermes/.hermes/cache/scratch/models/
      # PP-LCNet_x1_0_doc_ori.onnx.
      #
      # Note: lives under `nc-ocr-flow/`, NOT `nc-ocr/` — the
      # `nc-ocr/` directory is owned by a separate merged-dir
      # derivation (`nc-ocr-models`) that drops sibling files,
      # so per-file entries under that prefix are silently lost.
      environment.etc."nc-ocr-flow/pp_lcnet_x1_0_doc_ori.onnx".source =
        pkgs.fetchurl {
          url = "https://huggingface.co/PaddleOcrNet/PaddleOcrNet-models/resolve/main/PP-LCNet_x1_0_doc_ori.onnx";
          sha256 = "sha256-2FsxhQda/KGoMVf3PqwuUrWY1y6dR90ZzEovNgXiPj8=";
        };

      # NOTE: ``nextcloud-cron.path`` / ``nextcloud-setup.path`` used to get
      # ocrmypdf + tesseract injected here. That existed only for the
      # third-party ``workflow_ocr`` app, which ran OCRmyPDF from the Nextcloud
      # cron context; this service carries its own PATH on its own unit, so the
      # injections went away with the app (2026-10-17).

      # --- OCR Flow app: context-menu action → nc-ocr-flow webhook ---
      # Install as a raw app directory (nix-built, no fetchNextcloudApp —
      # the app is ours, built from this repo).
      services.nextcloud.extraApps = {
        # Nix-built app dir (appinfo/info.xml at store root — same shape as
        # fetchNextcloudApp output). This is OUR app: the context-menu action
        # and status panel, which talk to the local nc-ocr-flow service. It
        # does no OCR itself.
        ocrflow = pkgs.callPackage ../../../../pkgs/ocrflow-ncapp { };
      };
      services.nextcloud.extraAppsEnable = true;
      # Guard #2: keep the app store off. It is the only route by which a
      # competing OCR app could appear at runtime — the build-time assertion
      # can only see what nix configures.
      services.nextcloud.appstoreEnable = lib.mkForce false;

      # Wire the webhook secret into the app's system config so the PHP
      # proxy can authenticate to the local nc-ocr-flow service.
      # NB: $nextcloudOcc is NOT defined in postStart (only in the module's
      # own script) — use config.services.nextcloud.occ directly.
      systemd.services.nextcloud-setup.postStart = lib.mkAfter ''
        ${config.services.nextcloud.occ}/bin/nextcloud-occ config:system:set ocrflow_url --value="http://127.0.0.1:8095"
        ${config.services.nextcloud.occ}/bin/nextcloud-occ config:system:set ocrflow_secret --value="$(cat ${config.sops.secrets."nextcloud/ocr-webhook-secret".path})"
      '';

      # --- OCR webhook receiver service ---
      systemd.services.nc-ocr-webhook = {
        description = "Nextcloud OCR webhook receiver (google-vision + tesseract fallback)";
        after = [ "nextcloud-setup.service" "network.target" ];
        wants = [ "nextcloud-setup.service" ];
        wantedBy = [ "multi-user.target" ];

        environment = {
          NC_OCR_NC_URL = "http://localhost";
          # WebDAV creds must match the app password in sops
          # nextcloud/ocr-webdav-password (that password belongs to likivik,
          # NOT admin — a user/password mismatch caused 401s and silently
          # blocked all OCR processing, 2026-09-03).
          NC_OCR_NC_USER = "likivik";
          # Engine: google (default) = Google Cloud Vision whole-doc OCR;
          # tesseract = local ocrmypdf fallback. minimax available via
          # NC_OCR_ENGINE=minimax. Surya/monkey/L2 routing removed 2026-09.
          NC_OCR_ENGINE = "google";

          # Параллелизм. Очередь задач живёт в SQLite, поэтому воркеров
          # можно поднимать без роста памяти. Каждый движок имеет свой
          # потолок одновременных задач — это и есть защита квот API:
          # поднять NC_OCR_WORKERS можно, не превысив лимиты Google/VLM.
          NC_OCR_WORKERS = "2";
          NC_OCR_MAX_CONCURRENT_GOOGLE = "2";
          NC_OCR_MAX_CONCURRENT_TESSERACT = "1";
          NC_OCR_MAX_CONCURRENT_MINIMAX = "1";
          # Google Cloud Vision (service-account key via CREDENTIALS_DIRECTORY)
          NC_OCR_GOOGLE_PROJECT = "spectacle-xandria";
          NC_OCR_GOOGLE_BUCKET = "ocr-project-tmp";
          # NC_OCR_GOOGLE_LOCATION MUST match the bucket's region — if
          # the project/bucket live in another region, Vision silently
          # fails with no operator-visible hint (the engine defaults
          # to "US" otherwise). Keep in sync with ``NC_OCR_GOOGLE_BUCKET``.
          NC_OCR_GOOGLE_LOCATION = "US";
          # Async whole-document batch can take tens of minutes on
          # large scans. Default 1800s; raise this for very large jobs.
          NC_OCR_GOOGLE_BATCH_TIMEOUT = "1800";
          NC_OCR_LISTEN_HOST = "127.0.0.1";
          NC_OCR_LISTEN_PORT = "8095";
          NC_OCR_FONT_PATH = "${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSans.ttf";
          TESSDATA_PREFIX = "${pkgs.tesseract5}/share/tessdata";
          # Doc/photo gate: fp32 MobileNetV3-Small (see environment.etc."nc-ocr/...").
          NC_OCR_MOBILENET_MODEL = "/etc/static/nc-ocr/mobilenet_v3_small_fp32.onnx";
          # Stage-1 page-orientation classifier: PP-LCNet_x1_0_doc_ori.
          # Used by nc_ocr_flow.doc_ori; falls back to the 4-rotation
          # OCR vote when the margin is < 0.15 (see orientation.DOC_ORI_MARGIN_THRESHOLD).
          NC_OCR_ORIENTATION_MODEL = "/etc/static/nc-ocr-flow/pp_lcnet_x1_0_doc_ori.onnx";
          # onnxruntime imports numpy, which needs libz; without it `import numpy`
          # dies and every image hit the "classifier failed" path.
          LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib";
        };

        serviceConfig = {
          Type = "simple";
          User = "nextcloud";
          Group = "nextcloud";
          Restart = "on-failure";
          RestartSec = "10s";
          StateDirectory = "nc-ocr";
          StateDirectoryMode = "0755";
          TimeoutStartSec = "5min";  # first venv creation + pip install
          LoadCredential = let
            webdavPass = config.sops.secrets."nextcloud/ocr-webdav-password".path;
            webhookSecret = config.sops.secrets."nextcloud/ocr-webhook-secret".path;
            googleKey = config.sops.secrets."nextcloud/ocr-google-key".path;
            minimaxKey = config.sops.secrets."nextcloud/minimax-api-key".path;
          in [
            "nc-ocr-password:${webdavPass}"
            "nc-ocr-webhook-secret:${webhookSecret}"
            "google-ocr-key:${googleKey}"
            "nc-ocr-minimax-key:${minimaxKey}"
          ];
        };

        path = [
          pkgs.ocrmypdf
          pkgs.tesseract5
          pkgs.poppler-utils
          pkgs.curl
          pkgs.stdenv.cc.cc.lib
          # ``sha256sum`` / ``awk`` / ``sed`` / ``grep`` for the new
          # content-based venv-rebuild check. The systemd unit inherits
          # ``$PATH`` from the systemd manager, which on NixOS does
          # NOT include coreutils — declaring them here keeps the
          # start script (which runs without /etc/profile) working.
          pkgs.coreutils
          pkgs.gawk
          pkgs.gnused
          pkgs.gnugrep
        ];

        script = ''
          exec ${webhookStartScript}
        '';
      };

      # --- NC webhook background-job worker ---
      # NC fires webhooks via background jobs; default cron is every 5 min.
      # This worker polls for webhook dispatch jobs every 60s for faster OCR.
      systemd.services.nc-webhook-worker = {
        description = "Nextcloud webhook dispatch worker";
        after = [ "nextcloud-setup.service" ];
        wants = [ "nextcloud-setup.service" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          Type = "simple";
          User = "nextcloud";
          Group = "nextcloud";
          Restart = "always";
          RestartSec = "30s";
          LoadCredential = let
            adminPass = config.sops.secrets."nextcloud/admin-password".path;
            resendKey = config.sops.secrets."resend/api-key".path;
          in [
            "adminpass:${adminPass}"
            "mail_smtppassword:${resendKey}"
          ];
        };

        environment = {
          NEXTCLOUD_CONFIG_DIR = "/tank/nextcloud/config";
        };

        path = [ ncPhp ];

        script = ''
          while true; do
            ${ncPhp}/bin/php ${ncRoot}/occ background-job:worker -t 60 \
              "OCA\WebhookListeners\BackgroundJobs\WebhookCall" 2>&1 || true
            sleep 5
          done
        '';
      };

      # --- Register webhook listener (idempotent oneshot via PHP) ---
      systemd.services.nc-ocr-register-webhook = {
        description = "Register OCR webhook listener in Nextcloud";
        # tailscaled: the OCS call goes to this host's tailnet name, so
        # MagicDNS must be up (see register-webhook.php for why loopback and
        # the LAN address are refused).
        after = [ "nextcloud-setup.service" "nc-ocr-webhook.service" "tailscaled.service" ];
        wants = [ "nextcloud-setup.service" "nc-ocr-webhook.service" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          Type = "oneshot";
          User = "nextcloud";
          Group = "nextcloud";
          RemainAfterExit = true;
          # the PHP scripts log to /tmp; the default umask would leave them
          # world-readable
          UMask = "0077";
          LoadCredential = let
            adminPass = config.sops.secrets."nextcloud/admin-password".path;
            resendKey = config.sops.secrets."resend/api-key".path;
            webhookSecret = config.sops.secrets."nextcloud/ocr-webhook-secret".path;
            ocsAppPassword = config.sops.secrets."nextcloud/ocr-svc-app-password".path;
          in [
            "adminpass:${adminPass}"
            "mail_smtppassword:${resendKey}"
            "nc-ocr-webhook-secret:${webhookSecret}"
            "ocr-svc-app-password:${ocsAppPassword}"
          ];
        };

        environment = {
          NEXTCLOUD_CONFIG_DIR = lib.mkForce "/tank/nextcloud/config";
        };

        path = [ ncPhp ];

        script = ''
          # Register the file-event webhooks through the documented OCS API as
          # the dedicated service account (register-webhook.php explains why the
          # base URL has to be the Tailscale name).
          #
          # Retried: at boot MagicDNS may not be up yet. The failure that
          # matters is otherwise silent — after a secret rotation a stale
          # listener 401s every dispatch while the service still looks
          # perfectly healthy and only uploads quietly stop being processed.
          regRc=0
          attempt=1
          while [ "$attempt" -le 5 ]; do
            if ${ncPhp}/bin/php ${registerWebhookPhp} \
                 ${ocsBaseUrl} ${ocsServiceUser} \
                 "$CREDENTIALS_DIRECTORY/ocr-svc-app-password" \
                 "$CREDENTIALS_DIRECTORY/nc-ocr-webhook-secret"; then
              regRc=0
              break
            else
              regRc=$?
              echo "nc-ocr-register-webhook: attempt $attempt failed (see /tmp/ocr-webhook-register.log)" >&2
              attempt=$((attempt + 1))
              sleep 10
            fi
          done
          # Guard #3: make the single-owner invariant true of the running
          # instance, not just of the nix config (disables a competing OCR app
          # that is still enabled; reports, but does not delete, its leftover
          # Flow rule).
          ${ncPhp}/bin/php ${enforceSingleOwnerPhp} ${ncRoot} ${lib.concatStringsSep " " competingOcrApps}
          enfRc=$?
          if [ "$regRc" -ne 0 ]; then
            echo "nc-ocr-register-webhook: webhook registration FAILED after 5 attempts" >&2
          fi
          # Leave the unit FAILED (visible in `systemctl --failed`) rather than
          # succeeding while automatic OCR is silently dead.
          [ "$regRc" -eq 0 ] && [ "$enfRc" -eq 0 ]
        '';
      };

      # NOTE: the third-party ``workflow_ocr`` Flow rule that used to be
      # created here (``systemd.services.nextcloud-ocr-flow`` + the now-deleted
      # ``setup-flow.php``) was removed on 2026-10-17. It fired on
      # \OCP\Files::postCreate and \OCP\Files::postWrite — the same events this
      # service listens on — and overwrote this service's text layer on every
      # file. Do not reintroduce a second OCR writer here; see the
      # single-owner note at the top of this module.
    };
  };
}
