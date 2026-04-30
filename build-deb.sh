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
Recommends: lightdm, slick-greeter, pipewire-pulse | pulseaudio-utils, network-manager, i3lock
Maintainer: damnhalfling <damnhalfling@github.com>
Description: Harmoni OS — AI-first desktop interface
 A AI-first layer that replaces apps with intent-driven
 execution on top of Linux. Speak intent, get results.
 .
 Can be installed as an additional X session alongside
 GNOME/KDE, or as the default desktop with custom login.
Homepage: https://github.com/damnhalfling/harmoni
EOF

# ── DEBIAN/preinst (clean previous version + install deps) ──
cat > "${PKG_DIR}/DEBIAN/preinst" << 'PREINST'
#!/bin/bash
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

# ── Remove previous version if installed ──
if dpkg -s harmoni >/dev/null 2>&1; then
    PREV_VER=$(dpkg-query -W -f='${Version}' harmoni 2>/dev/null || echo "unknown")
    echo "[Harmoni] Previous version detected: ${PREV_VER}"
    echo "[Harmoni] Cleaning up before upgrade..."

    # Stop daemon if running
    if [ -f /tmp/harmoni.sock ]; then
        echo '{"command":"shutdown"}' | socat - UNIX-CONNECT:/tmp/harmoni.sock 2>/dev/null || true
        sleep 0.5
    fi

    # Kill any running Harmoni processes (but not this installer)
    pkill -f "python.*harmoni\.main" 2>/dev/null || true
    pkill -f "harmoni-session" 2>/dev/null || true

    # Remove old venv (will be recreated by postinst)
    if [ -d /usr/share/harmoni/.venv ]; then
        echo "[Harmoni] Removing old virtual environment..."
        rm -rf /usr/share/harmoni/.venv
    fi

    # Remove old .pyc caches
    find /usr/share/harmoni -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    echo "[Harmoni] Cleanup complete. Installing ${PREV_VER} → new version..."
fi

# ── Install system dependencies ──
echo "[Harmoni] Checking dependencies..."

if ! fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; then
    apt-get update -qq 2>/dev/null || true
    apt-get install -y -qq python3 python3-pip python3-venv python3-tk \
        openbox wmctrl xdotool x11-xserver-utils curl 2>/dev/null || true
fi

exit 0
PREINST
chmod 755 "${PKG_DIR}/DEBIAN/preinst"

# ── DEBIAN/postinst ──
cat > "${PKG_DIR}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
set -e
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

# Wait for dpkg lock to be released (we're called from dpkg itself)
_wait_dpkg_lock() {
    local max_wait=60
    local waited=0
    while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
        if [ $waited -ge $max_wait ]; then
            echo "[Harmoni] ⚠ dpkg lock timeout — skipping package install"
            return 1
        fi
        sleep 2
        waited=$((waited + 2))
    done
    return 0
}

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║       Harmoni OS — Configuration         ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# ── Install Python deps ──
echo "[Harmoni] Installing Python dependencies..."
if [ ! -d /usr/share/harmoni/.venv ]; then
    python3 -m venv /usr/share/harmoni/.venv 2>/dev/null || {
        echo "[Harmoni] ⚠ Could not create venv. Trying with system Python..."
        # Fallback: install directly to system (less clean but works)
        pip3 install --quiet --break-system-packages \
            boto3==1.35.86 prompt_toolkit==3.0.48 rich==13.9.4 psutil==6.1.1 2>/dev/null || true
    }
fi

if [ -d /usr/share/harmoni/.venv ]; then
    /usr/share/harmoni/.venv/bin/pip install --quiet \
        boto3==1.35.86 \
        prompt_toolkit==3.0.48 \
        rich==13.9.4 \
        psutil==6.1.1 2>/dev/null || {
        echo "[Harmoni] ⚠ Some Python deps failed to install (non-critical)"
    }

    /usr/share/harmoni/.venv/bin/pip install --quiet -e /usr/share/harmoni 2>/dev/null || {
        echo "[Harmoni] ⚠ Package install failed (non-critical)"
    }
fi

chmod +x /usr/local/bin/harmoni-session 2>/dev/null || true

# ── Install Ollama (local LLM) ──
if command -v ollama &>/dev/null; then
    echo "[Harmoni] Ollama already installed ✓"
