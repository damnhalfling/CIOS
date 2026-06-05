#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  CIOS — Build .deb package
#  Usage: bash build-deb.sh [VERSION]
#  Example: bash build-deb.sh 2.0.0-rc5
#
#  REQUIREMENTS (all mandatory, no fallbacks):
#    - cios-shell compiles (wlroots + build deps)
#    - Python modules present (cios/, ui/, core/)
#    - Plymouth theme present
#    - Assets present (logo, background)
#
#  If any requirement fails, the build ABORTS.
#  A broken .deb is worse than no .deb.
# ═══════════════════════════════════════════════════
set -euo pipefail

VERSION="${1:-2.0.0-rc5}"
PKG_NAME="cios"
PKG_DIR="${PKG_NAME}_${VERSION}_amd64"
INSTALL_DIR="/usr/share/cios"

# ── Helper: fatal error ──
fatal() {
    echo ""
    echo "══════════════════════════════════════════════════════════"
    echo "  ✗ FATAL: $1"
    echo ""
    if [ -n "${2:-}" ]; then
        echo "  $2"
        echo ""
    fi
    echo "══════════════════════════════════════════════════════════"
    echo ""
    exit 1
}

# ── Ensure fakeroot is available ──
if ! command -v fakeroot &>/dev/null; then
    echo "⚠ fakeroot not found. Installing..."
    sudo apt-get install -y fakeroot
fi

echo "╔═══════════════════════════════════════════╗"
echo "║  CIOS — Building .deb v${VERSION}        ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# ══════════════════════════════════════════════════
#  PHASE 1: Validate all requirements BEFORE building
# ══════════════════════════════════════════════════

echo "→ Validating requirements..."

# 1. Shell source must exist
[ -d shell ] || fatal "shell/ directory not found." "Cannot build without the Wayland compositor source."

# 2. Python modules must exist
[ -f cios/__init__.py ] || fatal "cios/ Python package not found."
[ -d cios/core ] || fatal "cios/core/ not found."
[ -d cios/ui ] || fatal "cios/ui/ not found."
[ -d cios/ui/gtk ] || fatal "cios/ui/gtk/ not found (greeter)."

# 3. Plymouth theme must exist
[ -d plymouth/cios ] || fatal "plymouth/cios/ theme not found."
[ -f plymouth/cios/cios.plymouth ] || fatal "plymouth/cios/cios.plymouth not found."
[ -f plymouth/cios/cios.script ] || fatal "plymouth/cios/cios.script not found."

# 4. Logo must exist
[ -f assets/cios_logo.png ] || fatal "assets/cios_logo.png not found."

echo "  ✓ All source files present"
echo ""

# ══════════════════════════════════════════════════
#  PHASE 2: Build compositor (mandatory)
# ══════════════════════════════════════════════════

echo "→ Building CIOS Shell (Wayland compositor)..."
export PKG_CONFIG_PATH="/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig:${PKG_CONFIG_PATH:-}"

pushd shell > /dev/null
rm -rf build

if ! meson setup build --prefix=/usr 2>&1; then
    popd > /dev/null
    fatal "meson setup failed for cios-shell." \
        "Install build deps: sudo apt install libwlroots-dev libwayland-dev libxkbcommon-dev libinput-dev libseat-dev libpixman-1-dev libdrm-dev libgbm-dev libegl-dev libgles-dev meson ninja-build"
fi

if ! ninja -C build 2>&1; then
    popd > /dev/null
    fatal "ninja build failed for cios-shell." \
        "Check compiler errors above."
fi

popd > /dev/null

[ -f shell/build/cios-shell ] || fatal "cios-shell binary not found after build."
echo "  ✓ cios-shell compiled"
echo ""

# ══════════════════════════════════════════════════
#  PHASE 3: Assemble .deb package
# ══════════════════════════════════════════════════

echo "→ Assembling package..."

# ── Clean previous build ──
rm -rf "${PKG_DIR}" "${PKG_DIR}.deb"

