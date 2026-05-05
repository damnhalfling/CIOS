#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  Harmoni — Build .deb package
#  Usage: bash build-deb.sh [VERSION]
#  Example: bash build-deb.sh 0.3.0
# ═══════════════════════════════════════════════════
set -euo pipefail

VERSION="${1:-0.3.0}"
PKG_NAME="harmoni"
PKG_DIR="${PKG_NAME}_${VERSION}_amd64"
INSTALL_DIR="/usr/share/harmoni"

echo "╔═══════════════════════════════════════════╗"
echo "║  Harmoni — Building .deb v${VERSION}          ║"
echo "╚═══════════════════════════════════════════╝"

# ── Clean previous build ──
rm -rf "${PKG_DIR}" "${PKG_DIR}.deb"

# ── Create directory structure ──
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/harmoni/core"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/harmoni/ui"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/harmoni/infra"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/harmoni/skills"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/assets"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/config"
mkdir -p "${PKG_DIR}/usr/local/bin"
mkdir -p "${PKG_DIR}/usr/share/xsessions"
mkdir -p "${PKG_DIR}/usr/share/backgrounds"
mkdir -p "${PKG_DIR}/etc/xdg/openbox-harmoni"

# ── DEBIAN/control ──
cat > "${PKG_DIR}/DEBIAN/control" << EOF
Package: harmoni
Version: ${VERSION}
Section: x11
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10), python3-pip, python3-venv, python3-tk, openbox, wmctrl, xdotool, x11-xserver-utils, curl
Recommends: pipewire-pulse | pulseaudio-utils, network-manager, i3lock
Suggests: lightdm, slick-greeter
Maintainer: damnhalfling <damnhalfling@github.com>
Description: Harmoni OS — AI-first desktop interface
 A AI-first layer that replaces apps with intent-driven
 execution on top of Linux. Speak intent, get results.
 .
 Can be installed as an additional X session alongside
 GNOME/KDE, or as the default desktop with custom login.
Homepage: https://github.com/damnhalfling/harmoni
EOF

# ── DEBIAN/preinst (clean previous version) ──
cat > "${PKG_DIR}/DEBIAN/preinst" << 'PREINST'
#!/bin/bash
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

# ── Remove previous version if installed ──
if dpkg -s harmoni >/dev/null 2>&1; then
    PREV_VER=$(dpkg-query -W -f='${Version}' harmoni 2>/dev/null || echo "unknown")
    echo "[Harmoni] Previous version detected: ${PREV_VER}"
    echo "[Harmoni] Cleaning up before upgrade..."

    # Stop daemon if running (socket only, not the session)
    if [ -f /tmp/harmoni.sock ]; then
        echo '{"command":"shutdown"}' | socat - UNIX-CONNECT:/tmp/harmoni.sock 2>/dev/null || true
        sleep 0.5
    fi

    # NOTE: Do NOT kill harmoni-session or harmoni.main here!
    # The user might be running dpkg -i from within the Harmoni session itself.
    # Killing those processes would terminate the X session and log out the user.

    # Remove old venv (will be recreated by postinst)
    if [ -d /usr/share/harmoni/.venv ]; then
        echo "[Harmoni] Removing old virtual environment..."
        rm -rf /usr/share/harmoni/.venv
    fi

    # Remove old .pyc caches
    find /usr/share/harmoni -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    echo "[Harmoni] Cleanup complete."
fi

exit 0
PREINST
chmod 755 "${PKG_DIR}/DEBIAN/preinst"

# ── DEBIAN/postinst ──
cat > "${PKG_DIR}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
# Harmoni postinst — MUST NOT restart any services or ask questions.
# dpkg -i must complete without side effects on the running session.
# All interactive setup (Ollama, LightDM mode) happens via: harmoni --setup
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║       Harmoni OS — Installed             ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# ── Create Python venv + install deps ──
echo "[Harmoni] Setting up Python environment..."
if [ ! -d /usr/share/harmoni/.venv ]; then
    python3 -m venv /usr/share/harmoni/.venv 2>/dev/null || {
        echo "[Harmoni] ⚠ Could not create venv. Will use system Python."
        pip3 install --quiet --break-system-packages \
            boto3==1.35.86 prompt_toolkit==3.0.48 rich==13.9.4 psutil==6.1.1 2>/dev/null || true
    }
fi

if [ -d /usr/share/harmoni/.venv ]; then
    /usr/share/harmoni/.venv/bin/pip install --quiet \
        boto3==1.35.86 \
        prompt_toolkit==3.0.48 \
        rich==13.9.4 \
        psutil==6.1.1 2>/dev/null || true

    /usr/share/harmoni/.venv/bin/pip install --quiet -e /usr/share/harmoni 2>/dev/null || true
