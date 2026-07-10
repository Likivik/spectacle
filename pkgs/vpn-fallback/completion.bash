_vpn_fallback() {
  local cur prev words cword
  _init_completion || return

  local tools="zapret byedpi v2ray"
  local actions="on off status logs"

  if [[ $cword -eq 1 ]]; then
    COMPREPLY=($(compgen -W "status help $tools" -- "$cur"))
  elif [[ $cword -eq 2 ]]; then
    case "${words[1]}" in
      zapret|byedpi|v2ray)
        COMPREPLY=($(compgen -W "$actions" -- "$cur"))
        ;;
    esac
  fi
} &&
complete -F _vpn_fallback vpn-fallback
