#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  CIOS — One-line installer
#  Usage: sudo bash install-cios.sh [cios_*.deb]
#     or: sudo bash install-cios.sh  (auto-downloads latest)
#
#  Modes:
#    1. Session only — adds CIOS alongside GNOME/KDE
#    2. Full replacement — switches to LightDM with CIOS as default
#
#  This script prevents display manager restarts during installation.
# ═══════════════════════════════════════════════════
set -euo pipefail

export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"
export DEBIAN_FRONTEND=noninteractive

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║     CIOS — Installer           ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# Check root
if [ "$(id -u)" -ne 0 ]; then
    echo "  ✗ Run with sudo: sudo bash $0 $*"
    exit 1
fi

DEB_FILE="${1:-}"

# If no .deb provided, download latest from GitHub
if [ -z "$DEB_FILE" ]; then
    echo "  → Downloading latest release..."
    apt-get update -qq 2>/dev/null || true
    apt-get install -y -qq curl 2>/dev/null || true

    LATEST_URL=$(curl -sL -o /dev/null -w '%{url_effective}' \
        https://github.com/damnhalfling/cios/releases/latest)
    VERSION=$(basename "$LATEST_URL")
    DEB_URL="https://github.com/damnhalfling/cios/releases/download/${VERSION}/cios_${VERSION#v}_amd64.deb"

    DEB_FILE="/tmp/cios_${VERSION#v}_amd64.deb"
    echo "  → Downloading ${VERSION}..."
    curl -sL -o "$DEB_FILE" "$DEB_URL" || {
        echo "  ✗ Download failed. Get the .deb manually from:"
        echo "    https://github.com/damnhalfling/cios/releases"
        exit 1
    }
    echo "  ✓ Downloaded"
fi

if [ ! -f "$DEB_FILE" ]; then
    echo "  ✗ File not found: $DEB_FILE"
    exit 1
fi

# Move .deb to /tmp if in a restricted directory (avoids apt _apt user warning)
if ! sudo -u _apt test -r "$DEB_FILE" 2>/dev/null; then
    TMP_DEB="/tmp/$(basename "$DEB_FILE")"
    cp "$DEB_FILE" "$TMP_DEB"
    chmod 644 "$TMP_DEB"
    DEB_FILE="$TMP_DEB"
fi

# ══════════════════════════════════════════════════════════════
#  INSTALLATION MODE SELECTION
# ══════════════════════════════════════════════════════════════

echo "  ┌─────────────────────────────────────────┐"
echo "  │  Como deseja instalar?                   │"
echo "  │                                          │"
echo "  │  1) Sessão adicional                     │"
echo "  │     CIOS aparece ao lado do GNOME/KDE │"
echo "  │     na tela de login. Nada é removido.   │"
echo "  │                                          │"
echo "  │  2) Substituição completa                │"
echo "  │     Remove o desktop atual e instala     │"
echo "  │     LightDM com CIOS como padrão.     │"
echo "  │     (pode reverter desinstalando)        │"
echo "  │                                          │"
echo "  └─────────────────────────────────────────┘"
echo ""

# Default to session-only if non-interactive (piped input)
INSTALL_MODE="1"
if [ -t 0 ]; then
    read -rp "  Opção [1]: " INSTALL_MODE
    INSTALL_MODE="${INSTALL_MODE:-1}"
fi

echo ""

# ══════════════════════════════════════════════════════════════
#  PREVENT DISPLAY MANAGER RESTARTS
# ══════════════════════════════════════════════════════════════

_DM_POLICY_CREATED=false
_DM_INVOKE_PATCHED=false

_block_dm_restart() {
    mkdir -p /usr/sbin
    if [ ! -f /usr/sbin/policy-rc.d ] || ! grep -q "cios-installer" /usr/sbin/policy-rc.d 2>/dev/null; then
        cat > /usr/sbin/policy-rc.d << 'POLICY'
#!/bin/sh
# Installed by cios-installer — blocks DM restarts during install
case "$1" in
    lightdm|gdm|gdm3|sddm|display-manager) exit 101 ;;
    *) exit 0 ;;
esac
POLICY
        chmod 755 /usr/sbin/policy-rc.d
        _DM_POLICY_CREATED=true
    fi

    if [ -f /usr/bin/deb-systemd-invoke ] && [ ! -f /usr/bin/deb-systemd-invoke.bak.cios ]; then
        cp /usr/bin/deb-systemd-invoke /usr/bin/deb-systemd-invoke.bak.cios
        cat > /usr/bin/deb-systemd-invoke << 'NOOP'
