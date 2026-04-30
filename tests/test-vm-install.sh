#!/usr/bin/env bash
# ═══════════════════════════════════════════════════
#  Symbiont — VM Installation Test
#  Validates the .deb installs correctly on a clean system.
#
#  Usage:
#    # Build the .deb first
#    bash build-deb.sh 0.9.0
#
#    # Then run this test (requires root or sudo)
#    sudo bash tests/test-vm-install.sh symbiont_0.9.0_amd64.deb
#
#  Or with Vagrant:
#    cd tests && vagrant up
# ═══════════════════════════════════════════════════
set -euo pipefail

DEB_FILE="${1:-}"
PASS=0
FAIL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
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

echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║  Symbiont — Installation Test         ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""

# ── Pre-checks ──
if [ -z "$DEB_FILE" ]; then
    # Try to find a .deb in the project root
    DEB_FILE=$(ls -1 ../symbiont_*_amd64.deb 2>/dev/null | head -1 || true)
    if [ -z "$DEB_FILE" ]; then
        DEB_FILE=$(ls -1 ./symbiont_*_amd64.deb 2>/dev/null | head -1 || true)
    fi
    if [ -z "$DEB_FILE" ]; then
        echo "  ✗ No .deb file found. Build first: bash build-deb.sh 0.9.0"
        exit 1
    fi
fi

if [ ! -f "$DEB_FILE" ]; then
    echo "  ✗ File not found: $DEB_FILE"
    exit 1
fi

echo "  Testing: $DEB_FILE"
echo ""

# ── 1. Package structure ──
echo "  [1/6] Package structure"
check "Control file exists" dpkg-deb --info "$DEB_FILE"
check "File listing works" dpkg-deb --contents "$DEB_FILE"
check "Contains symbiont python package" bash -c "dpkg-deb --contents '$DEB_FILE' | grep -q 'symbiont/__init__.py'"
check "Contains session script" bash -c "dpkg-deb --contents '$DEB_FILE' | grep -q 'symbiont-session'"
check "Contains xsession desktop" bash -c "dpkg-deb --contents '$DEB_FILE' | grep -q 'symbiont.desktop'"
check "Contains rc.xml" bash -c "dpkg-deb --contents '$DEB_FILE' | grep -q 'rc.xml'"
echo ""

# ── 2. Installation (if root) ──
if [ "$(id -u)" -eq 0 ]; then
    echo "  [2/6] Installation"
    
    # Install
    dpkg -i "$DEB_FILE" 2>/dev/null || apt-get install -f -y -qq 2>/dev/null || true
    
    check "Package is installed" dpkg -s symbiont
    check "/usr/share/symbiont exists" test -d /usr/share/symbiont
    check "Session script is executable" test -x /usr/local/bin/symbiont-session
    check "Xsession file exists" test -f /usr/share/xsessions/symbiont.desktop
    check "Openbox config exists" test -f /etc/xdg/openbox-symbiont/rc.xml
    check "Python venv exists" test -d /usr/share/symbiont/.venv
    echo ""

    # ── 3. Python imports ──
    echo "  [3/6] Python imports"
    PYTHON="/usr/share/symbiont/.venv/bin/python3"
    if [ -x "$PYTHON" ]; then
        check "import symbiont" $PYTHON -c "import symbiont"
        check "import symbiont.bridge" $PYTHON -c "import symbiont.bridge"
        check "import symbiont.intent_parser" $PYTHON -c "import symbiont.intent_parser"
        check "import symbiont.planner" $PYTHON -c "import symbiont.planner"
        check "import symbiont.mcp" $PYTHON -c "import symbiont.mcp"
        check "import symbiont.daemon" $PYTHON -c "import symbiont.daemon"
        check "import symbiont.splash" $PYTHON -c "import symbiont.splash"
        check "import symbiont.error_recovery" $PYTHON -c "import symbiont.error_recovery"
    else
        echo "  ⚠ Python venv not found, skipping import tests"
    fi
    echo ""

    # ── 4. CLI smoke test ──
    echo "  [4/6] CLI smoke test"
    if [ -x "$PYTHON" ]; then
        check "symbiont --help doesn't crash" timeout 5 $PYTHON -m symbiont.main --help 2>/dev/null || true
        check "Intent parser works" $PYTHON -c "
from symbiont.intent_parser import parse_intent
i = parse_intent('status')
assert i.type.value == 'status'
"
        check "Error recovery works" $PYTHON -c "
from symbiont.error_recovery import enrich_error
r = enrich_error('Connection failed', context={'intent': 'network'})
assert 'Quer' in r or 'Want' in r
"
    fi
    echo ""

    # ── 5. Session file validation ──
    echo "  [5/6] Session files"
    check "Desktop file has Exec" grep -q "Exec=" /usr/share/xsessions/symbiont.desktop
    check "Desktop file has Name" grep -q "Name=Symbiont" /usr/share/xsessions/symbiont.desktop
    check "Session script has openbox" grep -q "openbox" /usr/local/bin/symbiont-session
    check "Session script has splash" grep -q "splash" /usr/local/bin/symbiont-session
    check "Session script has xsetroot" grep -q "xsetroot" /usr/local/bin/symbiont-session
    echo ""

    # ── 6. Uninstall ──
    echo "  [6/6] Uninstall"
    dpkg -r symbiont 2>/dev/null || true
    check "Package removed" bash -c "! dpkg -s symbiont 2>/dev/null | grep -q 'installed'"
    check "Venv cleaned" test ! -d /usr/share/symbiont/.venv
    echo ""

else
    echo "  [2-6] Skipped (not root). Run with sudo for full test."
    echo ""
fi

# ── Summary ──
TOTAL=$((PASS + FAIL))
echo "  ═══════════════════════════════════════"
if [ $FAIL -eq 0 ]; then
    echo -e "  ${GREEN}✓ All $TOTAL checks passed${NC}"
else
    echo -e "  ${RED}✗ $FAIL/$TOTAL checks failed${NC}"
fi
echo "  ═══════════════════════════════════════"
echo ""

exit $FAIL
