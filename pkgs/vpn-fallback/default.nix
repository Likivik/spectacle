{ writeShellApplication
, runCommand
, coreutils
, gnugrep
, procps
, sudo
, systemd
, byedpi
}:

let
  mainProgram = writeShellApplication {
    name = "vpn-fallback";
    runtimeInputs = [
      coreutils
      gnugrep
      procps
      sudo
      systemd
      byedpi
    ];
    text = builtins.readFile ./vpn-fallback.sh;
  };
in
runCommand "vpn-fallback" { } ''
  mkdir -p $out/bin $out/share/bash-completion/completions
  cp ${mainProgram}/bin/vpn-fallback $out/bin/vpn-fallback
  cp ${./completion.bash} $out/share/bash-completion/completions/vpn-fallback
''
