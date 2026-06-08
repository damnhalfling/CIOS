"""Window Manager — Move apps between sidebar/foreground/fullscreen.

Provides compositor-level window control via available backends:
1. CIOS Shell IPC (native, preferred)
2. wlr-randr + compositor hints (Wayland fallback)
3. xdotool + wmctrl (X11/XWayland fallback)

Usage:
    from cios.skills.window_manager import move_to_sidebar, move_to_foreground

    move_to_sidebar("firefox")
    move_to_foreground("firefox")
"""

import json
import logging
import os
import socket
import subprocess

logger = logging.getLogger(__name__)


def move_to_sidebar(target: str) -> tuple[bool, str]:
    """Move a window to sidebar mode (small, non-intrusive, on-top).

    Args:
        target: Window title substring, WM_CLASS, or PID.

    Returns (success, message).
    """
    # Try CIOS Shell IPC first
    surface_id = _find_surface_by_target(target)
    if surface_id:
        geometry = _calculate_sidebar_geometry()
        ok = _shell_configure(surface_id, geometry=geometry, layer="top", ontop=True)
        if ok:
            return True, f"'{target}' movido para sidebar"

    # Fallback: xdotool (XWayland)
    wid = _find_window_xdotool(target)
    if wid:
        try:
            w, h = 420, 236  # 16:9 small
            screen_w, screen_h = _get_screen_size()
            x = screen_w - w - 20
            y = screen_h - h - 52

            subprocess.run(
                ["xdotool", "windowsize", wid, str(w), str(h)],
                capture_output=True,
                timeout=3,
            )
            subprocess.run(
                ["xdotool", "windowmove", wid, str(x), str(y)],
                capture_output=True,
                timeout=3,
            )
            # Set always-on-top via wmctrl
            subprocess.run(
                ["wmctrl", "-i", "-r", wid, "-b", "add,above"],
                capture_output=True,
                timeout=3,
            )
            return True, f"'{target}' movido para sidebar"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return False, f"Janela '{target}' não encontrada"


def move_to_foreground(target: str) -> tuple[bool, str]:
    """Move a window back to foreground (normal size, remove on-top).

    Args:
        target: Window title substring, WM_CLASS, or PID.

    Returns (success, message).
    """
    surface_id = _find_surface_by_target(target)
    if surface_id:
        ok = _shell_configure(surface_id, layer="normal", ontop=False, maximize=True)
        if ok:
            return True, f"'{target}' em primeiro plano"

    # Fallback: xdotool
    wid = _find_window_xdotool(target)
    if wid:
        try:
            subprocess.run(
                ["wmctrl", "-i", "-r", wid, "-b", "remove,above"],
                capture_output=True,
                timeout=3,
            )
            subprocess.run(
                ["xdotool", "windowactivate", wid],
                capture_output=True,
                timeout=3,
            )
            # Maximize
            subprocess.run(
                ["wmctrl", "-i", "-r", wid, "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True,
                timeout=3,
            )
            return True, f"'{target}' em primeiro plano"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return False, f"Janela '{target}' não encontrada"


def move_to_fullscreen(target: str) -> tuple[bool, str]:
    """Make a window fullscreen.

    Args:
        target: Window title substring, WM_CLASS, or PID.

    Returns (success, message).
    """
    surface_id = _find_surface_by_target(target)
    if surface_id:
        ok = _shell_configure(surface_id, fullscreen=True)
        if ok:
            return True, f"'{target}' em tela cheia"

    wid = _find_window_xdotool(target)
    if wid:
        try:
            subprocess.run(
                ["wmctrl", "-i", "-r", wid, "-b", "add,fullscreen"],
                capture_output=True,
                timeout=3,
            )
            return True, f"'{target}' em tela cheia"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return False, f"Janela '{target}' não encontrada"


# ═══════════════════════════════════════════════════════════════════════════
#  SHELL IPC (preferred — native compositor control)
# ═══════════════════════════════════════════════════════════════════════════


def _get_shell_socket_path() -> str:
    """Get CIOS Shell IPC socket path."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(runtime_dir, "cios-shell.sock")


def _shell_command(command: dict) -> dict | None:
    """Send a command to CIOS Shell via IPC."""
    sock_path = _get_shell_socket_path()
    if not os.path.exists(sock_path):
        return None

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(sock_path)

        msg = json.dumps(command) + "\n"
        sock.sendall(msg.encode())

        response = sock.recv(4096)
        sock.close()

        if response:
            return json.loads(response.decode().strip())
    except (ConnectionRefusedError, OSError, json.JSONDecodeError):
        pass

    return None


def _shell_list_surfaces() -> list[dict]:
    """List all surfaces known to the shell."""
    result = _shell_command({"v": 1, "id": "wm-list", "command": "list_surfaces"})
    if result and result.get("response") == "surfaces":
        return result.get("surfaces", [])
    return []


def _find_surface_by_target(target: str) -> str | None:
    """Find a surface ID by title, class, or PID."""
    surfaces = _shell_list_surfaces()
    target_lower = target.lower()

    for surface in surfaces:
        title = surface.get("title", "").lower()
        wm_class = surface.get("wm_class", "").lower()
        pid = str(surface.get("pid", ""))

        if target_lower in title or target_lower in wm_class or target == pid:
            return surface.get("surface_id")

    return None


def _shell_configure(
    surface_id: str,
    geometry: str | None = None,
    layer: str | None = None,
    ontop: bool | None = None,
    maximize: bool = False,
    fullscreen: bool = False,
) -> bool:
    """Configure a surface via shell IPC."""
    cmd: dict = {
        "v": 1,
        "id": f"wm-cfg-{surface_id}",
        "command": "configure_surface",
        "surface_id": surface_id,
    }

    if geometry:
        # Parse "WxH+X+Y" or "WxH+X-Y" format
        parts = geometry.replace("-", "+-").split("+")
        if len(parts) >= 3:
            wh = parts[0].split("x")
            if len(wh) == 2:
                cmd["w"] = int(wh[0])
                cmd["h"] = int(wh[1])
                cmd["x"] = int(parts[1])
                cmd["y"] = int(parts[2])

    if layer:
        cmd["layer"] = layer

    if ontop is not None:
        cmd["ontop"] = ontop

    if fullscreen:
        cmd["fullscreen"] = True

    if maximize:
        cmd["maximize"] = True

    result = _shell_command(cmd)
    return result is not None and result.get("response") == "ok"


# ═══════════════════════════════════════════════════════════════════════════
#  XDOTOOL FALLBACK
# ═══════════════════════════════════════════════════════════════════════════


def _find_window_xdotool(target: str) -> str | None:
    """Find a window ID using xdotool."""
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", target],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Return first match
            return result.stdout.strip().splitlines()[0]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Try by class
    try:
        result = subprocess.run(
            ["xdotool", "search", "--class", target],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[0]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def _get_screen_size() -> tuple[int, int]:
    """Get screen dimensions."""
    try:
        result = subprocess.run(
            ["xdpyinfo"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "dimensions:" in line:
                    parts = line.split()
                    for part in parts:
                        if "x" in part and part[0].isdigit():
                            w, h = part.split("x")
                            return int(w), int(h)
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return 1920, 1080


def _calculate_sidebar_geometry() -> str:
    """Calculate sidebar geometry string."""
    w, h = _get_screen_size()
    sw = max(360, int(w * 0.22))
    sh = int(sw * 9 / 16)
    x = w - sw - 20
    y = h - sh - 52
    return f"{sw}x{sh}+{x}+{y}"
