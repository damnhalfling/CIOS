"""Display settings skill — resolution, scaling, refresh rate via intent.

Uses wlr-randr (Wayland) to configure displays.
Falls back to compositor IPC for monitor arrangement.

#508 — Display settings: resolução/scaling via intent
#509 — Display settings: arranjo de monitores
"""

import json
import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DisplayInfo:
    """Information about a connected display."""
    name: str  # e.g. "eDP-1", "HDMI-A-1"
    resolution: str  # e.g. "1920x1080"
    refresh_rate: float  # e.g. 60.0
    scale: float  # e.g. 1.0, 1.5, 2.0
    position: str  # e.g. "0,0"
    enabled: bool
    primary: bool


def list_displays() -> list[DisplayInfo]:
    """List all connected displays with their current settings."""
    displays = []
    try:
        result = subprocess.run(
            ["wlr-randr", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            for output in data:
                name = output.get("name", "")
                enabled = output.get("enabled", False)
                modes = output.get("modes", [])
                current_mode = next((m for m in modes if m.get("current")), None)

                displays.append(DisplayInfo(
                    name=name,
                    resolution=f"{current_mode['width']}x{current_mode['height']}" if current_mode else "unknown",
                    refresh_rate=current_mode.get("refresh", 60.0) / 1000 if current_mode else 60.0,
                    scale=output.get("scale", 1.0),
                    position=f"{output.get('x', 0)},{output.get('y', 0)}",
                    enabled=enabled,
                    primary=output.get("x", 0) == 0 and output.get("y", 0) == 0,
                ))
            return displays
    except FileNotFoundError:
        logger.debug("wlr-randr not found, trying fallback")
    except Exception as e:
        logger.warning("wlr-randr failed: %s", e)

    # Fallback: parse wlr-randr text output
    try:
        result = subprocess.run(
            ["wlr-randr"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            displays = _parse_wlr_randr_text(result.stdout)
    except Exception as e:
        logger.warning("Display listing failed: %s", e)

    return displays


def set_resolution(output: str, width: int, height: int, refresh: float | None = None) -> tuple[bool, str]:
    """Set resolution for a display.

    Args:
        output: Display name (e.g. "eDP-1")
        width: Width in pixels
        height: Height in pixels
        refresh: Refresh rate in Hz (optional)

    Returns:
        (success, message)
    """
    mode = f"{width}x{height}"
    cmd = ["wlr-randr", "--output", output, "--mode", mode]
    if refresh:
        cmd.extend(["--custom-mode", f"{width}x{height}@{refresh}"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return True, f"Resolução de {output} alterada para {mode}."
        return False, f"Falha ao alterar resolução: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Erro: {e}"


def set_scale(output: str, scale: float) -> tuple[bool, str]:
    """Set scaling factor for a display.

    Args:
        output: Display name
        scale: Scale factor (1.0, 1.25, 1.5, 2.0)

    Returns:
        (success, message)
    """
    try:
        result = subprocess.run(
            ["wlr-randr", "--output", output, "--scale", str(scale)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return True, f"Escala de {output} alterada para {scale}x."
        return False, f"Falha ao alterar escala: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Erro: {e}"


def set_position(output: str, x: int, y: int) -> tuple[bool, str]:
    """Set position of a display (for multi-monitor arrangement).

    Args:
        output: Display name
        x: X position
        y: Y position

    Returns:
        (success, message)
    """
    try:
        result = subprocess.run(
            ["wlr-randr", "--output", output, "--pos", f"{x},{y}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return True, f"Posição de {output} alterada para ({x}, {y})."
        return False, f"Falha: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Erro: {e}"


def enable_output(output: str) -> tuple[bool, str]:
    """Enable a display output."""
    try:
        result = subprocess.run(
            ["wlr-randr", "--output", output, "--on"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return True, f"{output} ativado."
        return False, f"Falha: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Erro: {e}"


def disable_output(output: str) -> tuple[bool, str]:
    """Disable a display output."""
    try:
        result = subprocess.run(
            ["wlr-randr", "--output", output, "--off"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return True, f"{output} desativado."
        return False, f"Falha: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Erro: {e}"


def _parse_wlr_randr_text(output: str) -> list[DisplayInfo]:
    """Parse wlr-randr text output (fallback when --json not available)."""
    displays = []
    current_name = ""
    current_enabled = False

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Output name line (not indented)
        if not line.startswith(" ") and " " not in line.split("(")[0]:
            current_name = line.split(" ")[0]
            current_enabled = "enabled" in line.lower() if "(" in line else True
        elif "current" in line.lower() and "x" in line:
            # Mode line with "current" marker
            parts = line.split()
            if parts:
                mode = parts[0]  # e.g. "1920x1080"
                displays.append(DisplayInfo(
                    name=current_name,
                    resolution=mode,
                    refresh_rate=60.0,
                    scale=1.0,
                    position="0,0",
                    enabled=current_enabled,
                    primary=len(displays) == 0,
                ))

    return displays
