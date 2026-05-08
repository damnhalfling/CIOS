#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  CIOS — Build .deb package
#  Usage: bash build-deb.sh [VERSION]
#  Example: bash build-deb.sh 0.3.0
# ═══════════════════════════════════════════════════
set -euo pipefail

VERSION="${1:-0.3.0}"
PKG_NAME="cios"
PKG_DIR="${PKG_NAME}_${VERSION}_amd64"
INSTALL_DIR="/usr/share/cios"

echo "╔═══════════════════════════════════════════╗"
echo "║  CIOS — Building .deb v${VERSION}             ║"
echo "╚═══════════════════════════════════════════╝"

# ── Clean previous build ──
rm -rf "${PKG_DIR}" "${PKG_DIR}.deb"

# ── Create directory structure ──
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/core"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/core/handlers"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/ui"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/infra"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/skills"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/assets"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/config"
mkdir -p "${PKG_DIR}/usr/local/bin"
mkdir -p "${PKG_DIR}/usr/share/xsessions"
mkdir -p "${PKG_DIR}/usr/share/plymouth/themes/cios"
mkdir -p "${PKG_DIR}/usr/share/backgrounds"
mkdir -p "${PKG_DIR}/etc/xdg/openbox-cios"

# ── DEBIAN/control ──
cat > "${PKG_DIR}/DEBIAN/control" << EOF
Package: cios
Version: ${VERSION}
Section: x11
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10), python3-pip, python3-venv, python3-tk, xorg, lightdm, lightdm-gtk-greeter, openbox, wmctrl, xdotool, x11-xserver-utils, curl
Recommends: pipewire-pulse | pulseaudio-utils, network-manager, i3lock, plymouth
Suggests: slick-greeter, plymouth-themes
Maintainer: damnhalfling <damnhalfling@github.com>
Description: CIOS — AI-first desktop interface
 A AI-first layer that replaces apps with intent-driven
 execution on top of Linux. Speak intent, get results.
 .
 Can be installed as an additional X session alongside
 GNOME/KDE, or as the default desktop with custom login.
Homepage: https://github.com/damnhalfling/cios
EOF

# ── DEBIAN/preinst (clean previous version) ──
cat > "${PKG_DIR}/DEBIAN/preinst" << 'PREINST'
#!/bin/bash
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

# Always clean pycache (prevents stale bytecode on upgrades)
find /usr/share/cios -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# ── Remove previous version if installed ──
if dpkg -s cios >/dev/null 2>&1; then
    PREV_VER=$(dpkg-query -W -f='${Version}' cios 2>/dev/null || echo "unknown")
    echo "[CIOS] Previous version detected: ${PREV_VER}"
    echo "[CIOS] Cleaning up before upgrade..."

    # Stop daemon if running (socket only, not the session)
    if [ -f /tmp/cios.sock ]; then
        echo '{"command":"shutdown"}' | socat - UNIX-CONNECT:/tmp/cios.sock 2>/dev/null || true
        sleep 0.5
    fi

    # NOTE: Do NOT kill cios-session or cios.main here!
    # The user might be running dpkg -i from within the CIOS session itself.
    # Killing those processes would terminate the X session and log out the user.

    # Remove old venv (will be recreated by postinst)
    if [ -d /usr/share/cios/.venv ]; then
        echo "[CIOS] Removing old virtual environment..."
        rm -rf /usr/share/cios/.venv
    fi

    echo "[CIOS] Cleanup complete."
fi

exit 0
PREINST
chmod 755 "${PKG_DIR}/DEBIAN/preinst"

# ── DEBIAN/postinst ──
cat > "${PKG_DIR}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
# CIOS postinst — interactive installation with mode selection.
# Handles everything: venv, deps, LightDM, Plymouth, GRUB.
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"
export DEBIAN_FRONTEND=noninteractive

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║       CIOS — Installer                   ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# ── Create Python venv + install deps ──
echo "[CIOS] Setting up Python environment..."

