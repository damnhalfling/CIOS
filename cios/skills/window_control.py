"""Skill: Window Control — EWMH-based window management.

Provides window management operations using EWMH (Extended Window Manager Hints):
- List open windows
- Focus/activate a window
- Close a window
- Move/resize windows
- Tile windows (left/right/maximize/minimize)
- Switch workspaces/desktops

Uses wmctrl and xdotool for X11 window manipulation.
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    """Information about an open window."""
    wid: str  # hex window ID
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


def list_windows() -> list[WindowInfo]:
    """List all open windows with WM_CLASS for better matching."""
    windows = []
    try:
        # Use -x flag to get WM_CLASS alongside geometry and PID
        result = subprocess.run(
            ["wmctrl", "-l", "-G", "-p", "-x"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return windows

        for line in result.stdout.strip().splitlines():
            # Format with -x: WID DESKTOP PID X Y W H WM_CLASS HOST TITLE
            parts = line.split(None, 9)
            if len(parts) >= 10:
                try:
                    windows.append(WindowInfo(
                        wid=parts[0],
                        desktop=int(parts[1]),
                        pid=int(parts[2]),
                        x=int(parts[3]),
                        y=int(parts[4]),
                        width=int(parts[5]),
                        height=int(parts[6]),
                        wm_class=parts[7],
                        title=parts[9] if len(parts) > 9 else "",
                    ))
                except (ValueError, IndexError):
                    continue
            elif len(parts) >= 9:
                # Fallback: title might be merged
                try:
                    windows.append(WindowInfo(
                        wid=parts[0],
                        desktop=int(parts[1]),
                        pid=int(parts[2]),
                        x=int(parts[3]),
                        y=int(parts[4]),
                        width=int(parts[5]),
                        height=int(parts[6]),
                        wm_class=parts[7],
                        title=parts[8] if len(parts) > 8 else "",
                    ))
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        logger.warning("wmctrl not found — window control disabled")
    except Exception as e:
        logger.debug("Window list failed: %s", e)
    return windows


def find_window(query: str) -> Optional[WindowInfo]:
    """Find a window by title, app name, or WM_CLASS (fuzzy).

    Search order:
    1. WM_CLASS contains query (most reliable — e.g. "firefox" matches "Navigator.firefox")
    2. Title contains query
    3. App name contains query
    """
    query_lower = query.lower().strip()
    windows = list_windows()

    if not windows:
        return None

    # 1. WM_CLASS match (most reliable for app names)
    for w in windows:
        if query_lower in w.wm_class.lower():
            return w

    # 2. Title match
    for w in windows:
        if query_lower in w.title.lower():
            return w

    # 3. App name match (derived from wm_class or title)
    for w in windows:
        if query_lower in w.app_name.lower():
            return w

    return None


def focus_window(window: WindowInfo) -> tuple[list[str], bool, Optional[str]]:
    """Activate/focus a window."""
    steps = [f"Focusing: {window.title[:40]}"]
    try:
        result = subprocess.run(
            ["wmctrl", "-i", "-a", window.wid],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return steps, True, None
        return steps, False, result.stderr.strip()
    except Exception as e:
        return steps, False, str(e)


def close_window(window: WindowInfo) -> tuple[list[str], bool, Optional[str]]:
    """Close a window gracefully."""
    steps = [f"Closing: {window.title[:40]}"]
    try:
        result = subprocess.run(
            ["wmctrl", "-i", "-c", window.wid],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return steps, True, None
        return steps, False, result.stderr.strip()
    except Exception as e:
        return steps, False, str(e)


def move_window(window: WindowInfo, x: int, y: int, width: int = -1, height: int = -1) -> tuple[list[str], bool, Optional[str]]:
    """Move and optionally resize a window."""
    w = width if width > 0 else window.width
    h = height if height > 0 else window.height
    steps = [f"Moving: {window.title[:30]} to ({x},{y}) {w}x{h}"]
    try:
        # Remove maximized state first
        subprocess.run(
            ["wmctrl", "-i", "-r", window.wid, "-b", "remove,maximized_vert,maximized_horz"],
            capture_output=True, timeout=3,
        )
        result = subprocess.run(
            ["wmctrl", "-i", "-r", window.wid, "-e", f"0,{x},{y},{w},{h}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return steps, True, None
        return steps, False, result.stderr.strip()
    except Exception as e:
        return steps, False, str(e)


def tile_window(window: WindowInfo, position: str) -> tuple[list[str], bool, Optional[str]]:
    """Tile a window to a position: left, right, top, bottom, maximize, minimize."""
    steps = [f"Tiling: {window.title[:30]} → {position}"]

    try:
        # Get screen dimensions
        screen_w, screen_h = _get_screen_size()
        bar_offset = 28  # top bar height

        positions = {
            "left": (0, bar_offset, screen_w // 2, screen_h - bar_offset),
            "right": (screen_w // 2, bar_offset, screen_w // 2, screen_h - bar_offset),
            "top": (0, bar_offset, screen_w, (screen_h - bar_offset) // 2),
            "bottom": (0, bar_offset + (screen_h - bar_offset) // 2, screen_w, (screen_h - bar_offset) // 2),
            "top-left": (0, bar_offset, screen_w // 2, (screen_h - bar_offset) // 2),
            "top-right": (screen_w // 2, bar_offset, screen_w // 2, (screen_h - bar_offset) // 2),
            "bottom-left": (0, bar_offset + (screen_h - bar_offset) // 2, screen_w // 2, (screen_h - bar_offset) // 2),
            "bottom-right": (screen_w // 2, bar_offset + (screen_h - bar_offset) // 2, screen_w // 2, (screen_h - bar_offset) // 2),
        }

        if position == "maximize":
            subprocess.run(
                ["wmctrl", "-i", "-r", window.wid, "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True, timeout=3,
            )
            return steps, True, None

        if position == "minimize":
            subprocess.run(
                ["xdotool", "windowminimize", window.wid],
                capture_output=True, timeout=3,
            )
            return steps, True, None

        if position in positions:
            x, y, w, h = positions[position]
            return move_window(window, x, y, w, h)

        return steps, False, f"Unknown position: {position}"
    except Exception as e:
        return steps, False, str(e)


def get_active_window() -> Optional[WindowInfo]:
    """Get the currently focused window."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            wid_dec = int(result.stdout.strip())
            # Find in window list — compare as integers
            for w in list_windows():
                try:
                    if int(w.wid, 16) == wid_dec:
                        return w
                except ValueError:
                    continue
            # If not found in wmctrl list, build a minimal WindowInfo
            # This happens when wmctrl and xdotool disagree on window IDs
            return WindowInfo(
                wid=hex(wid_dec),
                desktop=0, pid=0, x=0, y=0, width=0, height=0,
                title="Active Window",
            )
    except Exception as e:
        logger.debug("get_active_window failed: %s", e)
    return None


def get_current_desktop() -> int:
    """Get current desktop/workspace number."""
    try:
        result = subprocess.run(
            ["wmctrl", "-d"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if "*" in line:
                    return int(line.split()[0])
    except Exception:
        pass
    return 0


def switch_desktop(desktop: int) -> tuple[list[str], bool, Optional[str]]:
    """Switch to a different desktop/workspace."""
    steps = [f"Switching to desktop {desktop}"]
    try:
        result = subprocess.run(
            ["wmctrl", "-s", str(desktop)],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return steps, True, None
        return steps, False, result.stderr.strip()
    except Exception as e:
        return steps, False, str(e)


def _get_screen_size() -> tuple[int, int]:
    """Get screen dimensions."""
    try:
        result = subprocess.run(
            ["xdpyinfo"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            match = re.search(r"dimensions:\s+(\d+)x(\d+)", result.stdout)
            if match:
                return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return 1920, 1080  # fallback
