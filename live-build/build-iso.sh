#!/bin/bash
# ═══════════════════════════════════════════════════
#  CIOS — Live ISO Build Orchestrator
#  Usage: sudo ./live-build/build-iso.sh [VERSION]
#
#  Builds the complete CIOS live ISO:
#    1. Builds the .deb package (via build-deb.sh)
#    2. Configures live-build
#    3. Produces the hybrid ISO image
#
#  Must be run as root (live-build requires chroot).
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

    for cmd in lb debootstrap dpkg-deb; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing required tools: ${missing[*]}"
        error "Install with: sudo apt install live-build debootstrap dpkg-dev"
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

    error "Could not determine version. Pass VERSION as argument or ensure pyproject.toml exists."
    exit 1
}

# ── Main Build ─────────────────────────────────────────────────────
main() {
    check_prerequisites

    VERSION=$(get_version)
    info "Building CIOS Live ISO v${VERSION}..."

    # Export git commit for manifest hook
    export CIOS_GIT_COMMIT
    CIOS_GIT_COMMIT=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

    # Step 1: Build the .deb package
    info "Step 1/4: Building .deb package..."
    if [ -f "$REPO_ROOT/build-deb.sh" ]; then
        bash "$REPO_ROOT/build-deb.sh"
    else
        error "build-deb.sh not found at $REPO_ROOT/build-deb.sh"
        exit 1
    fi

    # Find the built .deb
    local deb_file
    deb_file=$(find "$REPO_ROOT" -maxdepth 1 -name 'cios_*.deb' -newer "$REPO_ROOT/build-deb.sh" | head -1)
    if [ -z "$deb_file" ]; then
        deb_file=$(find "$REPO_ROOT" -maxdepth 1 -name 'cios_*.deb' | head -1)
    fi

    if [ -z "$deb_file" ]; then
        error ".deb package not found after build-deb.sh"
        exit 1
    fi
    info "  .deb: $(basename "$deb_file")"

    # Step 2: Copy .deb into live-build packages directory
    info "Step 2/4: Preparing live-build configuration..."
    mkdir -p "$SCRIPT_DIR/config/packages.chroot"
    cp "$deb_file" "$SCRIPT_DIR/config/packages.chroot/"

    # Step 3: Configure live-build
    info "Step 3/4: Running lb config..."
    (cd "$SCRIPT_DIR" && lb config)

    # Step 4: Build the ISO
    info "Step 4/4: Building ISO (this may take 15-30 minutes)..."
    (cd "$SCRIPT_DIR" && lb build)

    # Rename output ISO
    local output_iso="$SCRIPT_DIR/live-image-amd64.hybrid.iso"
    local final_iso="$SCRIPT_DIR/cios-${VERSION}-amd64.iso"

    if [ -f "$output_iso" ]; then
        mv "$output_iso" "$final_iso"
    elif [ -f "$SCRIPT_DIR/live-image-amd64.iso" ]; then
        mv "$SCRIPT_DIR/live-image-amd64.iso" "$final_iso"
    else
        error "ISO output not found. Check build logs in $SCRIPT_DIR/.build/"
        exit 1
    fi

    # Report result
    local iso_size
    iso_size=$(du -h "$final_iso" | cut -f1)
    echo ""
    info "═══════════════════════════════════════════════════"
    info "  ISO built successfully!"
    info "  File: $(basename "$final_iso")"
    info "  Size: $iso_size"
    info "  Path: $final_iso"
    info "═══════════════════════════════════════════════════"
    echo ""
    info "Test with: qemu-system-x86_64 -cdrom $final_iso -m 2G -enable-kvm"
}

main "$@"