fi

chmod +x /usr/local/bin/harmoni-session 2>/dev/null || true

echo "[Harmoni] ✓ Python environment ready"
echo ""
echo "═══════════════════════════════════════════"
echo "  Installation complete!"
echo ""
echo "  → Select 'Harmoni OS' at your login screen."
echo "  → Or run: harmoni --setup (for LightDM/Ollama config)"
echo ""
echo "  Reboot to start: sudo reboot"
echo "═══════════════════════════════════════════"
echo ""

# Never fail
exit 0
POSTINST
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

# ── DEBIAN/prerm ──
cat > "${PKG_DIR}/DEBIAN/prerm" << 'PRERM'
#!/bin/bash
set -e
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

echo "[Harmoni] Removing..."

# Restore original display manager if we changed it
if [ -f /etc/X11/default-display-manager.bak.harmoni ]; then
    cp /etc/X11/default-display-manager.bak.harmoni /etc/X11/default-display-manager
    rm -f /etc/X11/default-display-manager.bak.harmoni
    echo "[Harmoni] Restored original display manager"
fi

# Restore LightDM configs if we changed them
if [ -f /etc/lightdm/lightdm.conf.bak.harmoni ]; then
    mv /etc/lightdm/lightdm.conf.bak.harmoni /etc/lightdm/lightdm.conf
fi
if [ -f /etc/lightdm/slick-greeter.conf.bak.harmoni ]; then
    mv /etc/lightdm/slick-greeter.conf.bak.harmoni /etc/lightdm/slick-greeter.conf
fi
if [ -f /etc/lightdm/lightdm-gtk-greeter.conf.bak.harmoni ]; then
    mv /etc/lightdm/lightdm-gtk-greeter.conf.bak.harmoni /etc/lightdm/lightdm-gtk-greeter.conf
fi

# Clean venv
rm -rf /usr/share/harmoni/.venv

echo "[Harmoni] Removed."
PRERM
chmod 755 "${PKG_DIR}/DEBIAN/prerm"

# ── App files ──
echo "→ Copying application files..."