#!/bin/sh
case "$*" in
    *display-manager*|*lightdm*|*gdm*|*sddm*|*restart*lightdm*|*restart*gdm*)
        exit 0 ;;
    *)
        exec /usr/bin/deb-systemd-invoke.bak.cios "$@" ;;
esac
NOOP
        chmod 755 /usr/bin/deb-systemd-invoke
        _DM_INVOKE_PATCHED=true
    fi
}

_restore_dm_restart() {
    if [ "$_DM_POLICY_CREATED" = true ]; then
        rm -f /usr/sbin/policy-rc.d
    fi
    if [ "$_DM_INVOKE_PATCHED" = true ] && [ -f /usr/bin/deb-systemd-invoke.bak.cios ]; then
        mv /usr/bin/deb-systemd-invoke.bak.cios /usr/bin/deb-systemd-invoke
    fi
}

trap _restore_dm_restart EXIT

# ══════════════════════════════════════════════════════════════
#  INSTALL
# ══════════════════════════════════════════════════════════════

# Remove previous version if installed
if dpkg -s cios >/dev/null 2>&1; then
    PREV_VER=$(dpkg-query -W -f='${Version}' cios 2>/dev/null || echo "unknown")
    echo "  → Previous version detected: ${PREV_VER}"
    echo "  → Removing before upgrade..."
    pkill -f "python.*cios\.main" 2>/dev/null || true
    dpkg -r cios 2>/dev/null || true
    echo "  ✓ Previous version removed"
fi

# Block DM restarts BEFORE installing anything
echo "  → Installing dependencies..."
_block_dm_restart

apt-get update -qq 2>/dev/null || true
apt-get install -y -qq --no-install-recommends \
    python3 python3-pip python3-venv python3-tk \
    openbox wmctrl xdotool x11-xserver-utils curl 2>/dev/null || true
echo "  ✓ Dependencies installed"

# Install the .deb
echo "  → Installing CIOS..."
dpkg -i "$DEB_FILE" 2>/dev/null || true
apt-get install -f -y -qq --no-install-recommends 2>/dev/null || true

# ══════════════════════════════════════════════════════════════
#  MODE 2: FULL REPLACEMENT — Switch to LightDM + CIOS only
# ══════════════════════════════════════════════════════════════