# Ensure python3-tk is installed for the correct Python version
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "[CIOS] Installing python3-tk..."
    apt-get install -y python3-tk 2>/dev/null || true
    # Try version-specific package (e.g., python3.11-tk)
    if ! python3 -c "import tkinter" 2>/dev/null && [ -n "$PY_VER" ]; then
        apt-get install -y "python${PY_VER}-tk" 2>/dev/null || true
    fi
fi

if [ ! -d /usr/share/cios/.venv ]; then
    python3 -m venv --system-site-packages /usr/share/cios/.venv 2>/dev/null || {
        echo "[CIOS] ⚠ Could not create venv. Will use system Python."
        pip3 install --quiet --break-system-packages \
            prompt_toolkit==3.0.48 rich==13.9.4 psutil==6.1.1 Pillow 2>/dev/null || true
    }
fi

if [ -d /usr/share/cios/.venv ]; then
    # Verify venv has tkinter access, recreate if not
    if ! /usr/share/cios/.venv/bin/python3 -c "import tkinter" 2>/dev/null; then
        echo "[CIOS] Venv missing tkinter, recreating with --system-site-packages..."
        rm -rf /usr/share/cios/.venv
        python3 -m venv --system-site-packages /usr/share/cios/.venv 2>/dev/null || true
    fi

    /usr/share/cios/.venv/bin/pip install --quiet \
        prompt_toolkit==3.0.48 \
        rich==13.9.4 \
        psutil==6.1.1 \
        Pillow 2>/dev/null || true

    /usr/share/cios/.venv/bin/pip install --quiet -e /usr/share/cios 2>/dev/null || true
fi

chmod +x /usr/local/bin/cios-session 2>/dev/null || true
echo "[CIOS] ✓ Python environment ready"

# ── Install Ollama (local LLM) ──
if ! command -v ollama &>/dev/null; then
    echo "[CIOS] Installing Ollama (local AI)..."
    curl -fsSL https://ollama.com/install.sh | sh 2>/dev/null || {
        echo "[CIOS] ⚠ Could not install Ollama. Local AI will be unavailable."
        echo "[CIOS]   Install manually later: curl -fsSL https://ollama.com/install.sh | sh"
    }
fi

# Pull default model if Ollama is available
if command -v ollama &>/dev/null; then
    echo "[CIOS] Pulling default model (mistral)..."
    # Start ollama serve temporarily for the pull
    ollama serve &>/dev/null &
    OLLAMA_SERVE_PID=$!
    sleep 2
    ollama pull mistral 2>/dev/null || {
        echo "[CIOS] ⚠ Could not pull mistral model now. Will retry on first boot."
    }
    kill $OLLAMA_SERVE_PID 2>/dev/null || true
fi

echo "[CIOS] ✓ AI environment ready"

# ── Install voice tools (optional — STT/TTS) ──
echo "[CIOS] Setting up voice (optional)..."

# Install piper TTS (local, offline)
if ! command -v piper &>/dev/null; then
    echo "[CIOS] Installing piper (TTS)..."
    PIPER_VERSION="2023.11.14-2"
    PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz"
    if curl -fsSL "$PIPER_URL" -o /tmp/piper.tar.gz 2>/dev/null; then
        tar -xzf /tmp/piper.tar.gz -C /usr/local/bin/ --strip-components=1 piper/piper 2>/dev/null || true
        rm -f /tmp/piper.tar.gz
        # Download PT-BR voice model
        mkdir -p /usr/share/piper/voices
        VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
        curl -fsSL "$VOICE_URL" -o /usr/share/piper/voices/pt_BR-faber-medium.onnx 2>/dev/null || true
        curl -fsSL "${VOICE_URL}.json" -o /usr/share/piper/voices/pt_BR-faber-medium.onnx.json 2>/dev/null || true
        echo "[CIOS] ✓ Piper TTS installed"
    else
        echo "[CIOS] ⚠ Could not download piper. TTS will be unavailable."
    fi
fi

# Install whisper.cpp (local STT)
if ! command -v whisper-cpp &>/dev/null && ! command -v whisper &>/dev/null; then
    echo "[CIOS] Installing whisper (STT)..."
    # Try pip install (openai-whisper is simpler to install)
    if [ -d /usr/share/cios/.venv ]; then
        /usr/share/cios/.venv/bin/pip install --quiet openai-whisper 2>/dev/null && {
            # Create symlink so VoiceManager finds it
            ln -sf /usr/share/cios/.venv/bin/whisper /usr/local/bin/whisper 2>/dev/null || true
            echo "[CIOS] ✓ Whisper STT installed"
        } || {
            echo "[CIOS] ⚠ Could not install whisper. STT will be unavailable."
        }
    fi
