#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  CIOS — Build .deb package
#  Usage: bash build-deb.sh [VERSION]
#  Example: bash build-deb.sh 1.1.0-rc1
# ═══════════════════════════════════════════════════
set -euo pipefail

VERSION="${1:-1.1.0-rc5}"
PKG_NAME="cios"
PKG_DIR="${PKG_NAME}_${VERSION}_amd64"
INSTALL_DIR="/usr/share/cios"

# ── Ensure fakeroot is available (avoids permission issues in .deb) ──
if ! command -v fakeroot &>/dev/null; then
    echo "⚠ fakeroot not found. Installing..."
    sudo apt-get install -y fakeroot
fi

echo "╔═══════════════════════════════════════════╗"
echo "║  CIOS — Building .deb v${VERSION}             ║"
echo "╚═══════════════════════════════════════════╝"

# ── Clean previous build ──
rm -rf "${PKG_DIR}" "${PKG_DIR}.deb"

# ── Build Wayland compositor ──
echo "→ Building CIOS Shell (Wayland compositor)..."
export PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig:${PKG_CONFIG_PATH:-}"
if [ -d shell ]; then
    pushd shell > /dev/null
    rm -rf build
    meson setup build --prefix=/usr
    ninja -C build
    popd > /dev/null
    echo "→ ✓ cios-shell compiled"
else
    echo "ERROR: shell/ directory not found. Cannot build compositor."
    exit 1
fi

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
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/share/wayland-sessions"
mkdir -p "${PKG_DIR}/usr/share/plymouth/themes/cios"
mkdir -p "${PKG_DIR}/usr/share/backgrounds"

# ── DEBIAN/control ──
cat > "${PKG_DIR}/DEBIAN/control" << EOF
Package: cios
Version: ${VERSION}
Section: x11
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10), python3-pip, python3-venv, python3-gi, gir1.2-gtk-4.0, greetd, libxkbcommon0, libinput10, libseat1, seatd, libpixman-1-0, libdrm2, libgles2, libegl1, libgbm1, dmsetup, libcap2, plymouth, plymouth-themes, curl
Recommends: xwayland, pipewire-pulse | pulseaudio-utils, network-manager, wl-clipboard
Maintainer: damnhalfling <damnhalfling@github.com>
Description: CIOS — AI-first desktop interface (Wayland)
 A AI-first layer that replaces apps with intent-driven
 execution on top of Linux. Speak intent, get results.
 .
 Uses a custom Wayland compositor (cios-shell) based on
 wlroots 0.18+ with XWayland support for legacy apps.
 .
 Can be installed as an additional session alongside
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

# ── Note: bundled libs use RPATH, no global ldconfig needed ──

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║       CIOS — Installer                   ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# ── Note: bundled libs use RPATH on cios-shell binary, no global ldconfig needed ──

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
    # Verify venv has gi (GTK4) access, recreate if not
    if ! /usr/share/cios/.venv/bin/python3 -c "import gi" 2>/dev/null; then
        echo "[CIOS] Venv missing PyGObject (gi), recreating with --system-site-packages..."
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

# ── Install Ollama + Mistral (with progress feedback) ──
echo ""
echo "┌─────────────────────────────────────────────┐"
echo "│  Instalando IA local (Ollama + Mistral)      │"
echo "│  Isso pode levar 10-30 minutos.              │"
echo "│  Não interrompa a instalação.                 │"
echo "└─────────────────────────────────────────────┘"
echo ""

# Install Ollama
if ! command -v ollama &>/dev/null; then
    echo "[CIOS] [1/2] Baixando Ollama..."
    if curl -fsSL https://ollama.com/install.sh | sh; then
        echo "[CIOS] ✓ Ollama instalado"
    else
        echo "[CIOS] ⚠ Falha ao instalar Ollama. Execute depois: curl -fsSL https://ollama.com/install.sh | sh"
    fi
else
    echo "[CIOS] ✓ Ollama já instalado"
fi

# Pull Mistral model (with progress — ollama pull shows download %)
if command -v ollama &>/dev/null; then
    echo "[CIOS] [2/2] Baixando modelo Mistral (~4GB)..."
    echo "[CIOS]       O progresso aparece abaixo:"
    echo ""

    # Start ollama serve temporarily
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    sleep 3

    # Pull with visible progress (ollama pull shows % in real-time)
    if ollama pull mistral; then
        echo ""
        echo "[CIOS] ✓ Modelo Mistral instalado"
    else
        echo ""
        echo "[CIOS] ⚠ Falha ao baixar Mistral. Execute depois: ollama pull mistral"
    fi

    kill $OLLAMA_PID 2>/dev/null || true
