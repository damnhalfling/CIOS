"""Skill: Window Control — window management via CIOS Shell compositor IPC.

Provides window management operations:
- List open windows/surfaces
- Focus/activate a surface
- Close a surface
- Move/resize surfaces
- Tile surfaces (left/right/maximize/minimize)

All operations use the CIOS Shell IPC protocol (Unix socket at
$XDG_RUNTIME_DIR/cios-shell.sock). No X11 dependencies.
"""

import json
import logging
import os
import socket
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
            # Translate "cmd" → "command" for IPC protocol, add required "id"
            payload = {"v": 1, "id": f"py_{id(command)}", **command}
            if "cmd" in payload:
                payload["command"] = payload.pop("cmd")
            msg = json.dumps(payload) + "\n"
            sock.sendall(msg.encode("utf-8"))
            # Read response (newline-delimited JSON)
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            if data:
                resp = json.loads(data.decode("utf-8").strip())
                # Normalize response
                if resp.get("response") == "ok":
                    resp["ok"] = True
                elif resp.get("response") == "error":
                    resp["error"] = resp.get("reason", "unknown")
                return resp
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("IPC failed: %s", e)
    return None


@dataclass
class WindowInfo:
    """Information about an open surface."""

    wid: str  # surface ID (e.g. "s_1")
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
        """Extract app name from app_id or title."""
        if self.wm_class:
            return self.wm_class.split(".")[-1]
        return self.title.split(" - ")[-1] if " - " in self.title else self.title[:30]


# ═══════════════════════════════════════════════════════════════════════════
#  COMPOSITOR IPC OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════


def list_windows() -> list[WindowInfo]:
    """List all open surfaces via compositor IPC."""
    resp = _ipc_send({"cmd": "list_surfaces"})
    if not resp or "surfaces" not in resp:
        return []

    windows: list[WindowInfo] = []
    for s in resp["surfaces"]:
        windows.append(
            WindowInfo(
                wid=str(s.get("surface_id", s.get("id", ""))),
                desktop=0,
                pid=s.get("pid", 0),
                x=s.get("x", 0),
                y=s.get("y", 0),
                width=s.get("w", s.get("width", 0)),
                height=s.get("h", s.get("height", 0)),
                title=s.get("title", ""),
                wm_class=s.get("wm_class", s.get("app_id", "")),
            )
        )
    return windows


def find_window(query: str) -> WindowInfo | None:
    """Find a surface by title, app name, or app_id (fuzzy)."""
    query_lower = query.lower().strip()
    windows = list_windows()

    if not windows:
        return None

    # 1. app_id / WM_CLASS match
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
    """Focus/activate a surface."""
    steps = [f"Focusing: {window.title[:40]}"]
    resp = _ipc_send({"cmd": "focus_surface", "surface_id": window.wid})
    if resp and resp.get("ok"):
        return steps, True, None
    return steps, False, resp.get("error", "IPC failed") if resp else "No IPC response"


def close_window(window: WindowInfo) -> tuple[list[str], bool, str | None]:
    """Close a surface gracefully."""
    steps = [f"Closing: {window.title[:40]}"]
    resp = _ipc_send({"cmd": "close_surface", "surface_id": window.wid})
    if resp and resp.get("ok"):
        return steps, True, None
    return steps, False, resp.get("error", "IPC failed") if resp else "No IPC response"


def move_window(
    window: WindowInfo, x: int, y: int, width: int = -1, height: int = -1
) -> tuple[list[str], bool, str | None]:
    """Move and optionally resize a surface."""
    w = width if width > 0 else window.width
    h = height if height > 0 else window.height
    steps = [f"Moving: {window.title[:30]} to ({x},{y}) {w}x{h}"]
    resp = _ipc_send(
        {
            "cmd": "configure_surface",
            "surface_id": window.wid,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "maximized": False,
        }
    )
    if resp and resp.get("ok"):
        return steps, True, None
    return steps, False, resp.get("error", "IPC failed") if resp else "No IPC response"


def tile_window(window: WindowInfo, position: str) -> tuple[list[str], bool, str | None]:
    """Tile a surface: left, right, top, bottom, maximize, minimize, or quadrants."""
    steps = [f"Tiling: {window.title[:30]} → {position}"]

    if position == "maximize":
        resp = _ipc_send({"cmd": "configure_surface", "surface_id": window.wid, "maximized": True})
        if resp and resp.get("ok"):
            return steps, True, None
        return steps, False, resp.get("error", "IPC failed") if resp else "No IPC response"

    if position == "minimize":
        resp = _ipc_send({"cmd": "configure_surface", "surface_id": window.wid, "minimized": True})
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
        return move_window(window, x, y, w, h)

    return steps, False, f"Unknown position: {position}"


def get_active_window() -> WindowInfo | None:
    """Get the currently focused surface."""
    resp = _ipc_send({"cmd": "list_surfaces", "focused_only": True})
    if resp and resp.get("surfaces"):
        s = resp["surfaces"][0]
        return WindowInfo(
            wid=str(s.get("surface_id", s.get("id", ""))),
            desktop=0,
            pid=s.get("pid", 0),
            x=s.get("x", 0),
            y=s.get("y", 0),
            width=s.get("w", s.get("width", 0)),
            height=s.get("h", s.get("height", 0)),
            title=s.get("title", ""),
            wm_class=s.get("wm_class", s.get("app_id", "")),
        )
    # Fallback: return first surface from full list
    windows = list_windows()
    return windows[0] if windows else None


def get_current_desktop() -> int:
    """Get current workspace. CIOS Shell is single-workspace."""
    return 0


def switch_desktop(desktop: int) -> tuple[list[str], bool, str | None]:
    """Switch workspace. CIOS Shell is single-workspace by design."""
    return [f"Desktop {desktop}"], True, None


def _get_screen_size() -> tuple[int, int]:
    """Get screen dimensions from compositor IPC."""
    resp = _ipc_send({"cmd": "get_outputs"})
    if resp and "outputs" in resp:
        # Use primary output, or first available
        for output in resp["outputs"]:
            if output.get("primary", False):
                return output.get("width", 1920), output.get("height", 1080)
        # No primary marked — use first output
        if resp["outputs"]:
            out = resp["outputs"][0]
            return out.get("width", 1920), out.get("height", 1080)
    return 1920, 1080  # fallback if IPC unavailable
