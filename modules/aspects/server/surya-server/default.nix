{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.surya-server = {
    nixos = { config, lib, pkgs, ... }:

    let
      suryaVenv = "/var/lib/surya-server/venv";

      # Don't build ncOcrFlow as a nix package — surya_server.py only needs
      # pymupdf + pillow + requests, all provided by the venv (surya-ocr pulls
      # pillow). We just point PYTHONPATH at the source tree.
      ncOcrFlowSrc = ../../../../pkgs/nc-ocr-flow/src;

      suryaStartScript = pkgs.writeShellScript "surya-server-start" ''
        set -eu
        if [ ! -d "${suryaVenv}" ]; then
          echo "Creating Surya venv..."
          ${pkgs.python312}/bin/python3.12 -m venv ${suryaVenv}
          ${suryaVenv}/bin/pip install --no-cache-dir surya-ocr fastapi uvicorn pydantic pymupdf requests
        fi
        export PYTHONPATH="${ncOcrFlowSrc}:''${PYTHONPATH:-}"
        exec ${suryaVenv}/bin/python -m nc_ocr_flow.surya_server
      '';
    in {
      systemd.tmpfiles.rules = [
        "d /var/lib/surya-server 0755 nobody nobody -"
      ];

      systemd.services.nc-surya-server = {
        description = "Surya OCR server (GPU, for nc-ocr-flow VLM fallback)";
        after = [ "network.target" ];
        wantedBy = [ "multi-user.target" ];

        environment = {
          PORT = "8084";
        };

        path = [
          pkgs.python312
          pkgs.gcc
          pkgs.cudaPackages.cudatoolkit
        ];

        serviceConfig = {
          Type = "simple";
          Restart = "on-failure";
          RestartSec = "10s";
          StateDirectory = "surya-server";
          User = "nobody";
          Group = "nogroup";
          DeviceAllow = [ "char-nvidia*" "char-dri*" ];
          PrivateDevices = false;
          Environment = [
            "CUDA_VISIBLE_DEVICES=0"
          ];
          TimeoutStartSec = "10min";
        };

        script = ''
          exec ${suryaStartScript}
        '';
      };

      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 8084 ];
    };
  };
}