# ── Create directory structure ──
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/core/handlers"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/ui/gtk"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/infra"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/cios/skills"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/assets"
mkdir -p "${PKG_DIR}${INSTALL_DIR}/config"
mkdir -p "${PKG_DIR}/usr/local/bin"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/lib/cios"
mkdir -p "${PKG_DIR}/usr/share/wayland-sessions"
mkdir -p "${PKG_DIR}/usr/share/plymouth/themes/cios"
mkdir -p "${PKG_DIR}/usr/share/backgrounds"
mkdir -p "${PKG_DIR}/usr/share/pixmaps"
mkdir -p "${PKG_DIR}/etc/ld.so.conf.d"

# ── Register bundled libs with the system linker ──
echo "/usr/lib/cios" > "${PKG_DIR}/etc/ld.so.conf.d/cios.conf"

# ── DEBIAN/control ──
cat > "${PKG_DIR}/DEBIAN/control" << EOF
Package: cios
Version: ${VERSION}
Section: x11
Priority: optional
Architecture: amd64
Depends: python3 (>= 3.10), python3-pip, python3-venv, python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, gir1.2-pango-1.0, sudo, libxkbcommon0, libinput10, libseat1, seatd, libpixman-1-0, libdrm2, libgles2, libegl1, libgbm1, libcap2, plymouth, curl, network-manager, pipewire, pipewire-pulse, foot, gnome-keyring, libpam-gnome-keyring
Recommends: xwayland, wl-clipboard
Conflicts: lightdm, gdm3, sddm
Provides: x-display-manager
Maintainer: damnhalfling <damnhalfling@github.com>
Description: CIOS — AI-first operating system (Wayland)
 An AI-first desktop that replaces apps with intent-driven
 execution. Speak intent, get results.
 .
 Core stack: custom Wayland compositor (cios-shell/wlroots),
 greetd login, Ollama LLM (auto-selected), Whisper STT, Piper TTS.
 .
 This is NOT a session to run alongside GNOME/KDE.
 CIOS replaces the entire desktop environment.
Homepage: https://github.com/damnhalfling/cios
EOF

# ── DEBIAN/preinst ──
cat > "${PKG_DIR}/DEBIAN/preinst" << 'PREINST'
#!/bin/bash
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

# Clean pycache
find /usr/share/cios -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Remove previous venv on upgrade
if dpkg -s cios >/dev/null 2>&1; then
    PREV_VER=$(dpkg-query -W -f='${Version}' cios 2>/dev/null || echo "unknown")
    echo "[CIOS] Upgrading from ${PREV_VER}..."
    rm -rf /usr/share/cios/.venv
fi

exit 0
PREINST
chmod 755 "${PKG_DIR}/DEBIAN/preinst"

# ── DEBIAN/postinst ──
cat > "${PKG_DIR}/DEBIAN/postinst" << 'POSTINST'
#!/bin/bash
# CIOS postinst — full system setup. No modes, no fallbacks.
# CIOS IS the desktop. Period.
set -e
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"
export DEBIAN_FRONTEND=noninteractive

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║       CIOS — Installing                  ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# ── Register bundled shared libraries ──
ldconfig 2>/dev/null || true

# ══════════════════════════════════════════════════
#  1. Python environment
# ══════════════════════════════════════════════════

echo "[CIOS] [1/6] Python environment..."

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)

# Ensure python3-tk
if ! python3 -c "import tkinter" 2>/dev/null; then
    apt-get install -y python3-tk 2>/dev/null || true
    [ -n "$PY_VER" ] && apt-get install -y "python${PY_VER}-tk" 2>/dev/null || true
fi

# Create venv
python3 -m venv --system-site-packages /usr/share/cios/.venv || \
    fatal_postinst "Could not create Python venv"

