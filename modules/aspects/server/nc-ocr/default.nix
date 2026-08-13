{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.nc-ocr = {
    nixos = { config, lib, pkgs, ... }: {
      # tesseract5 with ru+eng traineddata, ocrmypdf, image→pdf helpers
      # tesseract5 ships tessdata in $out/share/tessdata/.
      environment.systemPackages = with pkgs; [
        tesseract5
        ocrmypdf
        img2pdf
        ghostscript
        pngquant
        unpaper
      ];

      # Russian + English OCR language packs (symlinked into /etc/tesseract-ocr/tessdata)
      environment.etc."tesseract-ocr/tessdata/eng.traineddata".source =
        "${pkgs.tesseract5}/share/tessdata/eng.traineddata";
      environment.etc."tesseract-ocr/tessdata/rus.traineddata".source =
        "${pkgs.tesseract5}/share/tessdata/rus.traineddata";

      # MobileNetV2 doc/photo binary classifier (vlad-m-dev/mobilenetv2_doc_photo_quant).
      # ~2.4MB ONNX, verified URL + hash 2026-08-13.
      environment.etc."nc-ocr/mobilenetv2_doc_photo_quant.onnx".source =
        pkgs.fetchurl {
          url = "https://huggingface.co/vlad-m-dev/mobilenetv2_doc_photo_quant/resolve/main/mobilenetv2_doc_photo_quant.onnx";
          sha256 = "sha256-6nmiF0smge6yXo+is3FO150WcwL4LE42VVUB1qW6gbs=";
        };

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
            # Nextcloud stores user files under /tank/nextcloud/data/<user>/files/.
            # "likivik" is the only NC user on this host; multi-user hosts need
            # one watcher per user or recursive watch.
            "NC_DATA_DIR=/tank/nextcloud/data/likivik/files"
            "NC_WATCH_DIRS=/Documents,/Inbox,/Scans"
            "NC_OCR_FAILED_DIR=/var/lib/nc-ocr/failed"
            "NC_OCR_SIDECAR_DIR=/var/lib/nc-ocr/sidecars"
            "NC_OCR_OLMOCR_ENDPOINT=http://serenity:8083"
            "NC_OCR_MODEL_PATH=/etc/nc-ocr/mobilenetv2_doc_photo_quant.onnx"
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
