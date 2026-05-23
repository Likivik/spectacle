#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
KDL="$HERE/../niri/config.kdl"
OUTPUT="$HERE/wallpapers/keybinds.png"

mkdir -p "$(dirname "$OUTPUT")"

FONT="${FONT_PATH:-Iosevka}"
BG="#1a1a2e"
FG_TITLE="#ffffff"
FG_SECTION="#f0c060"
FG_KEY="#7ec8e3"
FG_DESC="#e0e0e0"

W=1920
H=1080

args=(-size "${W}x${H}" xc:"$BG" -font "$FONT")

annotate() {
    local x=$1 y=$2 fill=$3 size=$4 text=$5
    args+=(-pointsize "$size" -fill "$fill" -annotate "+${x}+${y}" "$text")
}

annotate 60 50 "$FG_TITLE" 36 "Noctalia Keybinds"

describe() {
    case "$1" in
        *"panel-toggle launcher")        echo "Toggle Launcher" ;;
        *"panel-toggle control-center")  echo "Control Center" ;;
        *"panel-toggle clipboard")       echo "Clipboard" ;;
        *"panel-toggle session")         echo "Session Menu" ;;
        *"settings-toggle")              echo "Settings" ;;
        *"screen-lock")                  echo "Lock Screen" ;;
        *"theme-mode-toggle")            echo "Toggle Theme" ;;
        *"dock-toggle")                  echo "Toggle Dock" ;;
        *"notification-dnd-toggle")      echo "Do Not Disturb" ;;
        *"volume-up")                    echo "Volume Up" ;;
        *"volume-down")                  echo "Volume Down" ;;
        *"volume-mute")                  echo "Mute" ;;
        *"brightness-up")                echo "Brightness Up" ;;
        *"brightness-down")              echo "Brightness Down" ;;
        *)                               echo "$1" ;;
    esac
}

annotate 60 110 "$FG_SECTION" 22 "Core"
yc=160

annotate 1020 110 "$FG_SECTION" 22 "Media"
ym=160

while IFS= read -r line; do
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$line" ]] && continue
    [[ "$line" == //* ]] && continue
    [[ "$line" == "binds"* ]] && continue
    [[ "$line" == "}"* ]] && continue

    read -ra parts <<< "$line"
    key="${parts[0]}"
    [[ -z "$key" ]] && continue

    if [[ "$line" =~ spawn-sh\ \"(.*)\"\; ]]; then
        cmd="${BASH_REMATCH[1]}"
    else
        cmd=""
        for ((i = 3; i < ${#parts[@]}; i++)); do
            arg="${parts[$i]}"
            arg="${arg#\"}"; arg="${arg%\";}"; arg="${arg%\"}"
            [[ -n "$arg" ]] && cmd="$cmd $arg"
        done
        cmd="${cmd# }"
    fi

    [[ -z "$cmd" ]] && continue

    desc=$(describe "$cmd")

    if [[ "$key" == XF86* ]]; then
        annotate 1020 "$ym" "$FG_KEY" 18 "$key"
        annotate 1360 "$ym" "$FG_DESC" 18 "$desc"
        ym=$((ym + 36))
    else
        annotate 60 "$yc" "$FG_KEY" 18 "$key"
        annotate 340 "$yc" "$FG_DESC" 18 "$desc"
        yc=$((yc + 36))
    fi
done < "$KDL"

magick "${args[@]}" "$OUTPUT"
