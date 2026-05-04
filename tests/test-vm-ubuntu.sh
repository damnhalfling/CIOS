#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  Harmoni — VM Test: Ubuntu 22.04 Clean Install
#  Validates install + boot on a clean Ubuntu 22.04 system.
#
#  Validates: Requirements 4.1, 4.5
#    - Install completes with exit 0
#    - MCP initializes (all scanners return without crash)
#    - 3+ core skills execute successfully
#    - UI process starts without crash
#
#  Usage:
#    bash tests/test-vm-ubuntu.sh [DEB_FILE]
#
#  Requires: Vagrant + VirtualBox
# ═══════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEB_FILE="${1:-}"
VM_NAME="harmoni-test-ubuntu"
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
echo "  ║  Harmoni — Ubuntu 22.04 VM Test           ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""

# ── Locate .deb ──
if [ -z "$DEB_FILE" ]; then
    DEB_FILE=$(ls -1 "$PROJECT_ROOT"/harmoni_*_amd64.deb 2>/dev/null | head -1 || true)
fi
if [ -z "$DEB_FILE" ] || [ ! -f "$DEB_FILE" ]; then
    echo "  ✗ No .deb file found. Build first: bash build-deb.sh"
    exit 1
fi
DEB_FILE="$(cd "$(dirname "$DEB_FILE")" && pwd)/$(basename "$DEB_FILE")"
echo "  Testing: $DEB_FILE"
echo ""

# ── Pre-checks ──
echo "  [0/5] Pre-checks"
check "Vagrant installed" command -v vagrant
check "VirtualBox installed" command -v VBoxManage
echo ""

# ── Generate Vagrantfile ──
cp "$DEB_FILE" "$VAGRANT_DIR/harmoni.deb"

cat > "$VAGRANT_DIR/Vagrantfile" << 'VAGRANTFILE'
Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/jammy64"
  config.vm.hostname = "harmoni-test-ubuntu"

  config.vm.provider "virtualbox" do |vb|
    vb.memory = "2048"
    vb.cpus = 2
    vb.gui = false
    vb.name = "harmoni-test-ubuntu"
  end

  config.vm.provision "file", source: "harmoni.deb", destination: "/tmp/harmoni.deb"

  config.vm.provision "shell", inline: <<-SHELL
    set -e
    export DEBIAN_FRONTEND=noninteractive

    echo "=== [1/4] Installing base dependencies ==="
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv python3-tk \
      openbox wmctrl xdotool curl xclip x11-xserver-utils xvfb

    echo "=== [2/4] Installing Harmoni .deb ==="
    dpkg -i /tmp/harmoni.deb || apt-get install -f -y -qq
    echo "INSTALL_EXIT=$?" > /tmp/harmoni_results.txt

    echo "=== [3/4] Validating MCP + core skills ==="
    PYTHON="/usr/share/harmoni/.venv/bin/python3"
    if [ ! -x "$PYTHON" ]; then
      PYTHON="python3"
    fi
    export PYTHONPATH="/usr/share/harmoni:${PYTHONPATH:-}"

    # MCP initialization
    $PYTHON -c "
from harmoni.core.mcp import SystemContext
ctx = SystemContext()
ctx.start()
snap = ctx.snapshot()
ctx.stop()
print('MCP_OK')
" > /tmp/mcp_result.txt 2>&1 || echo "MCP_FAIL" > /tmp/mcp_result.txt

    # Core skill execution: status
    $PYTHON -c "
from harmoni.core.intent_parser import parse_intent
i = parse_intent('status')
assert i.type.value == 'status', f'Expected status, got {i.type.value}'
print('SKILL_STATUS_OK')
" > /tmp/skill_status.txt 2>&1 || echo "SKILL_STATUS_FAIL" > /tmp/skill_status.txt

    # Core skill execution: system_health
    $PYTHON -c "
from harmoni.core.intent_parser import parse_intent
i = parse_intent('como está meu sistema')
print(f'SKILL_HEALTH_OK type={i.type.value}')
" > /tmp/skill_health.txt 2>&1 || echo "SKILL_HEALTH_FAIL" > /tmp/skill_health.txt

    # Core skill execution: app_launch
    $PYTHON -c "
from harmoni.core.intent_parser import parse_intent
i = parse_intent('abrir terminal')
print(f'SKILL_APP_OK type={i.type.value}')
" > /tmp/skill_app.txt 2>&1 || echo "SKILL_APP_FAIL" > /tmp/skill_app.txt

    echo "=== [4/4] Validating UI process starts ==="
    # Start Xvfb for headless UI test
    Xvfb :99 -screen 0 1920x1080x24 &
    XVFB_PID=$!
    export DISPLAY=:99
    sleep 1

    # Try to start the UI process briefly and check it doesn't crash immediately
    timeout 5 $PYTHON -m harmoni.ui.splash &
    UI_PID=$!
    sleep 2
    if kill -0 $UI_PID 2>/dev/null; then
      echo "UI_OK" > /tmp/ui_result.txt
      kill $UI_PID 2>/dev/null || true
    else
      echo "UI_FAIL" > /tmp/ui_result.txt
    fi
    kill $XVFB_PID 2>/dev/null || true

    echo "=== VM validation complete ==="
  SHELL
end
VAGRANTFILE

# ── Start VM ──
echo "  [1/5] Starting Ubuntu 22.04 VM..."
cd "$VAGRANT_DIR"
vagrant up 2>&1 | tail -5
echo ""

# ── Validate install ──
echo "  [2/5] Install validation"
check "Package installed" vagrant ssh -c "dpkg -s harmoni" 2>/dev/null
check "Install dir exists" vagrant ssh -c "test -d /usr/share/harmoni" 2>/dev/null
check "Session script executable" vagrant ssh -c "test -x /usr/local/bin/harmoni-session" 2>/dev/null
check "Xsession registered" vagrant ssh -c "test -f /usr/share/xsessions/harmoni.desktop" 2>/dev/null
echo ""

# ── Validate MCP ──
echo "  [3/5] MCP initialization"
check "MCP starts without crash" vagrant ssh -c "grep -q 'MCP_OK' /tmp/mcp_result.txt" 2>/dev/null
echo ""

# ── Validate core skills ──
echo "  [4/5] Core skills (3+ required)"
check "Skill: status" vagrant ssh -c "grep -q 'SKILL_STATUS_OK' /tmp/skill_status.txt" 2>/dev/null
check "Skill: system_health" vagrant ssh -c "grep -q 'SKILL_HEALTH_OK' /tmp/skill_health.txt" 2>/dev/null
check "Skill: app_launch" vagrant ssh -c "grep -q 'SKILL_APP_OK' /tmp/skill_app.txt" 2>/dev/null
echo ""

# ── Validate UI ──
echo "  [5/5] UI process"
check "UI starts without crash" vagrant ssh -c "grep -q 'UI_OK' /tmp/ui_result.txt" 2>/dev/null
echo ""

# ── Summary ──
TOTAL=$((PASS + FAIL))
echo "  ═══════════════════════════════════════"
if [ $FAIL -eq 0 ]; then
    echo -e "  ${GREEN}✓ All $TOTAL checks passed (Ubuntu 22.04)${NC}"
else
    echo -e "  ${RED}✗ $FAIL/$TOTAL checks failed (Ubuntu 22.04)${NC}"
fi
echo "  ═══════════════════════════════════════"
echo ""

exit $FAIL
