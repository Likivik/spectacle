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
        *"launcher toggle")              echo "Launcher" ;;
        *"spotlight toggle")             echo "Spotlight" ;;
        *"clipboard toggle")             echo "Clipboard" ;;
        *"settings focusOrToggle")       echo "Settings" ;;
        *"notifications toggle")         echo "Notifications" ;;
        *"processlist focusOrToggle")    echo "Task Manager" ;;
        *"keybinds toggle"*)             echo "Keybinds" ;;
        *"dankdash wallpaper")           echo "Wallpapers" ;;
        *"lock lock")                    echo "Lock Screen" ;;
        *"audio increment")              echo "Volume Up" ;;
        *"audio decrement")              echo "Volume Down" ;;
        *"audio mute")                   echo "Mute" ;;
        *"audio micmute")                echo "Mic Mute" ;;
        *"brightness increment")         echo "Brightness Up" ;;
        *"brightness decrement")         echo "Brightness Down" ;;
        *"mpris playPause")              echo "Play/Pause" ;;
        *"mpris next")                   echo "Next Track" ;;
        *"mpris previous")               echo "Previous Track" ;;
        *"switch-layout")                echo "Switch Layout" ;;

        # Native niri actions
        "focus-column-left")             echo "Focus Left" ;;
        "focus-column-right")            echo "Focus Right" ;;
        "focus-window-or-workspace-up")  echo "Focus Up" ;;
        "focus-window-or-workspace-down") echo "Focus Down" ;;
        "move-column-left")              echo "Move Left" ;;
        "move-column-right")             echo "Move Right" ;;
        "move-window-up")                echo "Move Up" ;;
        "move-window-down")              echo "Move Down" ;;
        "close-window")                  echo "Close Window" ;;
        "fullscreen-window")             echo "Fullscreen" ;;
        "toggle-window-floating")        echo "Toggle Float" ;;
        "toggle-column-tabbed-display")  echo "Toggle Tabbed" ;;
        "switch-preset-column-width")    echo "Cycle Width" ;;
        "switch-preset-window-height")   echo "Cycle Height" ;;
        "center-column")                 echo "Center Column" ;;
        "center-visible-columns")        echo "Center All" ;;
        "set-column-width")              echo "Resize Column" ;;
        "set-window-height")             echo "Resize Window" ;;
        "focus-workspace")               echo "Focus Workspace" ;;
        "move-column-to-workspace")      echo "Move to Workspace" ;;
        "toggle-overview")               echo "Overview" ;;
        "focus-monitor-left")            echo "Focus Monitor L" ;;
        "focus-monitor-right")           echo "Focus Monitor R" ;;
        "move-column-to-monitor-left")   echo "Move to Monitor L" ;;
        "move-column-to-monitor-right")  echo "Move to Monitor R" ;;
        "toggle-keyboard-shortcuts-inhibit") echo "Escape" ;;
        "quit")                          echo "Quit" ;;
        "power-off-monitors")            echo "Power Off" ;;
        "screenshot")                    echo "Screenshot" ;;
        "screenshot-window")             echo "Screenshot Window" ;;
        *)                               echo "$1" ;;
    esac
}

annotate 60 110 "$FG_SECTION" 22 "Keybinds"
yc=160

while IFS= read -r line; do
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$line" ]] && continue
    [[ "$line" == //* ]] && continue
    [[ "$line" == "binds"* ]] && continue
    [[ "$line" == "}"* ]] && continue

    read -ra parts <<< "$line"
    key="${parts[0]}"
    [[ -z "$key" ]] && continue

    # Skip media/hardware keys — they have dedicated keys
    [[ "$key" == XF86* ]] && continue

    # Skip non-bind lines (include, layout, input, etc.)
    [[ ${#parts[@]} -lt 3 ]] && continue
    [[ "${parts[1]}" != "{" ]] && continue

    if [[ "${parts[2]}" == "spawn" ]]; then
        cmd=""
        for ((i = 3; i < ${#parts[@]}; i++)); do
            arg="${parts[$i]}"
            arg="${arg#\"}"; arg="${arg%\";}"; arg="${arg%\"}"
            [[ -n "$arg" ]] && cmd="$cmd $arg"
        done
        cmd="${cmd# }"
    elif [[ "${parts[2]}" == "spawn-sh" ]]; then
        if [[ "$line" =~ spawn-sh\ \"(.*)\"\; ]]; then
            cmd="${BASH_REMATCH[1]}"
        else
            cmd=""
        fi
    else
        # Native niri action
        cmd="${parts[2]}"
        cmd="${cmd%;}"
    fi

    [[ -z "$cmd" ]] && continue

    desc=$(describe "$cmd")
    annotate 60 "$yc" "$FG_KEY" 18 "$key"
    annotate 340 "$yc" "$FG_DESC" 18 "$desc"
    yc=$((yc + 36))

done < <(cat "$KDL" "$HERE/../niri/dms/binds.kdl")

magick "${args[@]}" "$OUTPUT"
