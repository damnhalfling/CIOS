#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  Harmoni OS — One-line installer
#  Usage: sudo bash install-harmoni.sh [harmoni_*.deb]
#     or: sudo bash install-harmoni.sh  (auto-downloads latest)
#
#  Modes:
#    1. Session only — adds Harmoni alongside GNOME/KDE
#    2. Full replacement — switches to LightDM with Harmoni as default
#
#  This script prevents display manager restarts during installation.
# ═══════════════════════════════════════════════════
set -euo pipefail

export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"
export DEBIAN_FRONTEND=noninteractive

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║     Harmoni OS — Installer           ║"
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
        https://github.com/damnhalfling/harmoni/releases/latest)
    VERSION=$(basename "$LATEST_URL")
    DEB_URL="https://github.com/damnhalfling/harmoni/releases/download/${VERSION}/harmoni_${VERSION#v}_amd64.deb"

    DEB_FILE="/tmp/harmoni_${VERSION#v}_amd64.deb"
    echo "  → Downloading ${VERSION}..."
    curl -sL -o "$DEB_FILE" "$DEB_URL" || {
        echo "  ✗ Download failed. Get the .deb manually from:"
        echo "    https://github.com/damnhalfling/harmoni/releases"
        exit 1
    }
    echo "  ✓ Downloaded"
fi

if [ ! -f "$DEB_FILE" ]; then
    echo "  ✗ File not found: $DEB_FILE"
    exit 1
fi

# ══════════════════════════════════════════════════════════════
#  INSTALLATION MODE SELECTION
# ══════════════════════════════════════════════════════════════

echo "  ┌─────────────────────────────────────────┐"
echo "  │  Como deseja instalar?                   │"
echo "  │                                          │"
echo "  │  1) Sessão adicional                     │"
echo "  │     Harmoni aparece ao lado do GNOME/KDE │"
echo "  │     na tela de login. Nada é removido.   │"
echo "  │                                          │"
echo "  │  2) Substituição completa                │"
echo "  │     Remove o desktop atual e instala     │"
echo "  │     LightDM com Harmoni como padrão.     │"
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
    if [ ! -f /usr/sbin/policy-rc.d ] || ! grep -q "harmoni-installer" /usr/sbin/policy-rc.d 2>/dev/null; then
        cat > /usr/sbin/policy-rc.d << 'POLICY'
#!/bin/sh
# Installed by harmoni-installer — blocks DM restarts during install
case "$1" in
    lightdm|gdm|gdm3|sddm|display-manager) exit 101 ;;
    *) exit 0 ;;
esac
POLICY
        chmod 755 /usr/sbin/policy-rc.d
        _DM_POLICY_CREATED=true
    fi

    if [ -f /usr/bin/deb-systemd-invoke ] && [ ! -f /usr/bin/deb-systemd-invoke.bak.harmoni ]; then
        cp /usr/bin/deb-systemd-invoke /usr/bin/deb-systemd-invoke.bak.harmoni
        cat > /usr/bin/deb-systemd-invoke << 'NOOP'
#!/bin/sh
case "$*" in
    *display-manager*|*lightdm*|*gdm*|*sddm*|*restart*lightdm*|*restart*gdm*)
        exit 0 ;;
    *)
        exec /usr/bin/deb-systemd-invoke.bak.harmoni "$@" ;;
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
    if [ "$_DM_INVOKE_PATCHED" = true ] && [ -f /usr/bin/deb-systemd-invoke.bak.harmoni ]; then
        mv /usr/bin/deb-systemd-invoke.bak.harmoni /usr/bin/deb-systemd-invoke
    fi
}

trap _restore_dm_restart EXIT

# ══════════════════════════════════════════════════════════════
#  INSTALL
# ══════════════════════════════════════════════════════════════

# Remove previous version if installed
if dpkg -s harmoni >/dev/null 2>&1; then
    PREV_VER=$(dpkg-query -W -f='${Version}' harmoni 2>/dev/null || echo "unknown")
    echo "  → Previous version detected: ${PREV_VER}"
    echo "  → Removing before upgrade..."
    pkill -f "python.*harmoni\.main" 2>/dev/null || true
    dpkg -r harmoni 2>/dev/null || true
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
echo "  → Installing Harmoni..."
dpkg -i "$DEB_FILE" 2>/dev/null || true
apt-get install -f -y -qq --no-install-recommends 2>/dev/null || true