# Verify gi access
if ! /usr/share/cios/.venv/bin/python3 -c "import gi" 2>/dev/null; then
    rm -rf /usr/share/cios/.venv
    python3 -m venv --system-site-packages /usr/share/cios/.venv
fi

/usr/share/cios/.venv/bin/pip install \
    prompt_toolkit==3.0.48 \
    rich==13.9.4 \
    psutil==6.1.1 \
    Pillow \
    qrcode \
    requests \
    beautifulsoup4 \
    pymupdf

/usr/share/cios/.venv/bin/pip install -e /usr/share/cios

echo "[CIOS] ✓ Python environment ready"

# ══════════════════════════════════════════════════
#  2. greetd + session (CRITICAL — must complete for boot)
# ══════════════════════════════════════════════════

echo "[CIOS] [2/6] Display manager (greetd)..."

# Kill and disable any other DM — they conflict with CIOS
for dm in lightdm gdm gdm3 sddm; do
    systemctl stop "$dm" 2>/dev/null || true
    systemctl disable "$dm" 2>/dev/null || true
    # Remove them to prevent apt from pulling X11 back
    apt-get remove -y "$dm" 2>/dev/null || true
done

# Remove X11 packages that may have been pulled as dependencies
apt-get autoremove -y 2>/dev/null || true

# Create greeter user
if ! id greeter &>/dev/null; then
    useradd -r -s /usr/sbin/nologin -d /tmp greeter 2>/dev/null || true
fi
usermod -aG video,render greeter 2>/dev/null || true

# Write greetd config
mkdir -p /etc/greetd
cat > /etc/greetd/config.toml << 'GREETD'
[terminal]
vt = 1

[default_session]
command = "/usr/local/bin/cios-greeter-session"
user = "greeter"
GREETD

# Enable greetd, disable getty on tty1
systemctl enable greetd 2>/dev/null || true
systemctl disable getty@tty1.service 2>/dev/null || true
systemctl mask getty@tty1.service 2>/dev/null || true
systemctl set-default graphical.target 2>/dev/null || true

# Ensure users have DRM + sudo access
for user in $(awk -F: '$3 >= 1000 && $3 < 65000 {print $1}' /etc/passwd); do
    usermod -aG video,render,input,sudo "$user" 2>/dev/null || true
done

echo "[CIOS] ✓ greetd configured (Wayland-only)"

# ══════════════════════════════════════════════════
#  3. Plymouth + GRUB (boot experience)
# ══════════════════════════════════════════════════

echo "[CIOS] [3/6] Boot experience (Plymouth + GRUB)..."

# Plymouth — universal approach (works on Ubuntu, Debian, Fedora)
CIOS_PLYMOUTH="/usr/share/plymouth/themes/cios/cios.plymouth"
if [ -f "$CIOS_PLYMOUTH" ]; then
    # Method 1: plymouth-set-default-theme (Debian/Ubuntu with plymouth-themes)
    if command -v plymouth-set-default-theme &>/dev/null; then
        plymouth-set-default-theme cios 2>/dev/null || true
    fi

    # Method 2: update-alternatives (Ubuntu 24.04+)
    if command -v update-alternatives &>/dev/null; then
        update-alternatives --install /usr/share/plymouth/themes/default.plymouth \
            default.plymouth "$CIOS_PLYMOUTH" 200 2>/dev/null || true
        update-alternatives --set default.plymouth "$CIOS_PLYMOUTH" 2>/dev/null || true
    fi

    # Method 3: direct config (fallback for any distro)
    mkdir -p /etc/plymouth
    printf "[Daemon]\nTheme=cios\n" > /etc/plymouth/plymouthd.conf
fi

mkdir -p /etc/initramfs-tools/conf.d
echo "FRAMEBUFFER=y" > /etc/initramfs-tools/conf.d/cios-splash

INITRAMFS_MODULES="/etc/initramfs-tools/modules"
for mod in drm drm_kms_helper i915 amdgpu nouveau radeon; do
    grep -q "^${mod}$" "$INITRAMFS_MODULES" 2>/dev/null || echo "$mod" >> "$INITRAMFS_MODULES"
