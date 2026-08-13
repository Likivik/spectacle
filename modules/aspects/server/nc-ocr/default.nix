{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.nc-ocr = {
    nixos = { config, lib, pkgs, ... }: {
      # tesseract5 with ru+eng traineddata, ocrmypdf, image→pdf helpers
      environment.systemPackages = with pkgs; [
        tesseract5
        tesseract5-traineddata
        ocrmypdf
        img2pdf
        ghostscript
        pngquant
        unpaper
      ];

      # Russian + English OCR language packs (symlinked into /etc/tesseract-ocr/tessdata)
      environment.etc."tesseract-ocr/tessdata/eng.traineddata".source =
        "${pkgs.tesseract5-traineddata}/share/tessdata-5/eng.traineddata";
      environment.etc."tesseract-ocr/tessdata/rus.traineddata".source =
        "${pkgs.tesseract5-traineddata}/share/tessdata-5/rus.traineddata";

      # OCR working dirs (owned by nextcloud user so watcher can write sidecars
      # into NC data dir).
      systemd.tmpfiles.rules = [
        "d /var/lib/nc-ocr 0750 nextcloud nextcloud -"
        "d /var/lib/nc-ocr/failed 0750 nextcloud nextcloud -"
        "d /var/lib/nc-ocr/sidecars 0750 nextcloud nextcloud -"
      ];

      # nc-ocr-flow Python watcher service.
      # Consumes the uv2nix-built package from pkgs/nc-ocr-flow.
      systemd.services.nc-ocr-flow = {
        description = "Nextcloud OCR pipeline watcher";
        after = [ "network-online.target" "nextcloud-setup.service" ];
        wants = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          Type = "simple";
          User = "nextcloud";
          Group = "nextcloud";
          WorkingDirectory = "/var/lib/nc-ocr";
          Restart = "on-failure";
          RestartSec = "5s";
          Environment = [
            "PYTHONUNBUFFERED=1"
            "NC_DATA_DIR=/tank/nextcloud/data"
            "NC_WATCH_DIRS=/Documents,/Inbox,/Scans"
            "NC_OCR_FAILED_DIR=/var/lib/nc-ocr/failed"
            "NC_OCR_SIDECAR_DIR=/var/lib/nc-ocr/sidecars"
            "NC_OCR_CLIP_ENDPOINT=http://serenity:8084"
            "NC_OCR_OLMOCR_ENDPOINT=http://serenity:8083"
          ];
          ExecStart = let
            ncOcrFlow = inputs.nc-ocr-flow.packages.${pkgs.system}.nc-ocr-flow or null;
          in if ncOcrFlow != null then
            "${ncOcrFlow}/bin/nc-ocr-flow"
          else
            "${pkgs.python3}/bin/python3 -m nc_ocr_flow";
        };
      };
    };
  };
}
