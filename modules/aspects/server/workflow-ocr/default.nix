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
      ocrVenv = "/var/lib/nc-ocr/venv";

      # Start script: create venv with pip if missing, then run webhook server
      webhookStartScript = pkgs.writeShellScript "nc-ocr-webhook-start" ''
        set -eu
        export NC_OCR_NC_PASSWORD_FILE="$CREDENTIALS_DIRECTORY/nc-ocr-password"
        export NC_OCR_WEBHOOK_SECRET_FILE="$CREDENTIALS_DIRECTORY/nc-ocr-webhook-secret"
        export NC_OCR_MINIMAX_KEY_FILE="$CREDENTIALS_DIRECTORY/minimax-api-key"
        if [ ! -d "${ocrVenv}" ] || [ ! -f "${ocrVenv}/.installed" ] || [ "${ocrVenv}/.installed" -ot "${ncOcrFlowSrc}/src/nc_ocr_flow/webhook_server.py" ] || [ "${ocrVenv}/.installed" -ot "${ncOcrFlowSrc}/src/nc_ocr_flow/ocr.py" ]; then
          echo "Creating OCR venv..."
          rm -rf "${ocrVenv}"
          ${pkgs.python312}/bin/python3.12 -m venv ${ocrVenv}
          ${ocrVenv}/bin/pip install --no-cache-dir pymupdf pillow requests img2pdf numpy onnxruntime fastapi uvicorn pydantic
          ${ocrVenv}/bin/pip install --no-cache-dir --no-deps ${ncOcrFlowSrc}
          touch ${ocrVenv}/.installed
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
        description = "Nextcloud OCR webhook receiver (tesseract + Surya fallback)";
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
          NC_OCR_SURYA_URL = "http://serenity:8084";
          # VLM backend: minimax (MiniMax-M3 vision) | surya. Default minimax.
          NC_OCR_VLM_BACKEND = "minimax";
          NC_OCR_LISTEN_HOST = "127.0.0.1";
          NC_OCR_LISTEN_PORT = "8095";
          NC_OCR_FONT_PATH = "${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSans.ttf";
          TESSDATA_PREFIX = "${pkgs.tesseract5}/share/tessdata";
          LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";
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
            minimaxKey = config.sops.secrets."nextcloud/minimax-api-key".path;
          in [
            "nc-ocr-password:${webdavPass}"
            "nc-ocr-webhook-secret:${webhookSecret}"
            "minimax-api-key:${minimaxKey}"
          ];
        };

        path = [
          pkgs.ocrmypdf
          pkgs.tesseract5
          pkgs.poppler-utils
          pkgs.curl
          pkgs.stdenv.cc.cc.lib
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