else
    echo ""
    echo "[Harmoni] Ollama (local AI) not found."
    echo "  Ollama enables offline AI reasoning (free, private, no API key needed)."
    echo "  Without it, Harmoni still works for 80%+ of commands via pattern matching."
    echo ""

    INSTALL_OLLAMA="n"
    if [ -t 0 ]; then
        read -p "  Install Ollama now? [Y/n] " -n 1 -r OLLAMA_CHOICE
        echo ""
        if [[ ! "$OLLAMA_CHOICE" =~ ^[Nn]$ ]]; then
            INSTALL_OLLAMA="y"
        fi
    fi

    if [ "$INSTALL_OLLAMA" = "y" ]; then
        echo "[Harmoni] Installing Ollama..."
        curl -fsSL https://ollama.ai/install.sh | sh 2>/dev/null || {
            echo "[Harmoni] ⚠ Ollama install failed (non-critical). You can install later:"
            echo "  curl -fsSL https://ollama.ai/install.sh | sh"
            echo "  ollama pull mistral"
        }

        # Pull default model if Ollama installed successfully
        if command -v ollama &>/dev/null; then
            echo "[Harmoni] Downloading AI model (mistral, ~4GB)..."
            echo "  This may take a few minutes on first install."
            ollama pull mistral 2>/dev/null || {
                echo "[Harmoni] ⚠ Model download failed. Run later: ollama pull mistral"
            }
            echo "[Harmoni] Ollama ready ✓"
        fi
    else
        echo "[Harmoni] Skipping Ollama. Install later if needed:"
        echo "  curl -fsSL https://ollama.ai/install.sh | sh && ollama pull mistral"
    fi
fi

# ── Session is always registered ──
# The .desktop file in /usr/share/xsessions/ makes Harmoni
# available as a session option in ANY display manager (GDM, LightDM, SDDM).

# ── Apply Harmoni branding to LightDM greeter (all modes) ──
if command -v lightdm &>/dev/null || [ -d /etc/lightdm ]; then
    mkdir -p /etc/lightdm
    # slick-greeter
    if [ -f /usr/share/harmoni/config/slick-greeter.conf ]; then
        if [ -f /etc/lightdm/slick-greeter.conf ] && [ ! -f /etc/lightdm/slick-greeter.conf.bak.harmoni ]; then
            cp /etc/lightdm/slick-greeter.conf /etc/lightdm/slick-greeter.conf.bak.harmoni
        fi
        cp /usr/share/harmoni/config/slick-greeter.conf /etc/lightdm/slick-greeter.conf
        echo "[Harmoni] LightDM greeter configured (slick-greeter)"
    fi
    # lightdm-gtk-greeter (Debian default)
    if command -v lightdm-gtk-greeter &>/dev/null || [ -f /etc/lightdm/lightdm-gtk-greeter.conf ]; then
        if [ ! -f /etc/lightdm/lightdm-gtk-greeter.conf.bak.harmoni ] && [ -f /etc/lightdm/lightdm-gtk-greeter.conf ]; then
            cp /etc/lightdm/lightdm-gtk-greeter.conf /etc/lightdm/lightdm-gtk-greeter.conf.bak.harmoni
        fi
        cat > /etc/lightdm/lightdm-gtk-greeter.conf << 'GTKGREETER'
[greeter]
background=/usr/share/backgrounds/harmoni.png
theme-name=Adwaita-dark
icon-theme-name=Adwaita
default-user-image=/usr/share/pixmaps/harmoni-logo.png
GTKGREETER
        echo "[Harmoni] LightDM greeter configured (gtk-greeter)"
    fi
fi

echo ""
echo "[Harmoni] Harmoni session registered."
echo ""
echo "  Choose installation mode:"
echo ""
echo "  1) Session only (recommended)"
echo "     Adds 'Harmoni OS' as an option in your login screen."
echo "     Your current desktop (GNOME/KDE) stays untouched."
echo ""
echo "  2) Full replacement"
echo "     Switches to LightDM with custom Harmoni theme."
echo "     Harmoni becomes the default session."
echo "     GNOME/KDE stays installed as fallback."
echo ""
echo "  3) Clean install (advanced)"
echo "     Removes GNOME/KDE completely. Only Harmoni remains."
echo "     ⚠ Cannot be undone easily. Make sure Harmoni works first."
echo ""

# Default to mode 1 if non-interactive (CI, piped input, etc.)
INSTALL_MODE="1"
if [ -t 0 ]; then
    read -p "  Choose [1/2/3] (default: 1): " -n 1 -r USER_CHOICE
    echo ""
    case "$USER_CHOICE" in
        2) INSTALL_MODE="2" ;;
        3) INSTALL_MODE="3" ;;
        *) INSTALL_MODE="1" ;;
    esac
fi