fi

echo "[CIOS] ✓ Voice setup complete"

# ── Apply LightDM branding if LightDM is installed (both modes) ──
if [ -d /etc/lightdm ] && command -v lightdm &>/dev/null; then
    CIOS_CONF="/usr/share/cios/config"
    if [ -f "$CIOS_CONF/slick-greeter.conf" ] && [ -f /usr/share/pixmaps/cios-logo.png ]; then
        if [ ! -f /etc/lightdm/slick-greeter.conf.bak.cios ]; then
            cp /etc/lightdm/slick-greeter.conf /etc/lightdm/slick-greeter.conf.bak.cios 2>/dev/null || true
        fi
        cp "$CIOS_CONF/slick-greeter.conf" /etc/lightdm/slick-greeter.conf
        echo "[CIOS] ✓ LightDM branding applied (logo + background)"
    fi
fi

echo ""

# ── Installation mode ──
# Auto-detect: if no display manager is running/installed, go full replacement
# If a DM exists (GDM, SDDM), ask the user
EXISTING_DM=""
for dm in gdm gdm3 sddm; do
    if command -v "$dm" &>/dev/null || systemctl is-active "$dm" &>/dev/null 2>&1; then
        EXISTING_DM="$dm"
        break
    fi
done

if [ -z "$EXISTING_DM" ]; then
    # No existing desktop — full replacement automatically
    echo "[CIOS] Nenhum desktop detectado. Instalando como desktop padrão."
    INSTALL_MODE="2"
else
    echo "┌─────────────────────────────────────────────┐"
    echo "│  Desktop detectado: $EXISTING_DM"
    echo "│                                              │"
    echo "│  1) Sessão adicional                         │"
    echo "│     CIOS aparece ao lado na tela de login    │"
    echo "│                                              │"
    echo "│  2) Substituição completa                    │"
    echo "│     Remove $EXISTING_DM, instala LightDM     │"
    echo "│     com tema CIOS + Plymouth boot splash     │"
    echo "│     (reversível com: sudo apt remove cios)   │"
    echo "│                                              │"
    echo "└─────────────────────────────────────────────┘"
    echo ""

    INSTALL_MODE="1"
    if [ -t 0 ]; then
        read -rp "  Opção [1]: " INSTALL_MODE
        INSTALL_MODE="${INSTALL_MODE:-1}"
    elif [ -e /dev/tty ]; then
        echo -n "  Opção [1]: " > /dev/tty
        read -r INSTALL_MODE < /dev/tty || INSTALL_MODE="1"
        INSTALL_MODE="${INSTALL_MODE:-1}"
    fi
fi

echo ""

# ── Mode 2: Full replacement ──
if [ "$INSTALL_MODE" = "2" ]; then
    echo "[CIOS] Configurando substituição completa..."

    # Block DM restarts during postinst
    cat > /usr/sbin/policy-rc.d << 'POLICY'
#!/bin/sh
case "$1" in
    lightdm|gdm|gdm3|sddm|display-manager) exit 101 ;;
    *) exit 0 ;;
esac
POLICY
    chmod 755 /usr/sbin/policy-rc.d

    # LightDM and Xorg are already installed as package dependencies
    # Just need to configure them
    echo "[CIOS] ✓ Xorg + LightDM already installed (package deps)"

    # Remove DM restart block
    rm -f /usr/sbin/policy-rc.d

    # Backup + set LightDM as default
    mkdir -p /etc/X11
    if [ -f /etc/X11/default-display-manager ] && [ ! -f /etc/X11/default-display-manager.bak.cios ]; then
        cp /etc/X11/default-display-manager /etc/X11/default-display-manager.bak.cios
    fi
    echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager

    # Apply LightDM configs (logo + background + theme)
    mkdir -p /etc/lightdm
    CIOS_CONF="/usr/share/cios/config"

    # Detect which greeter is available
    if command -v slick-greeter &>/dev/null; then
        GREETER="slick-greeter"
    elif [ -f /usr/share/xgreeters/lightdm-gtk-greeter.desktop ]; then
        GREETER="lightdm-gtk-greeter"
    else
        GREETER="lightdm-gtk-greeter"
    fi

    # Write lightdm.conf with correct greeter
    cat > /etc/lightdm/lightdm.conf << LDMCONF