# Core Python modules
cp pyproject.toml "${PKG_DIR}${INSTALL_DIR}/"
cp -r harmoni/*.py "${PKG_DIR}${INSTALL_DIR}/harmoni/"
cp -r harmoni/core/*.py "${PKG_DIR}${INSTALL_DIR}/harmoni/core/"
cp -r harmoni/ui/*.py "${PKG_DIR}${INSTALL_DIR}/harmoni/ui/"
cp -r harmoni/infra/*.py "${PKG_DIR}${INSTALL_DIR}/harmoni/infra/"
cp -r harmoni/skills/*.py "${PKG_DIR}${INSTALL_DIR}/harmoni/skills/"

# ── Session files ──
echo "→ Copying session files..."

# Session script
cat > "${PKG_DIR}/usr/local/bin/harmoni-session" << 'SESSION'
#!/bin/bash
# Harmoni X Session — optimized boot
# Zero flicker. Splash with real progress. Crash recovery.

export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export NO_AT_BRIDGE=1
export GTK_A11Y=none

LOGFILE="$HOME/.harmoni/session.log"
mkdir -p "$HOME/.harmoni"

echo "=== Harmoni session starting $(date) ===" >> "$LOGFILE"

# Set background IMMEDIATELY (prevents any flash)
xsetroot -solid '#0a0a0f' 2>/dev/null || true
xsetroot -cursor_name left_ptr 2>/dev/null || true

# Find Python
VENV="/usr/share/harmoni/.venv/bin/python3"
if [ ! -x "$VENV" ]; then
    VENV="python3"
fi

# Ensure harmoni module is findable
export PYTHONPATH="/usr/share/harmoni:${PYTHONPATH:-}"

# Show splash BEFORE Openbox (user sees brand instantly)
$VENV -m harmoni.splash &
SPLASH_PID=$!

# Start Openbox in parallel
OPENBOX_CONF="/etc/xdg/openbox-harmoni"
if command -v openbox &>/dev/null; then
    openbox --config-file "${OPENBOX_CONF}/rc.xml" &
    echo "Openbox started (PID $!)" >> "$LOGFILE"
else
    echo "WARNING: openbox not found" >> "$LOGFILE"
fi

# Start Harmoni (crash recovery loop)
CRASH_COUNT=0
while true; do
    echo "Starting Harmoni at $(date)" >> "$LOGFILE"
    $VENV -m harmoni.main >> "$LOGFILE" 2>&1
    EXIT_CODE=$?
    echo "Harmoni exited with code $EXIT_CODE at $(date)" >> "$LOGFILE"

    kill $SPLASH_PID 2>/dev/null || true

    if [ $EXIT_CODE -eq 0 ]; then
        break
    fi

    CRASH_COUNT=$((CRASH_COUNT + 1))
    if [ $CRASH_COUNT -ge 3 ]; then
        echo "Too many crashes, opening terminal" >> "$LOGFILE"
        xterm -e "echo 'Harmoni crashed 3x. Check ~/.harmoni/session.log'; tail -30 $LOGFILE; echo; bash" &
        wait
        break
    fi

    $VENV -m harmoni.splash &
    SPLASH_PID=$!
    sleep 1
done

echo "=== Session ended $(date) ===" >> "$LOGFILE"
SESSION
chmod 755 "${PKG_DIR}/usr/local/bin/harmoni-session"

# X session desktop entry
cat > "${PKG_DIR}/usr/share/xsessions/harmoni.desktop" << 'XSESSION'
[Desktop Entry]
Name=Harmoni OS
Comment=AI-first desktop interface
Exec=/usr/local/bin/harmoni-session
Type=Application
DesktopNames=Harmoni
XSESSION

# Openbox config
cp session/rc.xml "${PKG_DIR}/etc/xdg/openbox-harmoni/rc.xml"

# Openbox autostart (fallback)
cat > "${PKG_DIR}/etc/xdg/openbox-harmoni/autostart" << 'AUTOSTART'
#!/bin/bash
# Fallback autostart — used if session script doesn't handle it
xsetroot -solid '#0a0a0f' 2>/dev/null || true
export NO_AT_BRIDGE=1
export GTK_A11Y=none
export PYTHONPATH="/usr/share/harmoni:${PYTHONPATH:-}"
VENV="/usr/share/harmoni/.venv/bin/python3"
[ ! -x "$VENV" ] && VENV="python3"
$VENV -m harmoni.splash &
$VENV -m harmoni.main &
AUTOSTART
chmod 755 "${PKG_DIR}/etc/xdg/openbox-harmoni/autostart"

# ── LightDM config (bundled, applied only in full replacement mode) ──
echo "→ Bundling LightDM configs..."

cat > "${PKG_DIR}${INSTALL_DIR}/config/lightdm.conf" << 'LIGHTDM'
[Seat:*]
greeter-session=slick-greeter
user-session=harmoni
greeter-hide-users=false
allow-guest=false
LIGHTDM

cat > "${PKG_DIR}${INSTALL_DIR}/config/slick-greeter.conf" << 'GREETER'
[Greeter]
background=/usr/share/backgrounds/harmoni.png
logo=/usr/share/pixmaps/harmoni-logo.png
theme-name=Adwaita-dark
icon-theme-name=Adwaita
draw-grid=false
show-hostname=false
show-power=true
clock-format=%H:%M
GREETER

# ── Logo for LightDM ──
mkdir -p "${PKG_DIR}/usr/share/pixmaps"
if [ -f assets/harmoni_logo.png ]; then
    cp assets/harmoni_logo.png "${PKG_DIR}/usr/share/pixmaps/harmoni-logo.png"
    # Also copy to install dir so the running app can find it
    cp assets/harmoni_logo.png "${PKG_DIR}${INSTALL_DIR}/assets/harmoni_logo.png" 2>/dev/null || true
    echo "→ Harmoni logo bundled for LightDM + GUI"
fi

# ── Background ──
if [ -f assets/background.png ]; then
    cp assets/background.png "${PKG_DIR}/usr/share/backgrounds/harmoni.png"
    sed -i 's/harmoni\.jpg/harmoni.png/' "${PKG_DIR}${INSTALL_DIR}/config/slick-greeter.conf"
elif [ -f assets/background.jpg ]; then
    cp assets/background.jpg "${PKG_DIR}/usr/share/backgrounds/harmoni.jpg"
else
    echo "→ Generating placeholder background..."
    python3 assets/generate_background.py 2>/dev/null || true
    if [ -f assets/background.png ]; then
        cp assets/background.png "${PKG_DIR}/usr/share/backgrounds/harmoni.png"
        sed -i 's/harmoni\.jpg/harmoni.png/' "${PKG_DIR}${INSTALL_DIR}/config/slick-greeter.conf"
    else
        echo "  ⚠ Could not generate background (non-critical)"
    fi
fi

# ── Build .deb ──
echo "→ Building .deb..."
dpkg-deb --build "${PKG_DIR}"

# ── Cleanup ──
rm -rf "${PKG_DIR}"

echo ""
echo "═══════════════════════════════════════════"
echo "  ✓ Built: ${PKG_DIR}.deb"
echo "═══════════════════════════════════════════"
echo ""
echo "  Install:  sudo apt install ./${PKG_DIR}.deb"
echo "            sudo reboot"
echo ""