else
    echo "[CIOS] ⚠ Ollama não disponível, modelo não baixado"
fi

echo ""
echo "[CIOS] ✓ IA local configurada"
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

    # LightDM — configure for Wayland session
    echo "[CIOS] ✓ Wayland compositor installed"

    # Ensure session desktop files exist (belt + suspenders)
    mkdir -p /usr/share/xsessions /usr/share/wayland-sessions
    cat > /usr/share/xsessions/cios-shell.desktop << 'DSKTP'
[Desktop Entry]
Name=CIOS
Comment=CIOS — AI-first desktop (Wayland)
Exec=/usr/local/bin/cios-session
Type=Application
DesktopNames=CIOS
DSKTP
    cp /usr/share/xsessions/cios-shell.desktop /usr/share/wayland-sessions/cios-shell.desktop
    echo "[CIOS] ✓ Session desktop files installed"

    # Remove DM restart block
    rm -f /usr/sbin/policy-rc.d

    # ── Configure greetd (Wayland-native display manager) ──
    mkdir -p /etc/greetd

    # Create greeter user if it doesn't exist (required by greetd)
    if ! id greeter &>/dev/null; then
        useradd -r -s /usr/sbin/nologin -d /dev/null greeter 2>/dev/null || true
        usermod -aG video greeter 2>/dev/null || true
    fi

    # Only write config if it doesn't exist (don't overwrite user customization)
    if [ ! -f /etc/greetd/config.toml ]; then
        cat > /etc/greetd/config.toml << 'GREETD'
[terminal]
vt = 1

[default_session]
command = "/usr/local/bin/cios-greeter-session"
user = "greeter"
GREETD
        echo "[CIOS] ✓ greetd configured (new install)"
    else
        echo "[CIOS] ✓ greetd config preserved (upgrade)"
    fi

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

        sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=0 vt.global_cursor_default=0 rd.udev.log_priority=3 systemd.show_status=false"/' /etc/default/grub
        sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=0/' /etc/default/grub

        if grep -q "^GRUB_TIMEOUT_STYLE" /etc/default/grub; then
            sed -i 's/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=hidden/' /etc/default/grub
        else
            echo 'GRUB_TIMEOUT_STYLE=hidden' >> /etc/default/grub
        fi

        if grep -q "^GRUB_DISABLE_OS_PROBER" /etc/default/grub; then
            sed -i 's/^GRUB_DISABLE_OS_PROBER=.*/GRUB_DISABLE_OS_PROBER=true/' /etc/default/grub
        else
            echo 'GRUB_DISABLE_OS_PROBER=true' >> /etc/default/grub
        fi

        if grep -q "^GRUB_RECORDFAIL_TIMEOUT" /etc/default/grub; then
            sed -i 's/^GRUB_RECORDFAIL_TIMEOUT=.*/GRUB_RECORDFAIL_TIMEOUT=2/' /etc/default/grub
        else
            echo 'GRUB_RECORDFAIL_TIMEOUT=2' >> /etc/default/grub
        fi

        update-grub 2>/dev/null || true
        echo "[CIOS] ✓ GRUB invisible (0s timeout, silent kernel)"
    fi

    # Disable other DMs (lightdm, gdm, sddm)
    for dm in lightdm gdm gdm3 sddm; do
        systemctl disable "$dm" 2>/dev/null || true
    done
    systemctl enable greetd 2>/dev/null || true

    # Ensure system boots to graphical target
    systemctl set-default graphical.target 2>/dev/null || true

    # Customize /etc/os-release to show CIOS identity
    if [ ! -f /etc/os-release.bak.cios ]; then
        cp /etc/os-release /etc/os-release.bak.cios
    fi
    cat > /etc/os-release << 'OSREL'
