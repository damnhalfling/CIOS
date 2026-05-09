"""Skill: Window Control — window management via compositor IPC or EWMH.

Provides window management operations:
- List open windows
- Focus/activate a window
- Close a window
- Move/resize windows
- Tile windows (left/right/maximize/minimize)
- Switch workspaces/desktops

On Wayland: uses CIOS Shell IPC (Unix socket at $XDG_RUNTIME_DIR/cios-shell.sock).
On X11 (fallback): uses wmctrl and xdotool.
"""

import json
import logging
import os
import re
import socket
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _is_wayland() -> bool:
    """Detect if running under Wayland (CIOS Shell compositor)."""
    return os.environ.get("WAYLAND_DISPLAY") is not None


def _ipc_socket_path() -> str:
    """Get the CIOS Shell IPC socket path."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(runtime_dir, "cios-shell.sock")


def _ipc_send(command: dict) -> dict | None:
    """Send a JSON command to the CIOS Shell compositor via IPC."""
    sock_path = _ipc_socket_path()
    if not os.path.exists(sock_path):
        logger.warning("cios-shell.sock not found at %s", sock_path)
        return None

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(3)
            sock.connect(sock_path)
            msg = json.dumps({"v": 1, **command}) + "\n"
            sock.sendall(msg.encode("utf-8"))
            # Read response (newline-delimited JSON)
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            if data:
                return json.loads(data.decode("utf-8").strip())
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("IPC failed: %s", e)
    return None


@dataclass
class WindowInfo:
    """Information about an open window."""

    wid: str  # window/surface ID
    desktop: int
    pid: int
    x: int
    y: int
    width: int
    height: int
    title: str
    wm_class: str = ""

    @property
    def app_name(self) -> str:
        """Extract app name from WM_CLASS or title."""
        if self.wm_class:
            return self.wm_class.split(".")[-1]
        return self.title.split(" - ")[-1] if " - " in self.title else self.title[:30]


# ═══════════════════════════════════════════════════════════════════════════
#  WAYLAND (CIOS Shell IPC)
# ═══════════════════════════════════════════════════════════════════════════


def _wayland_list_windows() -> list[WindowInfo]:
    """List surfaces via compositor IPC."""
    resp = _ipc_send({"cmd": "list_surfaces"})
    if not resp or "surfaces" not in resp:
        return []

    windows = []
    for s in resp["surfaces"]:
        windows.append(
            WindowInfo(
                wid=str(s.get("id", "")),
                desktop=s.get("output", 0),
                pid=s.get("pid", 0),
                x=s.get("x", 0),
                y=s.get("y", 0),
                width=s.get("width", 0),
                height=s.get("height", 0),
                title=s.get("title", ""),
                wm_class=s.get("app_id", ""),
            )
        )
    return windows


def _wayland_focus_window(window: WindowInfo) -> tuple[list[str], bool, str | None]:
    """Focus a surface via compositor IPC."""
    steps = [f"Focusing: {window.title[:40]}"]
    resp = _ipc_send({"cmd": "focus_surface", "id": window.wid})
    if resp and resp.get("ok"):
        return steps, True, None
    return steps, False, resp.get("error", "IPC failed") if resp else "No IPC response"


def _wayland_close_window(window: WindowInfo) -> tuple[list[str], bool, str | None]:
    """Close a surface via compositor IPC."""
    steps = [f"Closing: {window.title[:40]}"]
    resp = _ipc_send({"cmd": "close_surface", "id": window.wid})
    if resp and resp.get("ok"):
        return steps, True, None
    return steps, False, resp.get("error", "IPC failed") if resp else "No IPC response"


def _wayland_move_window(
    window: WindowInfo, x: int, y: int, width: int = -1, height: int = -1
) -> tuple[list[str], bool, str | None]:
    """Move/resize a surface via compositor IPC."""
    w = width if width > 0 else window.width
    h = height if height > 0 else window.height
    steps = [f"Moving: {window.title[:30]} to ({x},{y}) {w}x{h}"]
    resp = _ipc_send(
        {
            "cmd": "configure_surface",
            "id": window.wid,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "maximized": False,
        }
    )
    if resp and resp.get("ok"):
        return steps, True, None
    return steps, False, resp.get("error", "IPC failed") if resp else "No IPC response"


def _wayland_tile_window(
    window: WindowInfo, position: str
) -> tuple[list[str], bool, str | None]:
    """Tile a surface via compositor IPC."""
    steps = [f"Tiling: {window.title[:30]} → {position}"]

    if position == "maximize":
        resp = _ipc_send(
            {"cmd": "configure_surface", "id": window.wid, "maximized": True}
        )
        if resp and resp.get("ok"):
            return steps, True, None
        return steps, False, resp.get("error", "IPC failed") if resp else "No IPC response"

    if position == "minimize":
        resp = _ipc_send(
            {"cmd": "configure_surface", "id": window.wid, "minimized": True}
        )
        if resp and resp.get("ok"):
            return steps, True, None
        return steps, False, resp.get("error", "IPC failed") if resp else "No IPC response"

    # Get screen size from compositor
    screen_w, screen_h = _get_screen_size()
    bar_offset = 32  # topbar height

    positions = {
        "left": (0, bar_offset, screen_w // 2, screen_h - bar_offset),
        "right": (screen_w // 2, bar_offset, screen_w // 2, screen_h - bar_offset),
        "top": (0, bar_offset, screen_w, (screen_h - bar_offset) // 2),
        "bottom": (
            0,
            bar_offset + (screen_h - bar_offset) // 2,
            screen_w,
            (screen_h - bar_offset) // 2,
        ),
        "top-left": (0, bar_offset, screen_w // 2, (screen_h - bar_offset) // 2),
        "top-right": (screen_w // 2, bar_offset, screen_w // 2, (screen_h - bar_offset) // 2),
        "bottom-left": (
            0,
            bar_offset + (screen_h - bar_offset) // 2,
            screen_w // 2,
            (screen_h - bar_offset) // 2,
        ),
        "bottom-right": (
            screen_w // 2,
            bar_offset + (screen_h - bar_offset) // 2,
            screen_w // 2,
            (screen_h - bar_offset) // 2,
        ),
    }

    if position in positions:
        x, y, w, h = positions[position]
        return _wayland_move_window(window, x, y, w, h)

    return steps, False, f"Unknown position: {position}"


# ═══════════════════════════════════════════════════════════════════════════
#  X11 FALLBACK (wmctrl + xdotool)
# ═══════════════════════════════════════════════════════════════════════════


def _x11_list_windows() -> list[WindowInfo]:
    """List all open windows via wmctrl."""
    windows = []
    try:
        result = subprocess.run(
            ["wmctrl", "-l", "-G", "-p", "-x"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return windows

        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 9)
            if len(parts) >= 10:
                try:
                    windows.append(
                        WindowInfo(
                            wid=parts[0],
                            desktop=int(parts[1]),
                            pid=int(parts[2]),
                            x=int(parts[3]),
                            y=int(parts[4]),
                            width=int(parts[5]),
                            height=int(parts[6]),
                            wm_class=parts[7],
                            title=parts[9] if len(parts) > 9 else "",
                        )
                    )
                except (ValueError, IndexError):
                    continue
            elif len(parts) >= 9:
                try:
                    windows.append(
                        WindowInfo(
                            wid=parts[0],
                            desktop=int(parts[1]),
                            pid=int(parts[2]),
                            x=int(parts[3]),
                            y=int(parts[4]),
                            width=int(parts[5]),
                            height=int(parts[6]),
                            wm_class=parts[7],
                            title=parts[8] if len(parts) > 8 else "",
                        )
                    )
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        logger.warning("wmctrl not found — window control disabled")
    except Exception as e:
        logger.debug("Window list failed: %s", e)
    return windows


def _x11_focus_window(window: WindowInfo) -> tuple[list[str], bool, str | None]:
    """Activate/focus a window via wmctrl."""
    steps = [f"Focusing: {window.title[:40]}"]
    try:
        result = subprocess.run(
            ["wmctrl", "-i", "-a", window.wid],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return steps, True, None
        return steps, False, result.stderr.strip()
    except Exception as e:
        return steps, False, str(e)


def _x11_close_window(window: WindowInfo) -> tuple[list[str], bool, str | None]:
    """Close a window via wmctrl."""
    steps = [f"Closing: {window.title[:40]}"]
    try:
        result = subprocess.run(
            ["wmctrl", "-i", "-c", window.wid],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return steps, True, None
        return steps, False, result.stderr.strip()
    except Exception as e:
        return steps, False, str(e)


def _x11_move_window(
    window: WindowInfo, x: int, y: int, width: int = -1, height: int = -1
) -> tuple[list[str], bool, str | None]:
    """Move and optionally resize a window via wmctrl."""
    w = width if width > 0 else window.width
    h = height if height > 0 else window.height
    steps = [f"Moving: {window.title[:30]} to ({x},{y}) {w}x{h}"]
    try:
        subprocess.run(
            ["wmctrl", "-i", "-r", window.wid, "-b", "remove,maximized_vert,maximized_horz"],
            capture_output=True,
            timeout=3,
        )
        result = subprocess.run(
            ["wmctrl", "-i", "-r", window.wid, "-e", f"0,{x},{y},{w},{h}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return steps, True, None
        return steps, False, result.stderr.strip()
    except Exception as e:
        return steps, False, str(e)


def _x11_tile_window(window: WindowInfo, position: str) -> tuple[list[str], bool, str | None]:
    """Tile a window to a position via wmctrl/xdotool."""
    steps = [f"Tiling: {window.title[:30]} → {position}"]

    try:
        screen_w, screen_h = _get_screen_size()
        bar_offset = 28

        positions = {
            "left": (0, bar_offset, screen_w // 2, screen_h - bar_offset),
            "right": (screen_w // 2, bar_offset, screen_w // 2, screen_h - bar_offset),
            "top": (0, bar_offset, screen_w, (screen_h - bar_offset) // 2),
            "bottom": (
                0,
                bar_offset + (screen_h - bar_offset) // 2,
                screen_w,
                (screen_h - bar_offset) // 2,
            ),
            "top-left": (0, bar_offset, screen_w // 2, (screen_h - bar_offset) // 2),
            "top-right": (
                screen_w // 2,
                bar_offset,
                screen_w // 2,
                (screen_h - bar_offset) // 2,
            ),
            "bottom-left": (
                0,
                bar_offset + (screen_h - bar_offset) // 2,
                screen_w // 2,
                (screen_h - bar_offset) // 2,
            ),
            "bottom-right": (
                screen_w // 2,
                bar_offset + (screen_h - bar_offset) // 2,
                screen_w // 2,
                (screen_h - bar_offset) // 2,
            ),
        }

        if position == "maximize":
            subprocess.run(
                ["wmctrl", "-i", "-r", window.wid, "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True,
                timeout=3,
            )
            return steps, True, None

        if position == "minimize":
            subprocess.run(
                ["xdotool", "windowminimize", window.wid],
                capture_output=True,
                timeout=3,
            )
            return steps, True, None

        if position in positions:
            x, y, w, h = positions[position]
            return _x11_move_window(window, x, y, w, h)

        return steps, False, f"Unknown position: {position}"
    except Exception as e:
        return steps, False, str(e)


# ═══════════════════════════════════════════════════════════════════════════
#  PUBLIC API (auto-selects Wayland or X11)
# ═══════════════════════════════════════════════════════════════════════════


def list_windows() -> list[WindowInfo]:
    """List all open windows/surfaces."""
    if _is_wayland():
        return _wayland_list_windows()
    return _x11_list_windows()


def find_window(query: str) -> WindowInfo | None:
    """Find a window by title, app name, or WM_CLASS/app_id (fuzzy)."""
    query_lower = query.lower().strip()
    windows = list_windows()

    if not windows:
        return None

    # 1. WM_CLASS / app_id match
    for w in windows:
        if query_lower in w.wm_class.lower():
            return w

    # 2. Title match
    for w in windows:
        if query_lower in w.title.lower():
            return w

    # 3. App name match
    for w in windows:
        if query_lower in w.app_name.lower():
            return w

    return None


def focus_window(window: WindowInfo) -> tuple[list[str], bool, str | None]:
    """Activate/focus a window."""
    if _is_wayland():
        return _wayland_focus_window(window)
    return _x11_focus_window(window)


def close_window(window: WindowInfo) -> tuple[list[str], bool, str | None]:
    """Close a window gracefully."""
    if _is_wayland():
        return _wayland_close_window(window)
    return _x11_close_window(window)


def move_window(
    window: WindowInfo, x: int, y: int, width: int = -1, height: int = -1
) -> tuple[list[str], bool, str | None]:
    """Move and optionally resize a window."""
    if _is_wayland():
        return _wayland_move_window(window, x, y, width, height)
    return _x11_move_window(window, x, y, width, height)


def tile_window(window: WindowInfo, position: str) -> tuple[list[str], bool, str | None]:
    """Tile a window to a position: left, right, top, bottom, maximize, minimize."""
    if _is_wayland():
        return _wayland_tile_window(window, position)
    return _x11_tile_window(window, position)


def get_active_window() -> WindowInfo | None:
    """Get the currently focused window."""
    if _is_wayland():
        # On Wayland, get focused surface from compositor
        windows = _wayland_list_windows()
        # The compositor marks the focused surface
        # For now, return the first one (compositor should sort by focus)
        resp = _ipc_send({"cmd": "list_surfaces", "focused_only": True})
        if resp and resp.get("surfaces"):
            s = resp["surfaces"][0]
            return WindowInfo(
                wid=str(s.get("id", "")),
                desktop=s.get("output", 0),
                pid=s.get("pid", 0),
                x=s.get("x", 0),
                y=s.get("y", 0),
                width=s.get("width", 0),
                height=s.get("height", 0),
                title=s.get("title", ""),
                wm_class=s.get("app_id", ""),
            )
        return windows[0] if windows else None

    # X11 fallback
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            wid_dec = int(result.stdout.strip())
            for w in _x11_list_windows():
                try:
                    if int(w.wid, 16) == wid_dec:
                        return w
                except ValueError:
                    continue
            return WindowInfo(
                wid=hex(wid_dec),
                desktop=0,
                pid=0,
                x=0,
                y=0,
                width=0,
                height=0,
                title="Active Window",
            )
    except Exception as e:
        logger.debug("get_active_window failed: %s", e)
    return None


def get_current_desktop() -> int:
    """Get current desktop/workspace number."""
    if _is_wayland():
        # CIOS Shell is single-workspace by design
        return 0

    try:
        result = subprocess.run(
            ["wmctrl", "-d"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if "*" in line:
                    return int(line.split()[0])
    except Exception:
        pass
    return 0


def switch_desktop(desktop: int) -> tuple[list[str], bool, str | None]:
    """Switch to a different desktop/workspace."""
    if _is_wayland():
        return [f"Desktop {desktop}"], True, None  # single workspace on CIOS Shell

    steps = [f"Switching to desktop {desktop}"]
    try:
        result = subprocess.run(
            ["wmctrl", "-s", str(desktop)],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return steps, True, None
        return steps, False, result.stderr.strip()
    except Exception as e:
        return steps, False, str(e)


def _get_screen_size() -> tuple[int, int]:
    """Get screen dimensions."""
    if _is_wayland():
        # Ask compositor for output dimensions
        resp = _ipc_send({"cmd": "list_surfaces"})
        # Fallback: use environment or default
        # TODO: add get_outputs IPC command
        pass

    try:
        result = subprocess.run(
            ["xdpyinfo"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            match = re.search(r"dimensions:\s+(\d+)x(\d+)", result.stdout)
            if match:
                return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return 1920, 1080  # fallback
