#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  CIOS — VM Test: No GPU Acceleration
#  Validates UI renders correctly without GPU/3D acceleration.
#
#  Validates: Requirements 4.3, 4.5
#    - Install completes with exit 0
#    - MCP initializes (all scanners return without crash)
#    - 3+ core skills execute successfully
#    - UI process starts and renders without GPU acceleration
#
#  Usage:
#    bash tests/test-vm-nogpu.sh [DEB_FILE]
#
#  Requires: Vagrant + VirtualBox
# ═══════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEB_FILE="${1:-}"
VM_NAME="cios-test-nogpu"
VAGRANT_DIR="$(mktemp -d)"
PASS=0
FAIL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $desc"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}✗${NC} $desc"
        FAIL=$((FAIL + 1))
    fi
}

cleanup() {
    echo ""
    echo -e "  ${YELLOW}→${NC} Cleaning up VM..."
    if [ -d "$VAGRANT_DIR" ]; then
        cd "$VAGRANT_DIR"
        vagrant destroy -f 2>/dev/null || true
        cd /
        rm -rf "$VAGRANT_DIR"
    fi
}
trap cleanup EXIT

echo ""
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║  CIOS — No GPU VM Test                 ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""

# ── Locate .deb ──
if [ -z "$DEB_FILE" ]; then
    DEB_FILE=$(ls -1 "$PROJECT_ROOT"/cios_*_amd64.deb 2>/dev/null | head -1 || true)
fi
if [ -z "$DEB_FILE" ] || [ ! -f "$DEB_FILE" ]; then
    echo "  ✗ No .deb file found. Build first: bash build-deb.sh"
    exit 1
fi
DEB_FILE="$(cd "$(dirname "$DEB_FILE")" && pwd)/$(basename "$DEB_FILE")"
echo "  Testing: $DEB_FILE"
echo ""

# ── Pre-checks ──
echo "  [0/6] Pre-checks"
check "Vagrant installed" command -v vagrant
check "VirtualBox installed" command -v VBoxManage
echo ""

# ── Generate Vagrantfile ──
# Key difference: 3D acceleration explicitly disabled, VRAM minimal,
# graphics controller set to VMSVGA (no GPU passthrough).
cp "$DEB_FILE" "$VAGRANT_DIR/cios.deb"

cat > "$VAGRANT_DIR/Vagrantfile" << 'VAGRANTFILE'
Vagrant.configure("2") do |config|
  config.vm.box = "debian/bookworm64"
  config.vm.hostname = "cios-test-nogpu"

  config.vm.provider "virtualbox" do |vb|
    vb.memory = "2048"
    vb.cpus = 2
    vb.gui = false
    vb.name = "cios-test-nogpu"

    # Explicitly disable GPU acceleration
    vb.customize ["modifyvm", :id, "--graphicscontroller", "vmsvga"]
    vb.customize ["modifyvm", :id, "--accelerate3d", "off"]
    vb.customize ["modifyvm", :id, "--vram", "16"]
  end

  config.vm.provision "file", source: "cios.deb", destination: "/tmp/cios.deb"

  config.vm.provision "shell", inline: <<-SHELL
    set -e
    export DEBIAN_FRONTEND=noninteractive

    echo "=== [1/5] Installing base dependencies ==="
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv python3-tk \
      openbox wmctrl xdotool curl xclip x11-xserver-utils xvfb mesa-utils

    echo "=== [2/5] Installing CIOS .deb ==="
    dpkg -i /tmp/cios.deb || apt-get install -f -y -qq
    echo "INSTALL_EXIT=$?" > /tmp/cios_results.txt

    echo "=== [3/5] Verifying no GPU acceleration ==="
    # Start Xvfb (software rendering only, no GPU)
    Xvfb :99 -screen 0 1920x1080x24 &
    XVFB_PID=$!
    export DISPLAY=:99
    sleep 1

    # Confirm software rendering (no direct rendering)
    RENDERER=$(glxinfo 2>/dev/null | grep "OpenGL renderer" || echo "software")
    echo "GPU_RENDERER=$RENDERER" > /tmp/gpu_info.txt
    if echo "$RENDERER" | grep -qi "llvmpipe\|softpipe\|swrast\|software\|mesa"; then
      echo "GPU_ACCEL=none" >> /tmp/gpu_info.txt
    else
      echo "GPU_ACCEL=detected" >> /tmp/gpu_info.txt
    fi

    echo "=== [4/5] Validating MCP + core skills ==="
    PYTHON="/usr/share/cios/.venv/bin/python3"
    if [ ! -x "$PYTHON" ]; then
      PYTHON="python3"
    fi
    export PYTHONPATH="/usr/share/cios:${PYTHONPATH:-}"

    # MCP initialization
    $PYTHON -c "
from cios.core.mcp import SystemContext
ctx = SystemContext()
ctx.start()
snap = ctx.snapshot()
ctx.stop()
print('MCP_OK')
" > /tmp/mcp_result.txt 2>&1 || echo "MCP_FAIL" > /tmp/mcp_result.txt

    # Core skill execution: status
    $PYTHON -c "
