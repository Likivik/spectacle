{ ipmitool, writeShellScriptBin, bmcUserFile, bmcPasswordFile }:

# Remote power control for the PowerEdge T110 II BMC (WPCM450, firmware 1.80).
#
# Two things are pinned on purpose:
#   * -C 3 — the BMC is configured to refuse every other RMCP+ cipher suite
#     (0 = no authentication at all, 1/2/6/7/11 = plaintext, 4/5/9/10 = RC4,
#     8 = MD5+AES, 12-14 unimplemented). Any call without -C 3 fails with
#     "no matching cipher suite".
#   * -E — ipmitool reads the password from $IPMI_PASSWORD instead of argv, so
#     it never shows up in `ps` for other local users.
#
# Credentials come from sops at activation time; their paths are baked in by
# the host module, so this script carries no secret material.
writeShellScriptBin "poweredge-power" ''
  set -euo pipefail

  host="''${PEDGE_BMC_HOST:-192.168.0.120}"
  action="''${1:-status}"

  user="$(cat ${bmcUserFile})"
  IPMI_PASSWORD="$(cat ${bmcPasswordFile})"
  export IPMI_PASSWORD

  ipmi() {
    ${ipmitool}/bin/ipmitool -I lanplus -C 3 -H "$host" -U "$user" -E "$@"
  }

  case "$action" in
    status|on|off|cycle|soft|reset)
      ipmi chassis power "$action"
      ;;
    sensors)
      ipmi sdr
      ;;
    *)
      echo "usage: poweredge-power status|on|off|cycle|soft|reset|sensors" >&2
      exit 2
      ;;
  esac
''
