#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  Harmoni OS — One-line installer
#  Usage: sudo bash install-harmoni.sh harmoni_0.8.0_amd64.deb
#     or: sudo bash install-harmoni.sh  (auto-downloads latest)
# ═══════════════════════════════════════════════════
set -euo pipefail

export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

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
    apt-get update -qq
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

# Remove previous version if installed
if dpkg -s harmoni >/dev/null 2>&1; then
    PREV_VER=$(dpkg-query -W -f='${Version}' harmoni 2>/dev/null || echo "unknown")
    echo "  → Previous version detected: ${PREV_VER}"
    echo "  → Removing before upgrade..."
    # Stop running processes
    pkill -f "python.*harmoni\.main" 2>/dev/null || true
    # Remove old package (keeps user data in ~/.harmoni)
    dpkg -r harmoni 2>/dev/null || true
    echo "  ✓ Previous version removed"
fi

# Install dependencies first
echo "  → Installing dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv python3-tk \
    openbox wmctrl xdotool x11-xserver-utils curl 2>&1 | tail -1
echo "  ✓ Dependencies installed"

# Install the .deb (apt resolves dependencies automatically)
echo "  → Installing Harmoni..."
apt-get install -y -qq "$DEB_FILE" 2>&1 || {
    # Fallback: dpkg + fix deps
    dpkg -i "$DEB_FILE" 2>&1 || true
    apt-get install -f -y -qq 2>&1 || true
}

echo ""
echo "  ═══════════════════════════════════════"
echo "  ✓ Harmoni installed successfully!"
echo "  ═══════════════════════════════════════"
echo ""
echo "  Reboot to start: sudo reboot"
echo ""