[Seat:*]
greeter-session=$GREETER
user-session=cios
greeter-hide-users=false
allow-guest=false
LDMCONF

    # Apply greeter theme if slick-greeter
    if [ "$GREETER" = "slick-greeter" ] && [ -f "$CIOS_CONF/slick-greeter.conf" ]; then
        cp "$CIOS_CONF/slick-greeter.conf" /etc/lightdm/slick-greeter.conf
    fi

    # Apply GTK greeter theme if lightdm-gtk-greeter
    if [ "$GREETER" = "lightdm-gtk-greeter" ]; then
        cat > /etc/lightdm/lightdm-gtk-greeter.conf << 'GTKCONF'
[greeter]
background=/usr/share/backgrounds/cios.png
theme-name=Adwaita-dark
icon-theme-name=Adwaita
font-name=Sans 11
indicators=~host;~spacer;~session;~power
position=50%,center 50%,center
GTKCONF
    fi
    echo "[CIOS] ✓ LightDM configured (greeter: $GREETER)"

    # ── Plymouth boot splash (instant, in initramfs) ──
    PLYMOUTH_THEME="/usr/share/plymouth/themes/cios"
    if [ -d "$PLYMOUTH_THEME" ] && [ -f "$PLYMOUTH_THEME/cios.plymouth" ]; then
        plymouth-set-default-theme cios 2>/dev/null || {
            mkdir -p /etc/plymouth
            printf "[Daemon]\nTheme=cios\n" > /etc/plymouth/plymouthd.conf
        }

        # Force Plymouth into initramfs for instant splash after BIOS
        mkdir -p /etc/initramfs-tools/conf.d
        echo "FRAMEBUFFER=y" > /etc/initramfs-tools/conf.d/cios-splash

        # Include GPU drivers in initramfs (KMS = instant framebuffer)
        INITRAMFS_MODULES="/etc/initramfs-tools/modules"
        for mod in drm drm_kms_helper i915 amdgpu nouveau radeon; do
            if ! grep -q "^${mod}$" "$INITRAMFS_MODULES" 2>/dev/null; then
                echo "$mod" >> "$INITRAMFS_MODULES"
            fi
        done

        update-initramfs -u 2>/dev/null || true
        echo "[CIOS] ✓ Plymouth configured (initramfs, instant splash)"
    fi

    # ── GRUB: invisible, zero delay, silent kernel ──
    if [ -f /etc/default/grub ]; then
        if [ ! -f /etc/default/grub.bak.cios ]; then
            cp /etc/default/grub /etc/default/grub.bak.cios
        fi

        # Replace GRUB_CMDLINE_LINUX_DEFAULT with fully silent boot
        sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=0 vt.global_cursor_default=0 rd.udev.log_priority=3 systemd.show_status=false"/' /etc/default/grub

        # Zero timeout — GRUB is invisible (Shift/Esc still works to access menu)
        sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=0/' /etc/default/grub

        # Hidden style — no countdown, no menu
        if grep -q "^GRUB_TIMEOUT_STYLE" /etc/default/grub; then
            sed -i 's/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=hidden/' /etc/default/grub
        else
            echo 'GRUB_TIMEOUT_STYLE=hidden' >> /etc/default/grub
        fi

        # Don't probe for other OS (faster boot, cleaner menu)
        if grep -q "^GRUB_DISABLE_OS_PROBER" /etc/default/grub; then
            sed -i 's/^GRUB_DISABLE_OS_PROBER=.*/GRUB_DISABLE_OS_PROBER=true/' /etc/default/grub
        else
            echo 'GRUB_DISABLE_OS_PROBER=true' >> /etc/default/grub
        fi

        # Even after failed boot, keep timeout minimal (2s safety net)
        if grep -q "^GRUB_RECORDFAIL_TIMEOUT" /etc/default/grub; then
            sed -i 's/^GRUB_RECORDFAIL_TIMEOUT=.*/GRUB_RECORDFAIL_TIMEOUT=2/' /etc/default/grub
        else
            echo 'GRUB_RECORDFAIL_TIMEOUT=2' >> /etc/default/grub
        fi

        update-grub 2>/dev/null || true
        echo "[CIOS] ✓ GRUB invisible (0s timeout, silent kernel, no OS probe)"
    fi

    # Disable other DMs
    for dm in gdm gdm3 sddm; do
        if systemctl is-enabled "$dm" 2>/dev/null | grep -q "enabled"; then
            systemctl disable "$dm" 2>/dev/null || true
        fi
    done
    systemctl enable lightdm 2>/dev/null || true

    # Ensure system boots to graphical target (not multi-user/text)
    systemctl set-default graphical.target 2>/dev/null || true

    echo ""
    echo "═══════════════════════════════════════════"
    echo "  ✓ Substituição completa configurada!"
    echo ""
    echo "  Boot: logo CIOS (Plymouth)"
    echo "  Login: LightDM com tema CIOS"
    echo "  Desktop: CIOS"
    echo ""
    echo "  Reboot: sudo reboot"
    echo "  Reverter: sudo apt remove cios && sudo reboot"
    echo "═══════════════════════════════════════════"
    echo ""
