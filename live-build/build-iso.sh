#!/bin/bash
# ═══════════════════════════════════════════════════
#  CIOS — Live ISO Build Orchestrator
#  Usage: sudo ./live-build/build-iso.sh [VERSION]
#
#  Builds the complete CIOS live ISO:
#    1. Builds the .deb package (via build-deb.sh)
#    2. Configures live-build
#    3. Produces the hybrid ISO image (UEFI + BIOS)
#
#  Must be run as root (live-build requires chroot).
#  Requires: live-build, debootstrap, dpkg-dev
#
#  Result: cios-VERSION-amd64.iso (~800MB-1.2GB)
#  Boot chain: GRUB(0s) → Plymouth(logo) → greetd → CIOS
# ═══════════════════════════════════════════════════
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="${1:-}"

# ── Colors ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}>>>${NC} $*"; }
warn()  { echo -e "${YELLOW}>>>${NC} $*"; }
error() { echo -e "${RED}>>>${NC} $*" >&2; }

# ── Prerequisite Checks ────────────────────────────────────────────
check_prerequisites() {
    local missing=()

    for cmd in lb debootstrap dpkg-deb meson ninja; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing required tools: ${missing[*]}"
        error "Install with: sudo apt install live-build debootstrap dpkg-dev meson ninja-build"
        exit 1
    fi

    if [ "$(id -u)" -ne 0 ]; then
        error "This script must be run as root (live-build requires chroot)."
        error "Usage: sudo $0 [VERSION]"
        exit 1
    fi
}

# ── Extract Version ────────────────────────────────────────────────
get_version() {
    if [ -n "$VERSION" ]; then
        echo "$VERSION"
        return
    fi

    # Extract from pyproject.toml
    local pyproject="$REPO_ROOT/pyproject.toml"
    if [ -f "$pyproject" ]; then
        VERSION=$(grep -oP 'version\s*=\s*"\K[^"]+' "$pyproject" | head -1)
        if [ -n "$VERSION" ]; then
            echo "$VERSION"
            return
        fi
    fi

    error "Could not determine version. Pass VERSION as argument."
    exit 1
}

# ── Clean previous build ──────────────────────────────────────────
clean_previous() {
    info "Cleaning previous build artifacts..."
    (cd "$SCRIPT_DIR" && lb clean 2>/dev/null || true)
    rm -rf "$SCRIPT_DIR/config/packages.chroot"
}

# ── Main Build ─────────────────────────────────────────────────────
main() {
    check_prerequisites

    VERSION=$(get_version)
    info "╔═══════════════════════════════════════════════╗"
    info "║  CIOS — Building Live ISO v${VERSION}"
    info "╚═══════════════════════════════════════════════╝"
    echo ""

    # Export git commit for manifest hook
    export CIOS_GIT_COMMIT
    CIOS_GIT_COMMIT=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

    # Step 1: Build the .deb package
    info "[1/5] Building .deb package..."
    if [ -f "$REPO_ROOT/build-deb.sh" ]; then
        (cd "$REPO_ROOT" && bash build-deb.sh "$VERSION")
    else
        error "build-deb.sh not found at $REPO_ROOT/build-deb.sh"
        exit 1
    fi

    # Find the built .deb
    local deb_file
    deb_file=$(find "$REPO_ROOT" -maxdepth 1 -name "cios_${VERSION}_amd64.deb" | head -1)
    if [ -z "$deb_file" ]; then
        deb_file=$(find "$REPO_ROOT" -maxdepth 1 -name 'cios_*.deb' | sort -t_ -k2 -V | tail -1)
    fi

    if [ -z "$deb_file" ]; then
        error ".deb package not found after build-deb.sh"
        exit 1
    fi
    info "    .deb: $(basename "$deb_file") ($(du -h "$deb_file" | cut -f1))"

    # Step 2: Clean and prepare
    info "[2/5] Preparing live-build environment..."
    clean_previous

    # Instead of using config/packages.chroot (which creates an unsigned local repo),
    # copy the .deb into includes.chroot and install via hook
    mkdir -p "$SCRIPT_DIR/config/includes.chroot/tmp"
    cp "$deb_file" "$SCRIPT_DIR/config/includes.chroot/tmp/cios.deb"

    # Ensure hooks are in BOTH locations for compatibility:
    # - config/hooks/live/*.chroot  (live-build >= 4.x, Debian)
    # - config/hooks/*.chroot       (live-build 3.x, Ubuntu)
    if [ -d "$SCRIPT_DIR/config/hooks/live" ]; then
        cp -f "$SCRIPT_DIR/config/hooks/live/"*.chroot "$SCRIPT_DIR/config/hooks/" 2>/dev/null || true
        chmod +x "$SCRIPT_DIR/config/hooks/"*.chroot 2>/dev/null || true
    fi

    # Step 3: Configure live-build
    info "[3/5] Running lb config..."
    # Clear Ubuntu defaults that conflict with Debian trixie
    sudo rm -f /etc/live/build.conf 2>/dev/null || true
    (cd "$SCRIPT_DIR" && lb config)

    # Step 4: Build the ISO
    info "[4/5] Building ISO (this takes 15-30 minutes)..."
    info "    Distribution: Debian trixie (13)"
    info "    Architecture: amd64"
    info "    Boot: UEFI + Legacy BIOS"
    echo ""

    # Run full build (no need to split phases since we don't use packages.chroot)
    (cd "$SCRIPT_DIR" && lb build)

    # Step 5: Rename and report
    info "[5/5] Finalizing..."
    local output_iso=""
    for candidate in \
        "$SCRIPT_DIR/live-image-amd64.hybrid.iso" \
        "$SCRIPT_DIR/live-image-amd64.iso" \
        "$SCRIPT_DIR/binary.hybrid.iso"; do
        if [ -f "$candidate" ]; then
            output_iso="$candidate"
            break
        fi
    done

    if [ -z "$output_iso" ]; then
        error "ISO output not found. Check build logs."
        ls -la "$SCRIPT_DIR"/*.iso 2>/dev/null || true
        exit 1
    fi

    local final_iso="$SCRIPT_DIR/cios-${VERSION}-amd64.iso"
    mv "$output_iso" "$final_iso"

    # Report
    local iso_size
    iso_size=$(du -h "$final_iso" | cut -f1)
    echo ""
    info "═══════════════════════════════════════════════════"
    info "  ✓ ISO built successfully!"
    info ""
    info "  File: $(basename "$final_iso")"
    info "  Size: $iso_size"
    info "  Path: $final_iso"
    info ""
    info "  Test:"
    info "    qemu-system-x86_64 -cdrom $final_iso -m 4G -enable-kvm \\"
    info "      -device virtio-vga -display gtk \\"
    info "      -net nic -net user,hostfwd=tcp::2222-:22"
    info ""
    info "  Write to USB:"
    info "    sudo dd if=$final_iso of=/dev/sdX bs=4M status=progress"
    info "═══════════════════════════════════════════════════"
}

main "$@"
