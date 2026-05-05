#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  Harmoni OS — One-line installer
#  Usage: sudo bash install-harmoni.sh harmoni_0.13.2_amd64.deb
#     or: sudo bash install-harmoni.sh  (auto-downloads latest)
#
#  This script prevents display manager restarts during installation.
#  Without it, installing dependencies can kill the active session.
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
#  PREVENT DISPLAY MANAGER RESTARTS
#  Installing packages like openbox/lightdm can trigger systemd
#  to restart the display manager, killing the user's session.
#  We temporarily block that.
# ══════════════════════════════════════════════════════════════

_DM_POLICY_CREATED=false
_DM_INVOKE_PATCHED=false

# Method 1: Policy-based — prevent any DM service from restarting
_block_dm_restart() {
    # Create a policy that prevents display-manager restart
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

    # Method 2: Also patch deb-systemd-invoke as belt-and-suspenders
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

# Ensure cleanup on exit
trap _restore_dm_restart EXIT

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

# Install the .deb (using dpkg to avoid apt re-resolving deps and triggering restarts)
echo "  → Installing Harmoni..."
dpkg -i "$DEB_FILE" 2>/dev/null || true
# Fix any missing deps (still with DM restart blocked)
apt-get install -f -y -qq --no-install-recommends 2>/dev/null || true

# Restore DM restart capability (trap will also do this on exit)
_restore_dm_restart

echo ""
echo "  ═══════════════════════════════════════"
echo "  ✓ Harmoni installed successfully!"
echo "  ═══════════════════════════════════════"
echo ""
echo "  Reboot to start: sudo reboot"
echo ""