# ══════════════════════════════════════════════════════════════
#  MODE 2: FULL REPLACEMENT — Switch to LightDM + Harmoni only
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
    if [ -f /etc/X11/default-display-manager ] && [ ! -f /etc/X11/default-display-manager.bak.harmoni ]; then
        cp /etc/X11/default-display-manager /etc/X11/default-display-manager.bak.harmoni
    fi

    # Set LightDM as default display manager
    echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager

    # Apply Harmoni LightDM configs
    HARMONI_CONF="/usr/share/harmoni/config"

    if [ -f "$HARMONI_CONF/lightdm.conf" ]; then
        # Backup existing LightDM config
        if [ -f /etc/lightdm/lightdm.conf ] && [ ! -f /etc/lightdm/lightdm.conf.bak.harmoni ]; then
            cp /etc/lightdm/lightdm.conf /etc/lightdm/lightdm.conf.bak.harmoni
        fi
        cp "$HARMONI_CONF/lightdm.conf" /etc/lightdm/lightdm.conf
        echo "  ✓ LightDM configured for Harmoni"
    fi

    if [ -f "$HARMONI_CONF/slick-greeter.conf" ]; then
        if [ -f /etc/lightdm/slick-greeter.conf ] && [ ! -f /etc/lightdm/slick-greeter.conf.bak.harmoni ]; then
            cp /etc/lightdm/slick-greeter.conf /etc/lightdm/slick-greeter.conf.bak.harmoni
        fi
        mkdir -p /etc/lightdm
        cp "$HARMONI_CONF/slick-greeter.conf" /etc/lightdm/slick-greeter.conf
        echo "  ✓ Greeter theme applied (logo + background)"
    fi

    # ── Plymouth boot splash ──
    PLYMOUTH_THEME="/usr/share/plymouth/themes/harmoni"
    if [ -d "$PLYMOUTH_THEME" ] && [ -f "$PLYMOUTH_THEME/harmoni.plymouth" ]; then
        # Set Harmoni as the Plymouth theme
        plymouth-set-default-theme harmoni 2>/dev/null || {
            # Manual fallback if plymouth-set-default-theme not available
            mkdir -p /etc/plymouth
            echo "[Daemon]" > /etc/plymouth/plymouthd.conf
            echo "Theme=harmoni" >> /etc/plymouth/plymouthd.conf
        }
        # Rebuild initramfs to include the theme
        update-initramfs -u 2>/dev/null || true
        echo "  ✓ Plymouth boot splash configured"

        # Ensure GRUB uses Plymouth (quiet splash)
        if [ -f /etc/default/grub ]; then
            if ! grep -q "quiet splash" /etc/default/grub; then
                # Backup
                if [ ! -f /etc/default/grub.bak.harmoni ]; then
                    cp /etc/default/grub /etc/default/grub.bak.harmoni
                fi
                # Add quiet splash to GRUB_CMDLINE_LINUX_DEFAULT
                sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 quiet splash"/' /etc/default/grub
                # Remove duplicate spaces
                sed -i 's/  */ /g' /etc/default/grub
                update-grub 2>/dev/null || true
                echo "  ✓ GRUB configured for splash boot"
            fi
        fi
    else
        echo "  ⚠ Plymouth theme not found (boot will show text)"
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
    echo "    Boot: logo Harmoni (Plymouth)"
    echo "    Login: LightDM com tema Harmoni"
    echo "    Para reverter: sudo apt remove harmoni && sudo reboot"
fi

# Restore DM restart capability
_restore_dm_restart

echo ""
echo "  ═══════════════════════════════════════"
echo "  ✓ Harmoni installed successfully!"
echo "  ═══════════════════════════════════════"
echo ""
if [ "$INSTALL_MODE" = "2" ]; then
    echo "  Modo: Substituição completa (LightDM + Harmoni)"
    echo "  Reboot para iniciar: sudo reboot"
    echo ""
    echo "  Para reverter:"
    echo "    sudo apt remove harmoni"
    echo "    sudo reboot"
else
    echo "  Modo: Sessão adicional"
    echo "  Reboot e selecione 'Harmoni OS' na tela de login."
fi
echo ""