if [ "$INSTALL_MODE" = "2" ]; then
    echo ""
    echo "  → Configurando substituição completa..."

    # Install LightDM + greeter + Plymouth
    apt-get install -y -qq --no-install-recommends \
        lightdm slick-greeter plymouth 2>/dev/null || {
        # Fallback to lightdm-gtk-greeter if slick not available
        apt-get install -y -qq --no-install-recommends \
            lightdm lightdm-gtk-greeter plymouth 2>/dev/null || true
    }
    echo "  ✓ LightDM + Plymouth installed"

    # Backup current display manager config
    if [ -f /etc/X11/default-display-manager ] && [ ! -f /etc/X11/default-display-manager.bak.cios ]; then
        cp /etc/X11/default-display-manager /etc/X11/default-display-manager.bak.cios
    fi

    # Set LightDM as default display manager
    echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager

    # Apply CIOS LightDM configs
    CIOS_CONF="/usr/share/cios/config"

    if [ -f "$CIOS_CONF/lightdm.conf" ]; then
        # Backup existing LightDM config
        if [ -f /etc/lightdm/lightdm.conf ] && [ ! -f /etc/lightdm/lightdm.conf.bak.cios ]; then
            cp /etc/lightdm/lightdm.conf /etc/lightdm/lightdm.conf.bak.cios
        fi
        cp "$CIOS_CONF/lightdm.conf" /etc/lightdm/lightdm.conf
        echo "  ✓ LightDM configured for CIOS"
    fi

    if [ -f "$CIOS_CONF/slick-greeter.conf" ]; then
        if [ -f /etc/lightdm/slick-greeter.conf ] && [ ! -f /etc/lightdm/slick-greeter.conf.bak.cios ]; then
            cp /etc/lightdm/slick-greeter.conf /etc/lightdm/slick-greeter.conf.bak.cios
        fi
        mkdir -p /etc/lightdm
        cp "$CIOS_CONF/slick-greeter.conf" /etc/lightdm/slick-greeter.conf
        echo "  ✓ Greeter theme applied (logo + background)"
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
        echo "  ✓ Plymouth splash configured (initramfs, instant)"
    else
        echo "  ⚠ Plymouth theme not found (boot will show text)"
    fi

    # ── GRUB: invisible, zero delay, silent kernel ──
    if [ -f /etc/default/grub ]; then
        if [ ! -f /etc/default/grub.bak.cios ]; then
            cp /etc/default/grub /etc/default/grub.bak.cios
        fi

        # Fully silent boot — no kernel messages, no cursor, no systemd status
        sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=0 vt.global_cursor_default=0 rd.udev.log_priority=3 systemd.show_status=false"/' /etc/default/grub

        # Zero timeout — GRUB invisible (Shift/Esc still works)
        sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=0/' /etc/default/grub

        # Hidden style
        if grep -q "^GRUB_TIMEOUT_STYLE" /etc/default/grub; then
            sed -i 's/^GRUB_TIMEOUT_STYLE=.*/GRUB_TIMEOUT_STYLE=hidden/' /etc/default/grub
        else
            echo 'GRUB_TIMEOUT_STYLE=hidden' >> /etc/default/grub
        fi

        # Don't probe for other OS
        if grep -q "^GRUB_DISABLE_OS_PROBER" /etc/default/grub; then
            sed -i 's/^GRUB_DISABLE_OS_PROBER=.*/GRUB_DISABLE_OS_PROBER=true/' /etc/default/grub
        else
            echo 'GRUB_DISABLE_OS_PROBER=true' >> /etc/default/grub
        fi

        # After failed boot, minimal timeout (safety net)
        if grep -q "^GRUB_RECORDFAIL_TIMEOUT" /etc/default/grub; then
            sed -i 's/^GRUB_RECORDFAIL_TIMEOUT=.*/GRUB_RECORDFAIL_TIMEOUT=2/' /etc/default/grub
        else
            echo 'GRUB_RECORDFAIL_TIMEOUT=2' >> /etc/default/grub
        fi

        update-grub 2>/dev/null || true
        echo "  ✓ GRUB invisible (0s, silent kernel, no OS probe)"
    fi

    # Disable GDM/SDDM if they're the current DM (don't remove, just disable)
    for dm in gdm gdm3 sddm; do
        if systemctl is-enabled "$dm" 2>/dev/null | grep -q "enabled"; then
            systemctl disable "$dm" 2>/dev/null || true
            echo "  → Disabled $dm"
        fi
    done

    # Enable LightDM
    systemctl enable lightdm 2>/dev/null || true
    echo "  ✓ LightDM enabled as default"

    echo ""
    echo "  ✓ Substituição completa configurada"
    echo "    Boot: logo CIOS (Plymouth)"
    echo "    Login: LightDM com tema CIOS"
    echo "    Para reverter: sudo apt remove cios && sudo reboot"
else
    # ── Mode 1: Session only — still optimize boot if Plymouth available ──
    PLYMOUTH_THEME="/usr/share/plymouth/themes/cios"
    if [ -d "$PLYMOUTH_THEME" ] && [ -f "$PLYMOUTH_THEME/cios.plymouth" ] && command -v plymouth-set-default-theme &>/dev/null; then
        echo "  → Otimizando boot..."
        plymouth-set-default-theme cios 2>/dev/null || true

        mkdir -p /etc/initramfs-tools/conf.d
        echo "FRAMEBUFFER=y" > /etc/initramfs-tools/conf.d/cios-splash

        INITRAMFS_MODULES="/etc/initramfs-tools/modules"
        for mod in drm drm_kms_helper i915 amdgpu nouveau radeon; do
            if ! grep -q "^${mod}$" "$INITRAMFS_MODULES" 2>/dev/null; then
                echo "$mod" >> "$INITRAMFS_MODULES"
            fi
        done

        update-initramfs -u 2>/dev/null || true

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
        echo "  ✓ Boot otimizado (Plymouth + GRUB silencioso)"
    fi
fi

# Restore DM restart capability
_restore_dm_restart

echo ""
echo "  ═══════════════════════════════════════"
echo "  ✓ CIOS installed successfully!"
echo "  ═══════════════════════════════════════"
echo ""
if [ "$INSTALL_MODE" = "2" ]; then
    echo "  Modo: Substituição completa (LightDM + CIOS)"
    echo "  Reboot para iniciar: sudo reboot"
    echo ""
    echo "  Para reverter:"
    echo "    sudo apt remove cios"
    echo "    sudo reboot"
else
    echo "  Modo: Sessão adicional"
    echo "  Reboot e selecione 'CIOS' na tela de login."
fi
echo ""