done

update-initramfs -u 2>/dev/null || true

# GRUB: invisible, silent
if [ -f /etc/default/grub ]; then
    [ ! -f /etc/default/grub.bak.cios ] && cp /etc/default/grub /etc/default/grub.bak.cios

    sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=0 vt.global_cursor_default=0 rd.udev.log_priority=3 systemd.show_status=false"/' /etc/default/grub
    sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=0/' /etc/default/grub

    grep -q "^GRUB_TIMEOUT_STYLE" /etc/default/grub && \
        sed -i 's/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=hidden/' /etc/default/grub || \
        echo 'GRUB_TIMEOUT_STYLE=hidden' >> /etc/default/grub

    grep -q "^GRUB_DISABLE_OS_PROBER" /etc/default/grub && \
        sed -i 's/^GRUB_DISABLE_OS_PROBER=.*/GRUB_DISABLE_OS_PROBER=true/' /etc/default/grub || \
        echo 'GRUB_DISABLE_OS_PROBER=true' >> /etc/default/grub

    grep -q "^GRUB_RECORDFAIL_TIMEOUT" /etc/default/grub && \
        sed -i 's/^GRUB_RECORDFAIL_TIMEOUT=.*/GRUB_RECORDFAIL_TIMEOUT=2/' /etc/default/grub || \
        echo 'GRUB_RECORDFAIL_TIMEOUT=2' >> /etc/default/grub

    update-grub 2>/dev/null || true
fi

echo "[CIOS] ✓ Boot configured"

# ══════════════════════════════════════════════════
#  4-6. AI + Voice (OPTIONAL — failures don't break install)
# ══════════════════════════════════════════════════

echo "[CIOS] [4/6] AI backend (Ollama + auto-selected model)..."

# Run hardware-aware model selection (non-fatal)
if [ -x /usr/local/bin/cios-setup-ai ]; then
    /usr/local/bin/cios-setup-ai || echo "[CIOS] ⚠ AI setup had issues (non-fatal). Run: sudo cios-setup-ai"
else
    echo "[CIOS] ⚠ cios-setup-ai not found, skipping AI setup"
fi

echo "[CIOS] [5/6] Piper TTS (opcional)..."

if ! command -v piper &>/dev/null; then
    PIPER_VERSION="2023.11.14-2"
    PIPER_URL="https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz"
    curl -fsSL "$PIPER_URL" -o /tmp/piper.tar.gz && {
        tar -xzf /tmp/piper.tar.gz -C /usr/local/bin/ --strip-components=1 piper/piper
        rm -f /tmp/piper.tar.gz
        mkdir -p /usr/share/piper/voices
        VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
        curl -fsSL "$VOICE_URL" -o /usr/share/piper/voices/pt_BR-faber-medium.onnx || true
        curl -fsSL "${VOICE_URL}.json" -o /usr/share/piper/voices/pt_BR-faber-medium.onnx.json || true
        echo "[CIOS] ✓ Piper TTS ready"
    } || echo "[CIOS] ⚠ Piper não instalado (não afeta o sistema)"
else
    echo "[CIOS] ✓ Piper já instalado"
fi

echo "[CIOS] [6/6] Whisper STT (opcional)..."

if ! command -v whisper &>/dev/null; then
    /usr/share/cios/.venv/bin/pip install --no-cache-dir openai-whisper 2>/dev/null && {
        ln -sf /usr/share/cios/.venv/bin/whisper /usr/local/bin/whisper
        echo "[CIOS] ✓ Whisper STT ready"
    } || echo "[CIOS] ⚠ Whisper não instalado (não afeta o sistema)"
else
    echo "[CIOS] ✓ Whisper já instalado"
fi

# ══════════════════════════════════════════════════
#  OS Identity
# ══════════════════════════════════════════════════

