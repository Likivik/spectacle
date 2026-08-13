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
    };
  };
}
