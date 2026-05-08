"""Multi-monitor detection and management.

Detects connected monitors and provides geometry info
for placing windows on specific screens.

Detection methods (in order):
1. xrandr --query (standard, needs x11-xserver-utils)
2. Tkinter winfo (fallback, always available if Tk works)

If xrandr is not installed, auto-installs it via apt (non-blocking suggestion).
"""

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Monitor:
    name: str  # e.g. "HDMI-1", "eDP-1"
    width: int
    height: int
    x: int  # x offset
    y: int  # y offset
    primary: bool


def detect_monitors() -> list[Monitor]:
    """Detect connected monitors.

    Tries xrandr first (accurate geometry + offsets).
    Falls back to Tkinter screen info (single logical screen).

    Returns list of monitors sorted: primary first, then by x offset.
    """
    # Try xrandr first
    monitors = _detect_via_xrandr()
    if monitors:
        logger.info("Detected %d monitor(s) via xrandr", len(monitors))
        return monitors

    # Fallback: try xrandr installation hint
    if not shutil.which("xrandr"):
        logger.warning(
            "xrandr not found — multi-monitor limited. "
            "Install with: sudo apt install x11-xserver-utils"
        )

    # Fallback: Tkinter screen detection
    monitors = _detect_via_tkinter()
    if monitors:
        logger.info("Detected %d monitor(s) via Tkinter (limited)", len(monitors))
        return monitors

    return []


def _detect_via_xrandr() -> list[Monitor]:
    """Detect monitors via xrandr --query."""
    monitors: list[Monitor] = []

    if not shutil.which("xrandr"):
        return monitors

    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.debug("xrandr returned non-zero: %s", result.stderr.strip()[:100])
            return monitors

        for line in result.stdout.splitlines():
            # Match: "HDMI-1 connected primary 1920x1080+0+0 (...)"
            # or:    "eDP-1 connected 1920x1080+1920+0 (...)"
            match = re.match(
                r"^(\S+)\s+connected\s+(primary\s+)?(\d+)x(\d+)\+(\d+)\+(\d+)",
                line,
            )
            if match:
                monitors.append(
                    Monitor(
                        name=match.group(1),
                        width=int(match.group(3)),
                        height=int(match.group(4)),
                        x=int(match.group(5)),
                        y=int(match.group(6)),
                        primary=bool(match.group(2)),
                    )
                )

    except FileNotFoundError:
        logger.debug("xrandr binary not found")
    except subprocess.TimeoutExpired:
        logger.debug("xrandr timed out")
    except Exception as e:
        logger.warning("xrandr detection failed: %s", e)

    _normalize_monitors(monitors)
    return monitors


def _detect_via_tkinter() -> list[Monitor]:
    """Fallback: detect screen geometry via Tkinter.

    This sees the full virtual screen (all monitors combined).
    Can detect multi-monitor if the virtual screen is wider than
    a single common resolution.
    """
    monitors: list[Monitor] = []

    try:
        import tkinter as tk

        # Use a temporary hidden window to query screen info
        probe = tk.Tk()
        probe.withdraw()

        screen_w = probe.winfo_screenwidth()
        screen_h = probe.winfo_screenheight()
        probe.destroy()

        if screen_w <= 0 or screen_h <= 0:
            return monitors

        # Heuristic: if virtual screen is much wider than tall,
        # it's likely multiple monitors side by side
        aspect = screen_w / screen_h

        if aspect > 2.8:
            # Likely 3+ monitors — split evenly
            n_monitors = round(aspect / 1.6)  # ~16:10 per monitor
            mon_w = screen_w // n_monitors
            for i in range(n_monitors):
                monitors.append(
                    Monitor(
                        name=f"screen-{i}",
                        width=mon_w,
                        height=screen_h,
                        x=mon_w * i,
                        y=0,
                        primary=(i == 0),
                    )
                )
        elif aspect > 1.9:
            # Likely 2 monitors side by side
            half_w = screen_w // 2
            monitors.append(
                Monitor(
                    name="screen-0",
                    width=half_w,
                    height=screen_h,
                    x=0,
                    y=0,
                    primary=True,
                )
            )
            monitors.append(
                Monitor(
                    name="screen-1",
                    width=screen_w - half_w,
                    height=screen_h,
                    x=half_w,
                    y=0,
                    primary=False,
                )
            )
        else:
            # Single monitor
            monitors.append(
                Monitor(
                    name="screen-0",
                    width=screen_w,
                    height=screen_h,
                    x=0,
                    y=0,
                    primary=True,
                )
            )

    except ImportError:
        logger.debug("Tkinter not available for screen detection")
    except Exception as e:
        logger.debug("Tkinter screen detection failed: %s", e)

    return monitors


def _normalize_monitors(monitors: list[Monitor]) -> None:
    """Sort and ensure exactly one primary monitor."""
    # Sort: primary first, then by x offset
    monitors.sort(key=lambda m: (not m.primary, m.x))

    # If no primary detected, mark the first one
    if monitors and not any(m.primary for m in monitors):
        monitors[0].primary = True


def get_secondary_monitors() -> list[Monitor]:
    """Get non-primary monitors."""
    return [m for m in detect_monitors() if not m.primary]


def get_primary_monitor() -> Monitor | None:
    """Get the primary monitor."""
    monitors = detect_monitors()
    for m in monitors:
        if m.primary:
            return m
    return monitors[0] if monitors else None