else
    # ── Mode 1: Session only — but still optimize boot if Plymouth available ──
    PLYMOUTH_THEME="/usr/share/plymouth/themes/cios"
    if [ -d "$PLYMOUTH_THEME" ] && [ -f "$PLYMOUTH_THEME/cios.plymouth" ] && command -v plymouth-set-default-theme &>/dev/null; then
        plymouth-set-default-theme cios 2>/dev/null || true

        # Plymouth in initramfs for instant splash
        mkdir -p /etc/initramfs-tools/conf.d
        echo "FRAMEBUFFER=y" > /etc/initramfs-tools/conf.d/cios-splash

        INITRAMFS_MODULES="/etc/initramfs-tools/modules"
        for mod in drm drm_kms_helper i915 amdgpu nouveau radeon; do
            if ! grep -q "^${mod}$" "$INITRAMFS_MODULES" 2>/dev/null; then
                echo "$mod" >> "$INITRAMFS_MODULES"
            fi
        done

        update-initramfs -u 2>/dev/null || true

        # Silent GRUB
        if [ -f /etc/default/grub ]; then
            if [ ! -f /etc/default/grub.bak.cios ]; then
                cp /etc/default/grub /etc/default/grub.bak.cios
            fi
            sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=0 vt.global_cursor_default=0 rd.udev.log_priority=3 systemd.show_status=false"/' /etc/default/grub
            sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=0/' /etc/default/grub
            if grep -q "^GRUB_TIMEOUT_STYLE" /etc/default/grub; then
                sed -i 's/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=hidden/' /etc/default/grub
            else
                echo 'GRUB_TIMEOUT_STYLE=hidden' >> /etc/default/grub
            fi
            if grep -q "^GRUB_RECORDFAIL_TIMEOUT" /etc/default/grub; then
                sed -i 's/^GRUB_RECORDFAIL_TIMEOUT=.*/GRUB_RECORDFAIL_TIMEOUT=2/' /etc/default/grub
            else
                echo 'GRUB_RECORDFAIL_TIMEOUT=2' >> /etc/default/grub
            fi
            update-grub 2>/dev/null || true
        fi
        echo "[CIOS] ✓ Boot otimizado (Plymouth + GRUB silencioso)"
    fi

    echo "═══════════════════════════════════════════"
    echo "  ✓ CIOS instalado (sessão adicional)"
    echo ""
    echo "  Reboot e selecione 'CIOS' na tela de login."
    echo "  sudo reboot"
    echo "═══════════════════════════════════════════"
    echo ""
fi

# Never fail
exit 0
POSTINST
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

