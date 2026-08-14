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
      # The NixOS nextcloud module builds an extended PHP (with redis, apcu, etc.)
      # as a local let-binding and assigns it to the phpfpm pool. Access it there.
      ncPhp = config.services.phpfpm.pools.nextcloud.phpPackage;

      # PHP script to create the flow rule — kept as a separate file to avoid
      # Nix string escaping nightmares with single quotes and backslashes.
      setupFlowPhp = ./setup-flow.php;
    in {
      environment.systemPackages = [
        pkgs.ocrmypdf
        pkgs.tesseract5
        pkgs.poppler-utils
      ];

      systemd.services.nextcloud-cron.path = lib.mkAfter [
        pkgs.ocrmypdf
        pkgs.tesseract5
      ];

      systemd.services.nextcloud-setup.path = lib.mkAfter [
        pkgs.ocrmypdf
        pkgs.tesseract5
      ];

      services.nextcloud.extraApps = { workflow_ocr = workflowOcr; };
      services.nextcloud.extraAppsEnable = true;
      services.nextcloud.appstoreEnable = lib.mkForce false;

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
          LoadCredential = [
            "adminpass:/run/secrets/nextcloud/admin-password"
            "mail_smtppassword:/run/secrets/resend/api-key"
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
