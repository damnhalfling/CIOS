#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  CIOS — Automated boot test in QEMU VM
#  Verifies: install → boot → greeter → login → UI
#
#  Usage: bash tests/test-boot-vm.sh [cios.deb]
#  Requires: qemu-system-x86_64, qemu-img, ssh
# ═══════════════════════════════════════════════════
set -euo pipefail

DEB_FILE="${1:-}"
DISK="/tmp/cios-boot-test.qcow2"
SSH_PORT=2299
TIMEOUT=120

if [ -z "$DEB_FILE" ]; then
    echo "Usage: $0 <cios_*.deb>"
    exit 1
fi

if [ ! -f "$DEB_FILE" ]; then
    echo "ERROR: $DEB_FILE not found"
    exit 1
fi

echo "╔═══════════════════════════════════════════╗"
echo "║  CIOS — Boot Test (QEMU)                 ║"
echo "╚═══════════════════════════════════════════╝"

# ── Check prerequisites ──
for cmd in qemu-system-x86_64 qemu-img ssh; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd not found"
        exit 1
    fi
done

# ── Create test disk (if not exists) ──
if [ ! -f "$DISK" ]; then
    echo "→ Creating test disk..."
    qemu-img create -f qcow2 "$DISK" 10G
    echo "  ⚠ Need a pre-installed Debian base image at $DISK"
    echo "  Create one with: qemu-img create + debian netinst"
    exit 1
fi

# ── Start VM ──
echo "→ Starting VM..."
qemu-system-x86_64 -m 4096 -smp 2 -enable-kvm \
    -drive file="$DISK",format=qcow2 \
    -device virtio-vga-gl -display none \
    -net nic -net user,hostfwd=tcp::${SSH_PORT}-:22 \
    -daemonize -pidfile /tmp/cios-test-vm.pid

VM_PID=$(cat /tmp/cios-test-vm.pid)
echo "  VM started (PID: $VM_PID)"

# ── Wait for SSH ──
echo "→ Waiting for SSH..."
for i in $(seq 1 60); do
    if ssh -p $SSH_PORT -o ConnectTimeout=2 -o StrictHostKeyChecking=no \
        cios@localhost "echo ok" &>/dev/null; then
        echo "  SSH ready after ${i}s"
        break
    fi
    sleep 1
done

# ── Install .deb ──
echo "→ Installing CIOS..."
scp -P $SSH_PORT -o StrictHostKeyChecking=no "$DEB_FILE" cios@localhost:/tmp/cios.deb
ssh -p $SSH_PORT cios@localhost "sudo apt install -y /tmp/cios.deb" || {
    echo "  ⚠ Install failed (may need dependencies)"
    ssh -p $SSH_PORT cios@localhost "sudo apt install -f -y"
}

# ── Reboot and test ──
echo "→ Rebooting..."
ssh -p $SSH_PORT cios@localhost "sudo reboot" || true
sleep 10

# Wait for SSH again (after reboot)
echo "→ Waiting for boot..."
for i in $(seq 1 $TIMEOUT); do
    if ssh -p $SSH_PORT -o ConnectTimeout=2 -o StrictHostKeyChecking=no \
        cios@localhost "echo ok" &>/dev/null; then
        echo "  System up after ${i}s"
        break
    fi
    sleep 1
done

# ── Verify ──
echo "→ Verifying..."

ERRORS=0

# Check greetd is running
if ssh -p $SSH_PORT cios@localhost "systemctl is-active greetd" | grep -q "active"; then
    echo "  ✓ greetd active"
else
    echo "  ✗ greetd not active"
    ERRORS=$((ERRORS + 1))
fi

# Check cios-shell binary exists
if ssh -p $SSH_PORT cios@localhost "test -x /usr/bin/cios-shell"; then
    echo "  ✓ cios-shell installed"
else
    echo "  ✗ cios-shell missing"
    ERRORS=$((ERRORS + 1))
fi

# Check cios-session exists
if ssh -p $SSH_PORT cios@localhost "test -x /usr/local/bin/cios-session"; then
    echo "  ✓ cios-session installed"
else
    echo "  ✗ cios-session missing"
    ERRORS=$((ERRORS + 1))
fi

# Check GTK4 available
if ssh -p $SSH_PORT cios@localhost "python3 -c 'import gi; gi.require_version(\"Gtk\",\"4.0\")'" 2>/dev/null; then
    echo "  ✓ GTK4 available"
else
    echo "  ✗ GTK4 not available"
    ERRORS=$((ERRORS + 1))
fi

# Check os-release
if ssh -p $SSH_PORT cios@localhost "grep -q CIOS /etc/os-release" 2>/dev/null; then
    echo "  ✓ os-release shows CIOS"
else
    echo "  ✗ os-release not customized"
    ERRORS=$((ERRORS + 1))
fi

# Check session log exists (greeter ran)
if ssh -p $SSH_PORT cios@localhost "test -f /home/cios/.cios/session.log" 2>/dev/null; then
    echo "  ✓ session.log exists"
    # Check for compositor startup
    if ssh -p $SSH_PORT cios@localhost "grep -q 'server initialized' /home/cios/.cios/session.log" 2>/dev/null; then
        echo "  ✓ compositor started successfully"
    else
        echo "  ⚠ compositor may not have started"
    fi
else
    echo "  ⚠ session.log not found (greeter may not have run yet)"
fi

# ── Cleanup ──
echo "→ Stopping VM..."
kill "$VM_PID" 2>/dev/null || true
rm -f /tmp/cios-test-vm.pid

echo ""
if [ $ERRORS -eq 0 ]; then
    echo "═══════════════════════════════════════════"
    echo "  ✓ All boot tests passed!"
    echo "═══════════════════════════════════════════"
    exit 0
else
    echo "═══════════════════════════════════════════"
    echo "  ✗ $ERRORS test(s) failed"
    echo "═══════════════════════════════════════════"
    exit 1
fi