[ ! -f /etc/os-release.bak.cios ] && cp /etc/os-release /etc/os-release.bak.cios
CIOS_VER=$(dpkg-query -W -f='${Version}' cios 2>/dev/null || echo "2.0")
cat > /etc/os-release << OSREL
PRETTY_NAME="CIOS ${CIOS_VER}"
NAME="CIOS"
VERSION_ID="${CIOS_VER}"
VERSION="${CIOS_VER} (Wayland)"
ID=cios
ID_LIKE=debian
HOME_URL="https://github.com/damnhalfling/CIOS"
BUG_REPORT_URL="https://github.com/damnhalfling/CIOS/issues"
OSREL

echo ""
echo "═══════════════════════════════════════════"
echo "  ✓ CIOS ${CIOS_VER} installed"
echo ""
echo "  Stack:"
echo "    Compositor: cios-shell (Wayland/wlroots)"
echo "    Login:      greetd"
echo "    LLM:        Ollama (hardware-aware model)"
echo "    STT:        Whisper"
echo "    TTS:        Piper"
echo "    Boot:       Plymouth (CIOS theme)"
echo ""
echo "  sudo reboot"
echo "═══════════════════════════════════════════"
echo ""

exit 0
POSTINST
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

# ── DEBIAN/prerm ──
cat > "${PKG_DIR}/DEBIAN/prerm" << 'PRERM'
#!/bin/bash
set -e
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

echo "[CIOS] Removing..."

# Restore Plymouth
if command -v plymouth-set-default-theme &>/dev/null; then
    CURRENT_THEME=$(plymouth-set-default-theme 2>/dev/null || echo "")
    if [ "$CURRENT_THEME" = "cios" ]; then
        plymouth-set-default-theme -R spinner 2>/dev/null || true
    fi
fi

# Remove initramfs config
rm -f /etc/initramfs-tools/conf.d/cios-splash
INITRAMFS_MODULES="/etc/initramfs-tools/modules"
if [ -f "$INITRAMFS_MODULES" ]; then
    for mod in drm drm_kms_helper i915 amdgpu nouveau radeon; do
        sed -i "/^${mod}$/d" "$INITRAMFS_MODULES" 2>/dev/null || true
    done
fi
update-initramfs -u 2>/dev/null || true

# Restore GRUB
if [ -f /etc/default/grub.bak.cios ]; then
    mv /etc/default/grub.bak.cios /etc/default/grub
    update-grub 2>/dev/null || true
fi

# Restore os-release
if [ -f /etc/os-release.bak.cios ]; then
    mv /etc/os-release.bak.cios /etc/os-release
fi

# Re-enable getty, disable greetd
systemctl unmask getty@tty1.service 2>/dev/null || true
systemctl enable getty@tty1.service 2>/dev/null || true
systemctl disable greetd 2>/dev/null || true
systemctl set-default multi-user.target 2>/dev/null || true

# Clean venv
rm -rf /usr/share/cios/.venv

echo "[CIOS] Removed. System restored to base Debian."
echo "[CIOS] Reboot to complete: sudo reboot"
PRERM
chmod 755 "${PKG_DIR}/DEBIAN/prerm"

# ══════════════════════════════════════════════════
#  Copy application files
# ══════════════════════════════════════════════════

echo "→ Copying application files..."