# ── Mode 2 & 3: Configure LightDM ──
if [ "$INSTALL_MODE" = "2" ] || [ "$INSTALL_MODE" = "3" ]; then
    echo ""
    echo "[Harmoni] Configuring LightDM as display manager..."

    # Install LightDM + greeter if not present
    LIGHTDM_OK=false
    if command -v lightdm &>/dev/null; then
        LIGHTDM_OK=true
    else
        echo "[Harmoni] Waiting for package manager..."
        if _wait_dpkg_lock; then
            apt-get update -qq 2>/dev/null || true
            if apt-get install -y -qq lightdm slick-greeter 2>/dev/null; then
                LIGHTDM_OK=true
            fi
        fi
    fi

    if [ "$LIGHTDM_OK" = true ]; then
        # Backup current display manager config
        if [ -f /etc/X11/default-display-manager ]; then
            cp /etc/X11/default-display-manager /etc/X11/default-display-manager.bak.harmoni
            echo "[Harmoni] Backed up current display manager to .bak.harmoni"
        fi

        # Set LightDM as default
        mkdir -p /etc/X11
        echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager
        dpkg-reconfigure -f noninteractive lightdm 2>/dev/null || true

        # Apply Harmoni LightDM configs
        mkdir -p /etc/lightdm
        if [ -f /etc/lightdm/lightdm.conf ]; then
            cp /etc/lightdm/lightdm.conf /etc/lightdm/lightdm.conf.bak.harmoni
        fi
        if [ -f /etc/lightdm/slick-greeter.conf ]; then
            cp /etc/lightdm/slick-greeter.conf /etc/lightdm/slick-greeter.conf.bak.harmoni
        fi
        cp /usr/share/harmoni/config/lightdm.conf /etc/lightdm/lightdm.conf
        cp /usr/share/harmoni/config/slick-greeter.conf /etc/lightdm/slick-greeter.conf

        echo "[Harmoni] LightDM configured. Harmoni is the default session."
    else
        echo "[Harmoni] ⚠ Could not install LightDM now."
        echo "  After install completes, run:"
        echo "    sudo apt-get install lightdm slick-greeter"
        echo "    sudo dpkg-reconfigure harmoni"
    fi
fi

# ── Mode 3: Remove GNOME/KDE ──
if [ "$INSTALL_MODE" = "3" ]; then
    echo ""
    echo "[Harmoni] Clean install — removing other desktop environments..."

    # Detect what's installed and remove it
    _REMOVED=""

    # GNOME
    if dpkg -l | grep -q "gnome-shell"; then
        echo "[Harmoni] Removing GNOME..."
        apt-get remove -y --purge gnome-shell gnome-session gnome-control-center \
            gnome-terminal nautilus gdm3 2>/dev/null || true
        apt-get remove -y --purge 'gnome-*' 2>/dev/null || true
        _REMOVED="${_REMOVED} GNOME"
    fi

    # KDE/Plasma
    if dpkg -l | grep -q "plasma-desktop"; then
        echo "[Harmoni] Removing KDE Plasma..."
        apt-get remove -y --purge plasma-desktop plasma-workspace sddm \
            kde-standard 2>/dev/null || true
        apt-get remove -y --purge 'kde-*' 'plasma-*' 2>/dev/null || true
        _REMOVED="${_REMOVED} KDE"
    fi

    # XFCE
    if dpkg -l | grep -q "xfce4-session"; then
        echo "[Harmoni] Removing XFCE..."
        apt-get remove -y --purge xfce4-session xfce4-panel xfdesktop4 \
            xfwm4 2>/dev/null || true
        apt-get remove -y --purge 'xfce4-*' 2>/dev/null || true
        _REMOVED="${_REMOVED} XFCE"
    fi

    # MATE
    if dpkg -l | grep -q "mate-session-manager"; then
        echo "[Harmoni] Removing MATE..."
        apt-get remove -y --purge mate-session-manager mate-panel \
            mate-desktop 2>/dev/null || true
        apt-get remove -y --purge 'mate-*' 2>/dev/null || true
        _REMOVED="${_REMOVED} MATE"
    fi

    # Cinnamon
    if dpkg -l | grep -q "cinnamon-session"; then
        echo "[Harmoni] Removing Cinnamon..."
        apt-get remove -y --purge cinnamon-session cinnamon-desktop \
            nemo 2>/dev/null || true
        apt-get remove -y --purge 'cinnamon-*' 2>/dev/null || true
        _REMOVED="${_REMOVED} Cinnamon"
    fi

    # Clean up orphaned packages
    echo "[Harmoni] Cleaning up orphaned packages..."
    apt-get autoremove -y --purge 2>/dev/null || true
    apt-get clean 2>/dev/null || true

    if [ -n "$_REMOVED" ]; then
        echo "[Harmoni] Removed:${_REMOVED}"
    else
        echo "[Harmoni] No other desktop environments found."
    fi

    echo "[Harmoni] ✓ Clean install complete. Only Harmoni remains."
fi

# ── Mode 1: Session only ──
if [ "$INSTALL_MODE" = "1" ]; then
    echo ""
    echo "[Harmoni] Session-only mode — no display manager changes."
    echo "[Harmoni] Select 'Harmoni OS' from your login screen session menu."
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  Installation complete. Reboot to start."
echo "═══════════════════════════════════════════"
echo ""

# Never fail the postinst — all optional steps are non-critical
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