# ── DEBIAN/prerm ──
cat > "${PKG_DIR}/DEBIAN/prerm" << 'PRERM'
#!/bin/bash
set -e
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

echo "[CIOS] Removing..."

# Restore original display manager if we changed it
if [ -f /etc/X11/default-display-manager.bak.cios ]; then
    cp /etc/X11/default-display-manager.bak.cios /etc/X11/default-display-manager
    rm -f /etc/X11/default-display-manager.bak.cios
    echo "[CIOS] Restored original display manager"
fi

# Restore LightDM configs if we changed them
if [ -f /etc/lightdm/lightdm.conf.bak.cios ]; then
    mv /etc/lightdm/lightdm.conf.bak.cios /etc/lightdm/lightdm.conf
fi
if [ -f /etc/lightdm/slick-greeter.conf.bak.cios ]; then
    mv /etc/lightdm/slick-greeter.conf.bak.cios /etc/lightdm/slick-greeter.conf
fi
if [ -f /etc/lightdm/lightdm-gtk-greeter.conf.bak.cios ]; then
    mv /etc/lightdm/lightdm-gtk-greeter.conf.bak.cios /etc/lightdm/lightdm-gtk-greeter.conf
fi

# Restore Plymouth theme to default
if command -v plymouth-set-default-theme &>/dev/null; then
    CURRENT_THEME=$(plymouth-set-default-theme 2>/dev/null || echo "")
    if [ "$CURRENT_THEME" = "cios" ]; then
        plymouth-set-default-theme -R spinner 2>/dev/null || \
        plymouth-set-default-theme -R ubuntu-logo 2>/dev/null || true
        echo "[CIOS] Restored default Plymouth theme"
    fi
fi

# Remove initramfs splash config
rm -f /etc/initramfs-tools/conf.d/cios-splash

# Remove GPU modules we added (only the ones we explicitly added)
INITRAMFS_MODULES="/etc/initramfs-tools/modules"
if [ -f "$INITRAMFS_MODULES" ]; then
    for mod in drm drm_kms_helper i915 amdgpu nouveau radeon; do
        sed -i "/^${mod}$/d" "$INITRAMFS_MODULES" 2>/dev/null || true
    done
fi

update-initramfs -u 2>/dev/null || true

# Restore GRUB if we changed it
if [ -f /etc/default/grub.bak.cios ]; then
    mv /etc/default/grub.bak.cios /etc/default/grub
    update-grub 2>/dev/null || true
    echo "[CIOS] Restored GRUB config"
fi

# Clean venv
rm -rf /usr/share/cios/.venv

echo "[CIOS] Removed."
PRERM
chmod 755 "${PKG_DIR}/DEBIAN/prerm"

# ── App files ──
echo "→ Copying application files..."