PRETTY_NAME="CIOS 1.1"
NAME="CIOS"
VERSION_ID="1.1"
VERSION="1.1 (Wayland)"
ID=cios
ID_LIKE=debian
HOME_URL="https://github.com/damnhalfling/CIOS"
BUG_REPORT_URL="https://github.com/damnhalfling/CIOS/issues"
OSREL
    echo "[CIOS] ✓ /etc/os-release customized"

    # Ensure all non-root users are in video/render/input groups (DRM access)
    for user in $(awk -F: '$3 >= 1000 && $3 < 65000 {print $1}' /etc/passwd); do
        usermod -aG video,render,input "$user" 2>/dev/null || true
    done
    echo "[CIOS] ✓ Users added to video/render/input groups"

    echo ""
    echo "═══════════════════════════════════════════"
    echo "  ✓ Substituição completa configurada!"
    echo ""
    echo "  Boot: logo CIOS (Plymouth)"
    echo "  Login: greetd (texto) → CIOS (Wayland)"
    echo "  Desktop: CIOS (Wayland compositor)"
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
    echo "  (Sessão Wayland com compositor próprio)"
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
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/ui/gtk"
cp -r cios/ui/gtk/*.py "${PKG_DIR}${INSTALL_DIR}/cios/ui/gtk/"
cp -r cios/infra/*.py "${PKG_DIR}${INSTALL_DIR}/cios/infra/"
cp -r cios/skills/*.py "${PKG_DIR}${INSTALL_DIR}/cios/skills/"

# ── Install compositor binary ──
echo "→ Installing cios-shell compositor..."
cp shell/build/cios-shell "${PKG_DIR}/usr/bin/cios-shell"
chmod 755 "${PKG_DIR}/usr/bin/cios-shell"

# ── Bundle ALL shared library dependencies not in base system ──
# Use ldd to find every lib cios-shell needs, bundle non-standard ones
echo "→ Bundling cios-shell runtime dependencies..."
mkdir -p "${PKG_DIR}/usr/lib/cios"

# List of libs that are ALWAYS in a base Debian/Ubuntu install (skip these)
# Also skip X11/xcb base libs that the display manager needs untouched
BASE_LIBS="linux-vdso|ld-linux|libc\.so|libm\.so|libdl\.so|libpthread|librt\.so|libstdc\+\+|libgcc_s|libX11\.so|libxcb\.so|libglib-2\.0|libgio-2\.0|libgobject-2\.0|libgmodule-2\.0|libffi\.so|libpcre2|libsystemd|libudev|libcap\.so|libgpg-error|libgcrypt|liblz4|liblzma|libzstd|libexpat"

# Get all linked libs and bundle the non-base ones
ldd "${PKG_DIR}/usr/bin/cios-shell" | grep "=> /" | awk '{print $3}' | while read -r lib; do
    libname=$(basename "$lib")
    # Skip base system libs
    if echo "$libname" | grep -qE "$BASE_LIBS"; then
        continue
    fi
    # Copy lib (follow symlinks to get the real file)
    if [ -f "$lib" ]; then
        cp -L "$lib" "${PKG_DIR}/usr/lib/cios/$libname"
    fi
done

echo "→ Bundled libs:"
ls "${PKG_DIR}/usr/lib/cios/"

# ── Set RPATH on cios-shell so it finds bundled libs WITHOUT global ldconfig ──
# This avoids polluting the system linker cache (which broke LightDM)
if command -v patchelf &>/dev/null; then
    patchelf --set-rpath '/usr/lib/cios' "${PKG_DIR}/usr/bin/cios-shell"
    echo "→ ✓ RPATH set on cios-shell"
else
    echo "→ ⚠ patchelf not found, will rely on LD_LIBRARY_PATH in cios-session"
fi

# ── Session files ──
echo "→ Copying session files..."

# Desktop entry in BOTH locations (xsessions for LightDM, wayland-sessions for GDM/SDDM)
mkdir -p "${PKG_DIR}/usr/share/xsessions"
cat > "${PKG_DIR}/usr/share/wayland-sessions/cios-shell.desktop" << 'WSESSION'
[Desktop Entry]
Name=CIOS
Comment=CIOS — AI-first desktop (Wayland)
Exec=/usr/local/bin/cios-session
Type=Application
DesktopNames=CIOS
WSESSION
cp "${PKG_DIR}/usr/share/wayland-sessions/cios-shell.desktop" "${PKG_DIR}/usr/share/xsessions/cios-shell.desktop"

# Greeter session — launched by greetd to show login screen
cat > "${PKG_DIR}/usr/local/bin/cios-greeter-session" << 'GREETER_SESSION'
#!/bin/bash
# CIOS Greeter Session — starts compositor with greeter as runtime
# greetd launches this; the greeter authenticates and tells greetd
# to start the real user session (cios-session).

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export XDG_SESSION_TYPE=wayland
export GDK_BACKEND=wayland
export WLR_NO_HARDWARE_CURSORS=1
export XKB_DEFAULT_LAYOUT="${XKB_DEFAULT_LAYOUT:-us}"
export LD_LIBRARY_PATH="/usr/lib/cios:${LD_LIBRARY_PATH:-}"
export PATH="/usr/bin:/usr/local/bin:/bin:/usr/sbin:/sbin:$PATH"
export PYTHONPATH="/usr/share/cios:${PYTHONPATH:-}"

# Launch compositor with greeter as the runtime
exec /usr/bin/cios-shell --runtime "/usr/share/cios/.venv/bin/python3 -m cios.ui.gtk.greeter"
GREETER_SESSION
chmod 755 "${PKG_DIR}/usr/local/bin/cios-greeter-session"

# Session script — launched by greetd after login
cat > "${PKG_DIR}/usr/local/bin/cios-session" << 'SESSION'
#!/bin/bash
# CIOS Session — Wayland compositor launcher
# Launched by greetd on VT1 with proper seat/session access.

export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export XDG_SESSION_TYPE=wayland
export GDK_BACKEND=wayland
export PATH="/usr/bin:/usr/local/bin:/bin:/usr/sbin:/sbin:$PATH"
export NO_AT_BRIDGE=1
export GTK_A11Y=none

# Use software cursor (fixes inverted/offset cursor in VMs)
export WLR_NO_HARDWARE_CURSORS=1

# Keyboard layout (ensures correct mapping in VMs and real hardware)
export XKB_DEFAULT_LAYOUT="${XKB_DEFAULT_LAYOUT:-us}"

# Ensure bundled libs in /usr/lib/cios are findable
export LD_LIBRARY_PATH="/usr/lib/cios:${LD_LIBRARY_PATH:-}"

LOGFILE="$HOME/.cios/session.log"
mkdir -p "$HOME/.cios"

echo "=== CIOS session starting $(date) ===" >> "$LOGFILE"
echo "  USER=$(whoami) UID=$(id -u) GROUPS=$(groups)" >> "$LOGFILE"
echo "  XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" >> "$LOGFILE"
echo "  TTY=$(tty 2>/dev/null || echo unknown)" >> "$LOGFILE"

# Find Python — try venv first, then system
VENV="/usr/share/cios/.venv/bin/python3"
if [ ! -x "$VENV" ]; then
    VENV=$(which python3 2>/dev/null)
    echo "WARNING: venv not found, using system python: $VENV" >> "$LOGFILE"
fi

# Verify venv has GTK4 (gi) access — essential for Wayland UI
if [ -x "/usr/share/cios/.venv/bin/python3" ]; then
    if ! /usr/share/cios/.venv/bin/python3 -c "import gi" 2>/dev/null; then
        echo "WARNING: gi not available in venv, falling back to system python" >> "$LOGFILE"
        VENV=$(which python3 2>/dev/null)
    fi
fi

if [ -z "$VENV" ]; then
    echo "FATAL: No python3 found!" >> "$LOGFILE"
    exit 1
fi

export PYTHONPATH="/usr/share/cios:${PYTHONPATH:-}"

if ! $VENV -c "import cios" 2>/dev/null; then
    echo "FATAL: Cannot import cios module" >> "$LOGFILE"
    $VENV -c "import cios" >> "$LOGFILE" 2>&1
    exit 1
fi

# ── Launch Wayland compositor ──
CRASH_COUNT=0
while true; do
    echo "Starting cios-shell at $(date)" >> "$LOGFILE"

    /usr/bin/cios-shell --runtime "$VENV -m cios.main" >> "$LOGFILE" 2>&1
    EXIT_CODE=$?

    echo "cios-shell exited with code $EXIT_CODE at $(date)" >> "$LOGFILE"

    if [ $EXIT_CODE -eq 0 ]; then
        break
    fi

    CRASH_COUNT=$((CRASH_COUNT + 1))
    if [ $CRASH_COUNT -ge 3 ]; then
        echo "Too many crashes ($CRASH_COUNT), giving up" >> "$LOGFILE"
        break
    fi

    sleep 1
done

echo "=== Session ended $(date) ===" >> "$LOGFILE"
SESSION
chmod 755 "${PKG_DIR}/usr/local/bin/cios-session"

# ── cios-setup-ai: installs heavy AI components after first login ──
cat > "${PKG_DIR}/usr/local/bin/cios-setup-ai" << 'SETUPAI'
#!/bin/bash
# CIOS — Install AI components (Ollama + model + Whisper + Piper)
# Run with: sudo cios-setup-ai
# Automatically triggered on first login if not yet done.
set -e

MARKER="/usr/share/cios/.ai-setup-done"

if [ -f "$MARKER" ]; then
    echo "[CIOS] AI components already installed."
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "[CIOS] Requires sudo: sudo cios-setup-ai"
    exit 1
fi

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║  CIOS — Installing AI Components         ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# ── Ollama ──
if ! command -v ollama &>/dev/null; then
    echo "[1/4] Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh || {
        echo "  ⚠ Failed. Install manually: curl -fsSL https://ollama.com/install.sh | sh"
    }
else
    echo "[1/4] Ollama already installed ✓"
fi

# ── Mistral model ──
if command -v ollama &>/dev/null; then
    echo "[2/4] Downloading Mistral model (~4GB)..."
    ollama serve &>/dev/null &
    SERVE_PID=$!
    sleep 3
    ollama pull mistral || echo "  ⚠ Failed. Run manually: ollama pull mistral"
    kill $SERVE_PID 2>/dev/null || true
else
    echo "[2/4] Skipped (Ollama not available)"
fi

# ── Piper TTS ──
if ! command -v piper &>/dev/null; then
    echo "[3/4] Installing Piper TTS..."
    PIPER_VERSION="2023.11.14-2"
    PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz"
    if curl -fsSL "$PIPER_URL" -o /tmp/piper.tar.gz; then
        tar -xzf /tmp/piper.tar.gz -C /usr/local/bin/ --strip-components=1 piper/piper 2>/dev/null || true
        rm -f /tmp/piper.tar.gz
        mkdir -p /usr/share/piper/voices
        VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
        curl -fsSL "$VOICE_URL" -o /usr/share/piper/voices/pt_BR-faber-medium.onnx 2>/dev/null || true
        curl -fsSL "${VOICE_URL}.json" -o /usr/share/piper/voices/pt_BR-faber-medium.onnx.json 2>/dev/null || true
        echo "  ✓ Piper TTS installed"
    else
        echo "  ⚠ Failed to download Piper"
    fi
else
    echo "[3/4] Piper already installed ✓"
fi

# ── Whisper STT ──
if ! command -v whisper &>/dev/null; then
    echo "[4/4] Installing Whisper STT..."
    if [ -d /usr/share/cios/.venv ]; then
        /usr/share/cios/.venv/bin/pip install --quiet openai-whisper && {
            ln -sf /usr/share/cios/.venv/bin/whisper /usr/local/bin/whisper 2>/dev/null || true
            echo "  ✓ Whisper installed"
        } || echo "  ⚠ Failed. Run: /usr/share/cios/.venv/bin/pip install openai-whisper"
    fi
else
    echo "[4/4] Whisper already installed ✓"
fi

# Mark as done
touch "$MARKER"

echo ""
echo "═══════════════════════════════════════════"
echo "  ✓ AI components installed!"
echo "  Restart CIOS session to activate."
echo "═══════════════════════════════════════════"
echo ""
SETUPAI
chmod 755 "${PKG_DIR}/usr/local/bin/cios-setup-ai"

# ── greetd config (bundled) ──
echo "→ Bundling greetd config..."

cat > "${PKG_DIR}${INSTALL_DIR}/config/greetd.toml" << 'GREETD'
[terminal]
vt = 1

[default_session]
command = "/usr/sbin/agreety --cmd /usr/local/bin/cios-session"
user = "greeter"
GREETD

# ── Logo for greeter ──
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
elif [ -f assets/background.jpg ]; then
    cp assets/background.jpg "${PKG_DIR}/usr/share/backgrounds/cios.jpg"
else
    echo "→ Generating placeholder background..."
    python3 assets/generate_background.py 2>/dev/null || true
    if [ -f assets/background.png ]; then
        cp assets/background.png "${PKG_DIR}/usr/share/backgrounds/cios.png"
    else
        echo "  ⚠ Could not generate background (non-critical)"
    fi
fi

# ── Fix permissions (ensure no root-owned files inside package) ──
echo "→ Fixing file permissions..."
find "${PKG_DIR}" -type d -exec chmod 755 {} \;
find "${PKG_DIR}" -type f -exec chmod 644 {} \;
chmod 755 "${PKG_DIR}/DEBIAN/preinst" "${PKG_DIR}/DEBIAN/postinst" "${PKG_DIR}/DEBIAN/prerm" 2>/dev/null || true
find "${PKG_DIR}/usr/bin" -type f -exec chmod 755 {} \; 2>/dev/null || true
find "${PKG_DIR}/usr/local/bin" -type f -exec chmod 755 {} \; 2>/dev/null || true

# ── Build .deb ──
echo "→ Building .deb..."
if command -v fakeroot &>/dev/null; then
    fakeroot dpkg-deb --build "${PKG_DIR}"
else
    dpkg-deb --build "${PKG_DIR}"
fi

# ── Cleanup ──
rm -rf "${PKG_DIR}"

echo ""
echo "═══════════════════════════════════════════"
echo "  ✓ Built: ${PKG_DIR}.deb"
echo "═══════════════════════════════════════════"
echo ""
echo "  Install:"
echo "    cp ${PKG_DIR}.deb /tmp/"
echo "    sudo apt install /tmp/${PKG_DIR}.deb"
echo "    sudo reboot"
echo ""
