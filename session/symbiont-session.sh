#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  Harmoni X Session
#  Boot flow: Background → Splash (instant) → Openbox → Harmoni → Splash closes
#  Zero flicker. Zero tela preta. Cinematographic transition.
#
#  Optimized boot sequence:
#  - Background set FIRST (< 50ms, prevents any flash)
#  - Splash starts BEFORE Openbox (user sees branded screen immediately)
#  - Openbox starts in parallel (WM ready while splash is visible)
#  - Harmoni loads behind splash (heavy imports hidden)
#  - Splash closes only when GUI is fully rendered
# ═══════════════════════════════════════════════════
set -u

export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
# Disable accessibility bridge (removes startup delay)
export NO_AT_BRIDGE=1
export GTK_A11Y=none

LOGFILE="$HOME/.harmoni/session.log"
mkdir -p "$HOME/.harmoni"
BOOT_START=$(date +%s%N)

echo "=== Harmoni session starting $(date) ===" >> "$LOGFILE"

# ── 0. Ensure critical dependencies are installed ──
_install_if_missing() {
    local missing=""
    for cmd in wmctrl xdotool xrandr xprop; do
        if ! command -v "$cmd" &>/dev/null; then
            missing="$missing $cmd"
        fi
    done
    if [ -n "$missing" ]; then
        echo "Missing tools:$missing — attempting install" >> "$LOGFILE"
        # Map commands to packages
        local pkgs=""
        echo "$missing" | grep -q "wmctrl" && pkgs="$pkgs wmctrl"
        echo "$missing" | grep -q "xdotool" && pkgs="$pkgs xdotool"
        echo "$missing" | grep -q "xrandr" && pkgs="$pkgs x11-xserver-utils"
        echo "$missing" | grep -q "xprop" && pkgs="$pkgs x11-utils"
        if [ -n "$pkgs" ]; then
            pkexec apt-get install -y -qq $pkgs >> "$LOGFILE" 2>&1 || \
            sudo -n apt-get install -y -qq $pkgs >> "$LOGFILE" 2>&1 || \
            echo "Could not auto-install:$pkgs" >> "$LOGFILE"
        fi
    fi
}
_install_if_missing

# ── 0.5. Ensure XDG user directories exist ──
_ensure_user_dirs() {
    local dirs=(
        "$HOME/Desktop"
        "$HOME/Documents"
        "$HOME/Downloads"
        "$HOME/Music"
        "$HOME/Pictures"
        "$HOME/Pictures/Screenshots"
        "$HOME/Videos"
        "$HOME/Videos/Recordings"
        "$HOME/Templates"
        "$HOME/Public"
    )
    for d in "${dirs[@]}"; do
        mkdir -p "$d" 2>/dev/null
    done

    # Create user-dirs.dirs config if missing
    local config_dir="${XDG_CONFIG_HOME:-$HOME/.config}"
    local user_dirs_file="$config_dir/user-dirs.dirs"
    if [ ! -f "$user_dirs_file" ]; then
        mkdir -p "$config_dir"
        cat > "$user_dirs_file" << 'EOF'
XDG_DESKTOP_DIR="$HOME/Desktop"
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_TEMPLATES_DIR="$HOME/Templates"
XDG_PUBLICSHARE_DIR="$HOME/Public"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="$HOME/Music"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_VIDEOS_DIR="$HOME/Videos"
EOF
        echo "Created user-dirs.dirs" >> "$LOGFILE"
    fi
}
_ensure_user_dirs

# ── 1. Set background IMMEDIATELY (< 50ms, prevents ANY flash) ──
xsetroot -solid '#0a0a0f' 2>/dev/null || true
xsetroot -cursor_name left_ptr 2>/dev/null || true

# ── 2. Find Python ──
VENV="/usr/share/harmoni/.venv/bin/python3"
if [ ! -x "$VENV" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    if [ -x "$(dirname "$SCRIPT_DIR")/.venv/bin/python3" ]; then
        VENV="$(dirname "$SCRIPT_DIR")/.venv/bin/python3"
    else
        VENV="python3"
    fi
fi

# Ensure harmoni module is findable
export PYTHONPATH="/usr/share/harmoni:${PYTHONPATH:-}"

# ── 3. Show splash BEFORE Openbox (user sees brand instantly) ──
$VENV -m harmoni.splash &
SPLASH_PID=$!
echo "Splash started (PID $SPLASH_PID)" >> "$LOGFILE"

# ── 4. Start Openbox in parallel (WM loads while splash is visible) ──
OPENBOX_CONF="${XDG_CONFIG_HOME}/openbox-harmoni"
mkdir -p "${OPENBOX_CONF}" 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/usr/share/harmoni"

if [ -f "${INSTALL_DIR}/session/rc.xml" ]; then
    SRC_DIR="${INSTALL_DIR}/session"
else
    SRC_DIR="${SCRIPT_DIR}"
fi

[ ! -f "${OPENBOX_CONF}/rc.xml" ] && cp "${SRC_DIR}/rc.xml" "${OPENBOX_CONF}/rc.xml" 2>/dev/null || true

# Start dbus if needed
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    eval "$(dbus-launch --sh-syntax)"
    export DBUS_SESSION_BUS_ADDRESS
fi

openbox --config-file "${OPENBOX_CONF}/rc.xml" &
OPENBOX_PID=$!
echo "Openbox started (PID $OPENBOX_PID)" >> "$LOGFILE"

# No sleep needed — splash is already visible, Openbox loads in background

# ── 5. Start Harmoni (main app) ──
# The app writes progress to ~/.harmoni/.splash_progress
# and creates ~/.harmoni/.splash_done when GUI is fully rendered
CRASH_COUNT=0

while true; do
    BOOT_END=$(date +%s%N)
    BOOT_MS=$(( (BOOT_END - BOOT_START) / 1000000 ))
    echo "Starting Harmoni with $VENV at $(date) (${BOOT_MS}ms since session start)" >> "$LOGFILE"

    $VENV -m harmoni.main >> "$LOGFILE" 2>&1
    EXIT_CODE=$?
    echo "Harmoni exited with code $EXIT_CODE at $(date)" >> "$LOGFILE"

    # Kill splash if still running (safety)
    kill $SPLASH_PID 2>/dev/null || true

    if [ $EXIT_CODE -eq 0 ]; then
        break
    fi

    # Crash — restart with splash
    CRASH_COUNT=$((CRASH_COUNT + 1))
    echo "Crash #$CRASH_COUNT detected" >> "$LOGFILE"

    if [ $CRASH_COUNT -ge 3 ]; then
        echo "Too many crashes, opening terminal for debug" >> "$LOGFILE"
        xterm -e "echo 'Harmoni crashed 3x. Check ~/.harmoni/session.log'; tail -30 $LOGFILE; echo; bash" &
        wait
        break
    fi

    # Show splash again during restart
    $VENV -m harmoni.splash &
    SPLASH_PID=$!
    sleep 1
done

# ── 6. Cleanup ──
kill $OPENBOX_PID 2>/dev/null || true
echo "=== Session ended $(date) ===" >> "$LOGFILE"