# Core Python modules
cp pyproject.toml "${PKG_DIR}${INSTALL_DIR}/"
cp -r cios/*.py "${PKG_DIR}${INSTALL_DIR}/cios/"
cp -r cios/core/*.py "${PKG_DIR}${INSTALL_DIR}/cios/core/"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/core/handlers"
cp -r cios/core/handlers/*.py "${PKG_DIR}${INSTALL_DIR}/cios/core/handlers/"
cp -r cios/ui/*.py "${PKG_DIR}${INSTALL_DIR}/cios/ui/"
cp -r cios/infra/*.py "${PKG_DIR}${INSTALL_DIR}/cios/infra/"
cp -r cios/skills/*.py "${PKG_DIR}${INSTALL_DIR}/cios/skills/"

# ── Session files ──
echo "→ Copying session files..."

# Session script
cat > "${PKG_DIR}/usr/local/bin/cios-session" << 'SESSION'
#!/bin/bash
# CIOS X Session — optimized boot
# Zero flicker. Splash with real progress. Crash recovery.

export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export NO_AT_BRIDGE=1
export GTK_A11Y=none

LOGFILE="$HOME/.cios/session.log"
mkdir -p "$HOME/.cios"

echo "=== CIOS session starting $(date) ===" >> "$LOGFILE"

# Set background IMMEDIATELY (prevents any flash)
xsetroot -solid '#0a0a0f' 2>/dev/null || true
xsetroot -cursor_name left_ptr 2>/dev/null || true

# Find Python — try venv first, then system
VENV="/usr/share/cios/.venv/bin/python3"
if [ ! -x "$VENV" ]; then
    VENV=$(which python3 2>/dev/null)
    echo "WARNING: venv not found, using system python: $VENV" >> "$LOGFILE"
fi

# Verify tkinter is accessible — if venv can't import it, fall back to system python
if [ -x "/usr/share/cios/.venv/bin/python3" ]; then
    if ! /usr/share/cios/.venv/bin/python3 -c "import tkinter" 2>/dev/null; then
        echo "WARNING: tkinter not available in venv, falling back to system python" >> "$LOGFILE"
        VENV=$(which python3 2>/dev/null)
    fi
fi

if [ -z "$VENV" ]; then
    echo "FATAL: No python3 found!" >> "$LOGFILE"
    xterm -e "echo 'CIOS: python3 not found. Check installation.'; bash" &
    wait
    exit 1
fi

# Ensure cios module is findable
export PYTHONPATH="/usr/share/cios:${PYTHONPATH:-}"

# Verify cios module is importable
if ! $VENV -c "import cios" 2>/dev/null; then
    echo "FATAL: Cannot import cios module" >> "$LOGFILE"
    echo "Python: $VENV" >> "$LOGFILE"
    echo "PYTHONPATH: $PYTHONPATH" >> "$LOGFILE"
    $VENV -c "import cios" >> "$LOGFILE" 2>&1
    xterm -e "echo 'CIOS: module not found. Run: sudo apt install -f'; tail -10 $LOGFILE; echo; bash" &
    wait
    exit 1
fi

# Show splash BEFORE Openbox (user sees brand instantly)
$VENV -m cios.ui.splash &
SPLASH_PID=$!

# Start Openbox in parallel
OPENBOX_CONF="/etc/xdg/openbox-cios"
if command -v openbox &>/dev/null; then
    openbox --config-file "${OPENBOX_CONF}/rc.xml" &
    echo "Openbox started (PID $!)" >> "$LOGFILE"
else
    echo "WARNING: openbox not found, trying without WM" >> "$LOGFILE"
fi

# Start CIOS (crash recovery loop)
CRASH_COUNT=0
while true; do
    echo "Starting CIOS at $(date)" >> "$LOGFILE"
    $VENV -m cios.main >> "$LOGFILE" 2>&1
    EXIT_CODE=$?
    echo "CIOS exited with code $EXIT_CODE at $(date)" >> "$LOGFILE"

    kill $SPLASH_PID 2>/dev/null || true

    # Exit code 77 = tkinter not available, fall back to CLI in xterm
    if [ $EXIT_CODE -eq 77 ]; then
        echo "Tkinter not available, launching CLI in xterm" >> "$LOGFILE"
        # Try to fix tkinter first
        sudo apt-get install -y python3-tk 2>/dev/null || true
        # If fix worked, retry GUI
        if $VENV -c "import tkinter" 2>/dev/null; then
            echo "python3-tk installed successfully, retrying GUI" >> "$LOGFILE"
            continue
        fi
        # Otherwise launch CLI in terminal
        xterm -fa "Monospace" -fs 11 -bg "#0a0a0f" -fg "#fafafa" \
            -T "CIOS" -e "$VENV -m cios --cli" 2>/dev/null || \
            x-terminal-emulator -e "$VENV -m cios --cli" 2>/dev/null || \
            $VENV -m cios --cli
        break
    fi

    if [ $EXIT_CODE -eq 0 ]; then
        break
    fi

    CRASH_COUNT=$((CRASH_COUNT + 1))
    if [ $CRASH_COUNT -ge 3 ]; then
        echo "Too many crashes, opening terminal" >> "$LOGFILE"
        xterm -e "echo 'CIOS crashed 3x. Check ~/.cios/session.log'; tail -30 $LOGFILE; echo; bash" &
        wait
        break
    fi

    $VENV -m cios.ui.splash &
    SPLASH_PID=$!
    sleep 1
done

echo "=== Session ended $(date) ===" >> "$LOGFILE"
SESSION
chmod 755 "${PKG_DIR}/usr/local/bin/cios-session"

# X session desktop entry
cat > "${PKG_DIR}/usr/share/xsessions/cios.desktop" << 'XSESSION'
[Desktop Entry]
Name=CIOS
Comment=AI-first desktop interface
Exec=/usr/local/bin/cios-session
Type=Application
DesktopNames=CIOS
XSESSION

# Openbox config
cp session/rc.xml "${PKG_DIR}/etc/xdg/openbox-cios/rc.xml"

# Openbox autostart (fallback)
cat > "${PKG_DIR}/etc/xdg/openbox-cios/autostart" << 'AUTOSTART'
#!/bin/bash
# Fallback autostart — used if session script doesn't handle it
xsetroot -solid '#0a0a0f' 2>/dev/null || true
export NO_AT_BRIDGE=1
export GTK_A11Y=none
export PYTHONPATH="/usr/share/cios:${PYTHONPATH:-}"
VENV="/usr/share/cios/.venv/bin/python3"
if [ ! -x "$VENV" ]; then
    VENV="python3"
elif ! $VENV -c "import tkinter" 2>/dev/null; then
    VENV="python3"
fi
$VENV -m cios.ui.splash &
$VENV -m cios.main &
AUTOSTART
chmod 755 "${PKG_DIR}/etc/xdg/openbox-cios/autostart"

# ── LightDM config (bundled, applied only in full replacement mode) ──
echo "→ Bundling LightDM configs..."

cat > "${PKG_DIR}${INSTALL_DIR}/config/lightdm.conf" << 'LIGHTDM'
[Seat:*]
greeter-session=slick-greeter
user-session=cios
greeter-hide-users=false
allow-guest=false
LIGHTDM

cat > "${PKG_DIR}${INSTALL_DIR}/config/slick-greeter.conf" << 'GREETER'
[Greeter]
background=/usr/share/backgrounds/cios.png
logo=/usr/share/pixmaps/cios-logo.png
theme-name=Adwaita-dark
icon-theme-name=Adwaita
draw-grid=false
show-hostname=false
show-power=true
clock-format=%H:%M
GREETER

# ── Logo for LightDM ──
mkdir -p "${PKG_DIR}/usr/share/pixmaps"
if [ -f assets/cios_logo.png ]; then
    cp assets/cios_logo.png "${PKG_DIR}/usr/share/pixmaps/cios-logo.png"
    # Also copy to install dir so the running app can find it
    cp assets/cios_logo.png "${PKG_DIR}${INSTALL_DIR}/assets/cios_logo.png" 2>/dev/null || true
    echo "→ CIOS logo bundled for LightDM + GUI"
fi

# ── Plymouth boot splash theme ──
echo "→ Copying Plymouth theme..."
if [ -d plymouth/cios ]; then
    cp plymouth/cios/cios.plymouth "${PKG_DIR}/usr/share/plymouth/themes/cios/"
    cp plymouth/cios/cios.script "${PKG_DIR}/usr/share/plymouth/themes/cios/"
    # Use the same logo for Plymouth boot splash
    if [ -f assets/cios_logo.png ]; then
        cp assets/cios_logo.png "${PKG_DIR}/usr/share/plymouth/themes/cios/logo.png"
    fi
    echo "→ Plymouth theme bundled"
fi

# ── Background ──
if [ -f assets/background.png ]; then
    cp assets/background.png "${PKG_DIR}/usr/share/backgrounds/cios.png"
    sed -i 's/cios\.jpg/cios.png/' "${PKG_DIR}${INSTALL_DIR}/config/slick-greeter.conf"
elif [ -f assets/background.jpg ]; then
    cp assets/background.jpg "${PKG_DIR}/usr/share/backgrounds/cios.jpg"
else
    echo "→ Generating placeholder background..."
    python3 assets/generate_background.py 2>/dev/null || true
    if [ -f assets/background.png ]; then
        cp assets/background.png "${PKG_DIR}/usr/share/backgrounds/cios.png"
        sed -i 's/cios\.jpg/cios.png/' "${PKG_DIR}${INSTALL_DIR}/config/slick-greeter.conf"
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