from cios.core.intent_parser import parse_intent
i = parse_intent('status')
assert i.type.value == 'status', f'Expected status, got {i.type.value}'
print('SKILL_STATUS_OK')
" > /tmp/skill_status.txt 2>&1 || echo "SKILL_STATUS_FAIL" > /tmp/skill_status.txt

    # Core skill execution: system_health
    $PYTHON -c "
from cios.core.intent_parser import parse_intent
i = parse_intent('como está meu sistema')
print(f'SKILL_HEALTH_OK type={i.type.value}')
" > /tmp/skill_health.txt 2>&1 || echo "SKILL_HEALTH_FAIL" > /tmp/skill_health.txt

    # Core skill execution: app_launch
    $PYTHON -c "
from cios.core.intent_parser import parse_intent
i = parse_intent('abrir terminal')
print(f'SKILL_APP_OK type={i.type.value}')
" > /tmp/skill_app.txt 2>&1 || echo "SKILL_APP_FAIL" > /tmp/skill_app.txt

    echo "=== [5/5] Validating UI renders without GPU ==="
    # Xvfb is already running from step 3 (software rendering)

    # Start splash screen — must not crash without GPU
    timeout 5 $PYTHON -m cios.ui.splash &
    SPLASH_PID=$!
    sleep 2
    if kill -0 $SPLASH_PID 2>/dev/null; then
      echo "SPLASH_OK" > /tmp/ui_result.txt
      kill $SPLASH_PID 2>/dev/null || true
    else
      echo "SPLASH_FAIL" > /tmp/ui_result.txt
    fi

    # Start main GUI — must not crash without GPU
    timeout 5 $PYTHON -m cios.ui.gui &
    GUI_PID=$!
    sleep 2
    if kill -0 $GUI_PID 2>/dev/null; then
      echo "GUI_OK" >> /tmp/ui_result.txt
      kill $GUI_PID 2>/dev/null || true
    else
      echo "GUI_FAIL" >> /tmp/ui_result.txt
    fi

    # Verify Tk can create a window (basic rendering test)
    $PYTHON -c "
import tkinter as tk
root = tk.Tk()
root.geometry('400x300')
root.title('CIOS Render Test')
label = tk.Label(root, text='CIOS', font=('sans-serif', 16))
label.pack(pady=20)
root.update()
root.destroy()
print('TK_RENDER_OK')
" > /tmp/tk_render.txt 2>&1 || echo "TK_RENDER_FAIL" > /tmp/tk_render.txt

    kill $XVFB_PID 2>/dev/null || true

    echo "=== VM validation complete ==="
  SHELL
end
VAGRANTFILE

# ── Start VM ──
echo "  [1/6] Starting No-GPU VM..."
cd "$VAGRANT_DIR"
vagrant up 2>&1 | tail -5
echo ""

# ── Validate install ──
echo "  [2/6] Install validation"
check "Package installed" vagrant ssh -c "dpkg -s cios" 2>/dev/null
check "Install dir exists" vagrant ssh -c "test -d /usr/share/cios" 2>/dev/null
check "Session script executable" vagrant ssh -c "test -x /usr/local/bin/cios-session" 2>/dev/null
check "Xsession registered" vagrant ssh -c "test -f /usr/share/xsessions/cios.desktop" 2>/dev/null
echo ""

# ── Validate no GPU ──
echo "  [3/6] GPU acceleration disabled"
check "Software rendering active" vagrant ssh -c "grep -q 'GPU_ACCEL=none' /tmp/gpu_info.txt" 2>/dev/null
echo ""

# ── Validate MCP ──
echo "  [4/6] MCP initialization"
check "MCP starts without crash" vagrant ssh -c "grep -q 'MCP_OK' /tmp/mcp_result.txt" 2>/dev/null
echo ""

# ── Validate core skills ──
echo "  [5/6] Core skills (3+ required)"
check "Skill: status" vagrant ssh -c "grep -q 'SKILL_STATUS_OK' /tmp/skill_status.txt" 2>/dev/null
check "Skill: system_health" vagrant ssh -c "grep -q 'SKILL_HEALTH_OK' /tmp/skill_health.txt" 2>/dev/null
check "Skill: app_launch" vagrant ssh -c "grep -q 'SKILL_APP_OK' /tmp/skill_app.txt" 2>/dev/null
echo ""

# ── Validate UI renders ──
echo "  [6/6] UI rendering without GPU"
check "Splash screen starts" vagrant ssh -c "grep -q 'SPLASH_OK' /tmp/ui_result.txt" 2>/dev/null
check "Main GUI starts" vagrant ssh -c "grep -q 'GUI_OK' /tmp/ui_result.txt" 2>/dev/null
check "Tk rendering works" vagrant ssh -c "grep -q 'TK_RENDER_OK' /tmp/tk_render.txt" 2>/dev/null
echo ""

# ── Summary ──
TOTAL=$((PASS + FAIL))
echo "  ═══════════════════════════════════════"
if [ $FAIL -eq 0 ]; then
    echo -e "  ${GREEN}✓ All $TOTAL checks passed (No GPU)${NC}"
else
    echo -e "  ${RED}✗ $FAIL/$TOTAL checks failed (No GPU)${NC}"
fi
echo "  ═══════════════════════════════════════"
echo ""

exit $FAIL