# Python modules
cp pyproject.toml "${PKG_DIR}${INSTALL_DIR}/"
cp -r cios/*.py "${PKG_DIR}${INSTALL_DIR}/cios/"
cp -r cios/core/*.py "${PKG_DIR}${INSTALL_DIR}/cios/core/"
cp -r cios/core/handlers/*.py "${PKG_DIR}${INSTALL_DIR}/cios/core/handlers/"
cp -r cios/ui/*.py "${PKG_DIR}${INSTALL_DIR}/cios/ui/"
cp -r cios/ui/gtk/*.py "${PKG_DIR}${INSTALL_DIR}/cios/ui/gtk/"
cp -r cios/infra/*.py "${PKG_DIR}${INSTALL_DIR}/cios/infra/"
cp -r cios/skills/*.py "${PKG_DIR}${INSTALL_DIR}/cios/skills/"

# ── Compositor binary + bundled libs ──
echo "→ Installing cios-shell compositor..."
cp shell/build/cios-shell "${PKG_DIR}/usr/bin/cios-shell"
chmod 755 "${PKG_DIR}/usr/bin/cios-shell"

# ── Bundle greetd binary (not in Debian repos) ──
echo "→ Bundling greetd..."
if command -v greetd &>/dev/null; then
    cp "$(which greetd)" "${PKG_DIR}/usr/bin/greetd"
    chmod 755 "${PKG_DIR}/usr/bin/greetd"
elif [ -f /usr/bin/greetd ]; then
    cp /usr/bin/greetd "${PKG_DIR}/usr/bin/greetd"
    chmod 755 "${PKG_DIR}/usr/bin/greetd"
else
    echo "  → greetd not found locally, will build from source..."
    if command -v cargo &>/dev/null; then
        cargo install greetd --root /tmp/greetd-build 2>/dev/null && \
            cp /tmp/greetd-build/bin/greetd "${PKG_DIR}/usr/bin/greetd" && \
            chmod 755 "${PKG_DIR}/usr/bin/greetd" || \
            fatal "Cannot build greetd. Install cargo or provide greetd binary."
    else
        fatal "greetd not found and cargo not available to build it." \
            "Install greetd: cargo install greetd, or apt install greetd from a third-party repo."
    fi
fi

# ── Bundle greetd systemd unit ──
mkdir -p "${PKG_DIR}/usr/lib/systemd/system"
cat > "${PKG_DIR}/usr/lib/systemd/system/greetd.service" << 'GREETD_UNIT'
[Unit]
Description=greetd login manager
Documentation=man:greetd(1)
After=systemd-user-sessions.service plymouth-quit-wait.service
After=getty@tty1.service
Conflicts=getty@tty1.service

[Service]
Type=idle
ExecStart=/usr/bin/greetd
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=30
StartLimitBurst=3

[Install]
Alias=display-manager.service
WantedBy=graphical.target
GREETD_UNIT

# ── PAM config for greetd (required for authentication) ──
mkdir -p "${PKG_DIR}/etc/pam.d"
cat > "${PKG_DIR}/etc/pam.d/greetd" << 'GREETD_PAM'
#%PAM-1.0
auth       include   login
auth       optional  pam_gnome_keyring.so

account    include   login

password   include   login

session    include   login
session    optional  pam_gnome_keyring.so auto_start
GREETD_PAM

# ── Override plymouth-quit-wait to not block forever ──
mkdir -p "${PKG_DIR}/etc/systemd/system/plymouth-quit-wait.service.d"
cat > "${PKG_DIR}/etc/systemd/system/plymouth-quit-wait.service.d/timeout.conf" << 'PLYTIMEOUT'
[Service]
TimeoutStartSec=15
PLYTIMEOUT

echo "→ Bundling runtime libraries..."
# Exclude base system libs AND GPU/EGL/Wayland libs (must use system versions for hardware compatibility)
BASE_LIBS="linux-vdso|ld-linux|libc\.so|libm\.so|libdl\.so|libpthread|librt\.so|libstdc\+\+|libgcc_s|libX11\.so|libxcb\.so|libglib-2\.0|libgio-2\.0|libgobject-2\.0|libgmodule-2\.0|libffi\.so|libpcre2|libsystemd|libudev|libcap\.so|libgpg-error|libgcrypt|liblz4|liblzma|libzstd|libexpat"
GPU_LIBS="libEGL|libGLESv2|libGLdispatch|libgbm|libGL\.so|libGLX|libOpenGL|libvulkan|libdrm\.so|libwayland-server|libwayland-client"

ldd "${PKG_DIR}/usr/bin/cios-shell" | grep "=> /" | awk '{print $3}' | while read -r lib; do
    libname=$(basename "$lib")
    echo "$libname" | grep -qE "$BASE_LIBS" && continue
    echo "$libname" | grep -qE "$GPU_LIBS" && continue
    [ -f "$lib" ] && cp -L "$lib" "${PKG_DIR}/usr/lib/cios/$libname"
done

echo "  Bundled:"
ls "${PKG_DIR}/usr/lib/cios/" 2>/dev/null | head -20

# Set RPATH
if command -v patchelf &>/dev/null; then
    patchelf --set-rpath '/usr/lib/cios' "${PKG_DIR}/usr/bin/cios-shell"
    echo "  ✓ RPATH set"
fi

# ── Session files (Wayland only) ──
echo "→ Installing session files..."

cat > "${PKG_DIR}/usr/share/wayland-sessions/cios-shell.desktop" << 'WSESSION'
[Desktop Entry]
Name=CIOS
Comment=CIOS — AI-first desktop (Wayland)
Exec=/usr/local/bin/cios-session
Type=Application
DesktopNames=CIOS
WSESSION

# Greeter session (launched by greetd)
cat > "${PKG_DIR}/usr/local/bin/cios-greeter-session" << 'GREETER_SESSION'
#!/bin/bash
# CIOS Greeter — compositor + GTK4 greeter
# Launched by greetd on VT1.

export HOME=/tmp/greeter-home
mkdir -p "$HOME/.cache"
export XDG_CACHE_HOME="$HOME/.cache"
export MESA_SHADER_CACHE_DIR="$HOME/.cache/mesa"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
[ ! -d "$XDG_RUNTIME_DIR" ] && mkdir -p "$XDG_RUNTIME_DIR" && chmod 0700 "$XDG_RUNTIME_DIR"

export XDG_SESSION_TYPE=wayland
export GDK_BACKEND=wayland
export WLR_NO_HARDWARE_CURSORS=1
export WLR_RENDERER=${WLR_RENDERER:-gles2}
export WLR_RENDERER_ALLOW_SOFTWARE=${WLR_RENDERER_ALLOW_SOFTWARE:-1}
export LIBSEAT_BACKEND=seatd
export XKB_DEFAULT_LAYOUT="${XKB_DEFAULT_LAYOUT:-us}"
export LD_LIBRARY_PATH="/usr/lib/cios:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="/usr/share/cios:${PYTHONPATH:-}"

LOGFILE="/tmp/cios-greeter.log"

PYTHON="/usr/share/cios/.venv/bin/python3"
[ ! -x "$PYTHON" ] && PYTHON="python3"

exec /usr/bin/cios-shell --runtime "$PYTHON -m cios.ui.gtk.greeter" >> "$LOGFILE" 2>&1
GREETER_SESSION
chmod 755 "${PKG_DIR}/usr/local/bin/cios-greeter-session"

# User session (launched by greetd after login)
cat > "${PKG_DIR}/usr/local/bin/cios-session" << 'SESSION'
#!/bin/bash
# CIOS Session — Wayland compositor + AI runtime
# Launched by greetd after authentication.

export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export XDG_SESSION_TYPE=wayland
export GDK_BACKEND=wayland
export WLR_NO_HARDWARE_CURSORS=1
export LIBSEAT_BACKEND=seatd
export XKB_DEFAULT_LAYOUT="${XKB_DEFAULT_LAYOUT:-us}"
export LD_LIBRARY_PATH="/usr/lib/cios:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="/usr/share/cios:${PYTHONPATH:-}"
export NO_AT_BRIDGE=1
export GTK_A11Y=none

LOGFILE="$HOME/.cios/session.log"
mkdir -p "$HOME/.cios"

echo "=== CIOS session $(date) ===" >> "$LOGFILE"

# Unlock gnome-keyring (Chrome, secrets storage)
eval $(gnome-keyring-daemon --start --components=pkcs11,secrets,ssh 2>/dev/null)
export SSH_AUTH_SOCK GNOME_KEYRING_CONTROL

# Find Python
VENV="/usr/share/cios/.venv/bin/python3"
if [ ! -x "$VENV" ] || ! "$VENV" -c "import gi" 2>/dev/null; then
    VENV=$(which python3 2>/dev/null)
fi

[ -z "$VENV" ] && { echo "FATAL: No python3" >> "$LOGFILE"; exit 1; }
$VENV -c "import cios" 2>/dev/null || { echo "FATAL: Cannot import cios" >> "$LOGFILE"; exit 1; }

# Launch compositor — NO restart loop.
# If it crashes, greetd handles the restart (with its own limits).
exec /usr/bin/cios-shell --runtime "$VENV -m cios.main" >> "$LOGFILE" 2>&1
SESSION
chmod 755 "${PKG_DIR}/usr/local/bin/cios-session"

# ── greetd config (bundled reference) ──
cat > "${PKG_DIR}${INSTALL_DIR}/config/greetd.toml" << 'GREETD'
[terminal]
vt = 1

[default_session]
command = "/usr/local/bin/cios-greeter-session"
user = "greeter"
GREETD

# ── cios-setup-ai script ──
echo "→ Installing cios-setup-ai..."
cp scripts/cios-setup-ai "${PKG_DIR}/usr/local/bin/cios-setup-ai"
chmod 755 "${PKG_DIR}/usr/local/bin/cios-setup-ai"

# ── Assets ──
echo "→ Copying assets..."
cp assets/cios_logo.png "${PKG_DIR}/usr/share/pixmaps/cios-logo.png"
cp assets/cios_logo.png "${PKG_DIR}${INSTALL_DIR}/assets/cios_logo.png"

# Plymouth theme
cp plymouth/cios/cios.plymouth "${PKG_DIR}/usr/share/plymouth/themes/cios/"
cp plymouth/cios/cios.script "${PKG_DIR}/usr/share/plymouth/themes/cios/"
cp assets/cios_logo.png "${PKG_DIR}/usr/share/plymouth/themes/cios/logo.png"

# Background
if [ -f assets/background.png ]; then
    cp assets/background.png "${PKG_DIR}/usr/share/backgrounds/cios.png"
elif [ -f assets/background.jpg ]; then
    cp assets/background.jpg "${PKG_DIR}/usr/share/backgrounds/cios.jpg"
else
    echo "  ⚠ No background image (non-critical, using solid color)"
fi

# ══════════════════════════════════════════════════
#  Fix permissions + build .deb
# ══════════════════════════════════════════════════

echo "→ Fixing permissions..."
find "${PKG_DIR}" -type d -exec chmod 755 {} \;
find "${PKG_DIR}" -type f -exec chmod 644 {} \;
chmod 755 "${PKG_DIR}/DEBIAN/preinst" "${PKG_DIR}/DEBIAN/postinst" "${PKG_DIR}/DEBIAN/prerm"
find "${PKG_DIR}/usr/bin" -type f -exec chmod 755 {} \;
find "${PKG_DIR}/usr/local/bin" -type f -exec chmod 755 {} \;

echo "→ Building .deb..."
if command -v fakeroot &>/dev/null; then
    fakeroot dpkg-deb --build "${PKG_DIR}"
else
    dpkg-deb --build "${PKG_DIR}"
fi

rm -rf "${PKG_DIR}"

echo ""
echo "═══════════════════════════════════════════"
echo "  ✓ Built: ${PKG_DIR}.deb"
echo ""
echo "  This package requires internet during"
echo "  install (downloads Ollama, Mistral,"
echo "  Whisper, Piper)."
echo ""
echo "  Install:"
echo "    sudo apt install ./${PKG_DIR}.deb"
echo "    sudo reboot"
echo "═══════════════════════════════════════════"
echo ""
