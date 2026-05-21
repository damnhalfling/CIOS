#!/bin/bash
set -e

echo "=== CIOS Shell — Building .deb package ==="
echo ""

# Check for cargo
if ! command -v cargo &> /dev/null; then
    echo "ERROR: Rust/Cargo not found. Install via: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
fi

# Build release binary
echo "[1/4] Compiling release binary..."
cargo build --release

BINARY="target/release/cios-shell"
if [ ! -f "$BINARY" ]; then
    echo "ERROR: Build failed — binary not found"
    exit 1
fi

echo "[2/4] Binary size: $(du -h $BINARY | cut -f1)"

# Create .deb structure
VERSION="0.1.0"
PKG_NAME="cios-shell_${VERSION}_amd64"
PKG_DIR="target/${PKG_NAME}"

echo "[3/4] Assembling package structure..."

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/cios-shell"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/doc/cios-shell"

# Control file
cp debian/control "$PKG_DIR/DEBIAN/control"
cp debian/postinst "$PKG_DIR/DEBIAN/postinst"
chmod 755 "$PKG_DIR/DEBIAN/postinst"

# Binary
cp "$BINARY" "$PKG_DIR/usr/bin/cios-shell"
chmod 755 "$PKG_DIR/usr/bin/cios-shell"

# Desktop entry
cat > "$PKG_DIR/usr/share/applications/cios-shell.desktop" << 'EOF'
[Desktop Entry]
Name=CIOS Shell
Comment=CIOS Grid Interface - Wayland Shell Overlay
Exec=cios-shell
Type=Application
Categories=System;
Keywords=cios;shell;wayland;tron;
EOF

# README
cat > "$PKG_DIR/usr/share/doc/cios-shell/README" << 'EOF'
CIOS Shell v0.1.0 — The Grid Interface

A TRON-inspired Wayland shell overlay for the CIOS operating system.

Visual Elements:
  - Identity Disc: Central ring showing runtime state (idle/listening/cloud/error)
  - Grid Background: Infinite coordinate plane with pulsing neon data lines
  - Rez-in/Derezz: Materialization and dissolution transitions

Color States:
  - Cyan (#00E5FF): Local processing, idle, safe
  - Orange (#FF6D00): Cloud intelligence active
  - Red (#FF1744): Error / security alert

Requirements:
  - Wayland compositor with wlr-layer-shell support
  - Vulkan-capable GPU

Source: https://github.com/cios-os/cios-shell
EOF

# Calculate installed size
INSTALLED_SIZE=$(du -sk "$PKG_DIR" | cut -f1)
echo "Installed-Size: ${INSTALLED_SIZE}" >> "$PKG_DIR/DEBIAN/control"

# Build .deb
echo "[4/4] Building .deb package..."
dpkg-deb --build "$PKG_DIR" "target/${PKG_NAME}.deb"

echo ""
echo "=== Build complete ==="
echo "Package: target/${PKG_NAME}.deb"
echo "Size: $(du -h target/${PKG_NAME}.deb | cut -f1)"
echo ""
echo "Install with: sudo dpkg -i target/${PKG_NAME}.deb"
