{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.workflow-ocr = {
    nixos = { config, lib, pkgs, ... }:

    let
      workflowOcr = pkgs.fetchNextcloudApp {
        appName = "workflow_ocr";
        appVersion = "1.34.0";
        license = "agpl3Plus";
        url = "https://github.com/R0Wi-DEV/workflow_ocr/releases/download/v1.34.0/workflow_ocr.tar.gz";
        sha512 = "sha512-sD1KqC7Fp1sRx7td5QFXJNHDknk2ueKd7CsCcGEp473O+oJhBOxXhzG/3MEhxX/qT2tBo5Z3h4QQJXdhSLJA1w==";
      };

      ncRoot = config.services.nextcloud.finalPackage;
      ncPhp = config.services.phpfpm.pools.nextcloud.phpPackage;
      setupFlowPhp = ./setup-flow.php;

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

      # PHP script to register webhook listeners via NC internal API (idempotent)
      registerWebhookPhp = ./register-webhook.php;
    in {
      environment.systemPackages = [
        pkgs.ocrmypdf
        pkgs.tesseract5
        pkgs.poppler-utils
      ];

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

      systemd.services.nextcloud-cron.path = lib.mkAfter [
        pkgs.ocrmypdf
        pkgs.tesseract5
      ];

      systemd.services.nextcloud-setup.path = lib.mkAfter [
        pkgs.ocrmypdf
        pkgs.tesseract5
      ];

      # --- OCR Flow app: context-menu action → nc-ocr-flow webhook ---
      # Install as a raw app directory (nix-built, no fetchNextcloudApp —
      # the app is ours, built from this repo).
      services.nextcloud.extraApps = {
        workflow_ocr = workflowOcr;
        # Nix-built app dir (appinfo/info.xml at store root — same shape as
        # fetchNextcloudApp output)
        ocrflow = pkgs.callPackage ../../../../pkgs/ocrflow-ncapp { };
      };
      services.nextcloud.extraAppsEnable = true;
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
        after = [ "nextcloud-setup.service" "nc-ocr-webhook.service" ];
        wants = [ "nextcloud-setup.service" "nc-ocr-webhook.service" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          Type = "oneshot";
          User = "nextcloud";
          Group = "nextcloud";
          RemainAfterExit = true;
          LoadCredential = let
            adminPass = config.sops.secrets."nextcloud/admin-password".path;
            resendKey = config.sops.secrets."resend/api-key".path;
            webhookSecret = config.sops.secrets."nextcloud/ocr-webhook-secret".path;
          in [
            "adminpass:${adminPass}"
            "mail_smtppassword:${resendKey}"
            "nc-ocr-webhook-secret:${webhookSecret}"
          ];
        };

        environment = {
          NEXTCLOUD_CONFIG_DIR = lib.mkForce "/tank/nextcloud/config";
        };

        path = [ ncPhp ];

        script = ''
          ${ncPhp}/bin/php ${registerWebhookPhp} ${ncRoot} "$CREDENTIALS_DIRECTORY/nc-ocr-webhook-secret"
        '';
      };

      # Declarative flow rule: idempotently insert OCR workflow rule after setup.
      systemd.services.nextcloud-ocr-flow = {
        description = "Create declarative OCR workflow rule";
        after = [ "nextcloud-setup.service" ];
        wants = [ "nextcloud-setup.service" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          Type = "oneshot";
          User = "nextcloud";
          Group = "nextcloud";
          RemainAfterExit = true;
          LoadCredential = let
            adminPass = config.sops.secrets."nextcloud/admin-password".path;
            resendKey = config.sops.secrets."resend/api-key".path;
          in [
            "adminpass:${adminPass}"
            "mail_smtppassword:${resendKey}"
          ];
        };

        environment = {
          NEXTCLOUD_CONFIG_DIR = lib.mkForce "/tank/nextcloud/config";
        };

        path = [ ncPhp ];

        script = ''
          ${ncPhp}/bin/php ${setupFlowPhp} ${ncRoot}
        '';
      };
    };
  };
}
