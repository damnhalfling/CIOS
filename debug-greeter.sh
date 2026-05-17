#!/bin/bash
# Run this inside the VM to diagnose the black screen issue
# Usage: bash debug-greeter.sh > /tmp/debug.log 2>&1

echo "=== CIOS Greeter Debug ==="
echo "Date: $(date)"
echo ""

echo "=== 1. greetd status ==="
systemctl status greetd 2>&1 | head -20
echo ""

echo "=== 2. greetd journal ==="
journalctl -u greetd --no-pager -n 50 2>&1
echo ""

echo "=== 3. Session log ==="
cat ~/.cios/session.log 2>/dev/null || echo "(not found)"
echo ""

echo "=== 4. greetd config ==="
cat /etc/greetd/config.toml 2>/dev/null || echo "(not found)"
echo ""

echo "=== 5. cios-greeter-session script ==="
cat /usr/local/bin/cios-greeter-session 2>/dev/null || echo "(not found)"
echo ""

echo "=== 6. Python check ==="
echo "venv python:"
/usr/share/cios/.venv/bin/python3 --version 2>&1
echo "gi available:"
/usr/share/cios/.venv/bin/python3 -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk; print('GTK4 OK')" 2>&1
echo "system python:"
python3 --version 2>&1
python3 -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk; print('GTK4 OK')" 2>&1
echo ""

echo "=== 7. Greeter module check ==="
/usr/share/cios/.venv/bin/python3 -c "import cios.ui.gtk.greeter; print('greeter module OK')" 2>&1
python3 -c "import cios.ui.gtk.greeter; print('greeter module OK')" 2>&1
echo ""

echo "=== 8. cios-shell binary ==="
which cios-shell 2>&1
cios-shell --version 2>&1
ldd /usr/bin/cios-shell 2>&1 | grep "not found"
echo ""

echo "=== 9. Running processes ==="
ps aux | grep -E "cios|greet|python|wayland" | grep -v grep
echo ""

echo "=== 10. GREETD_SOCK ==="
echo "GREETD_SOCK=$GREETD_SOCK"
ls -la /run/greetd* 2>/dev/null
echo ""

echo "=== 11. XDG_RUNTIME_DIR ==="
echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
ls -la ${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/ 2>/dev/null | head -10
echo ""

echo "=== 12. dmesg GPU errors ==="
dmesg | grep -iE "drm|gpu|error|fail" | tail -10
echo ""

echo "=== 13. Try running greeter directly ==="
export GREETD_SOCK="/tmp/fake-greetd.sock"
export WAYLAND_DISPLAY="wayland-0"
export GDK_BACKEND=wayland
timeout 3 /usr/share/cios/.venv/bin/python3 -m cios.ui.gtk.greeter 2>&1 || echo "exit code: $?"
echo ""

echo "=== DEBUG COMPLETE ==="
