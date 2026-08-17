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
        if [ ! -d "${suryaVenv}" ] || [ ! -f "${suryaVenv}/.installed" ] || [ "${suryaVenv}/.installed" -ot "${ncOcrFlowSrc}/src/nc_ocr_flow/surya_server.py" ]; then
          echo "Creating Surya venv..."
          ${pkgs.python312}/bin/python3.12 -m venv ${suryaVenv}
          ${suryaVenv}/bin/pip install --no-cache-dir surya-ocr fastapi uvicorn pydantic pymupdf requests
          touch ${suryaVenv}/.installed
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

        path = [
          pkgs.python312
          pkgs.gcc
          pkgs.cudaPackages.cudatoolkit
          pkgs.stdenv.cc.cc.lib
          pkgs.llama-cpp
        ];

        environment = {
          PORT = "8084";
          LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";
          SURYA_INFERENCE_BACKEND = "llamacpp";
          SURYA_INFERENCE_KEEP_ALIVE = "1";
          SURYA_INFERENCE_AUTOSTART = "1";
        };

        serviceConfig = {
          Type = "simple";
          Restart = "on-failure";
          RestartSec = "10s";
          StateDirectory = "surya-server";
          StateDirectoryMode = "0755";
          User = "nobody";
          Group = "nogroup";
          Environment = [
            "CUDA_VISIBLE_DEVICES=0"
            "HF_HOME=/var/lib/surya-server/hf-cache"
            "HOME=/var/lib/surya-server"
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
