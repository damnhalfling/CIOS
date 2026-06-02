"""Night light skill — gamma/color temperature adjustment.

Uses wlr-gamma-control or gammastep for Wayland.

#522 — Night light (gamma/color temperature)
"""

import logging
import os
import signal
import subprocess

logger = logging.getLogger(__name__)

_gammastep_pid: int | None = None


def enable_night_light(temperature: int = 3500) -> tuple[list[str], bool, str]:
    """Enable night light (warm color temperature).

    Args:
        temperature: Color temperature in Kelvin (2500-5000, lower = warmer)

    Returns:
        (steps, success, message)
    """
    global _gammastep_pid
    steps = ["Ativando luz noturna"]

    # Kill existing instance
    disable_night_light()

    try:
        proc = subprocess.Popen(
            ["gammastep", "-O", str(temperature)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _gammastep_pid = proc.pid
        return steps, True, f"Luz noturna ativada ({temperature}K)."
    except FileNotFoundError:
        # Try wlsunset as alternative
        try:
            proc = subprocess.Popen(
                ["wlsunset", "-t", str(temperature), "-T", "6500"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _gammastep_pid = proc.pid
            return steps, True, f"Luz noturna ativada ({temperature}K)."
        except FileNotFoundError:
            return steps, False, "gammastep ou wlsunset não instalado. Instale com: sudo apt install gammastep"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def disable_night_light() -> tuple[list[str], bool, str]:
    """Disable night light (restore normal colors).

    Returns:
        (steps, success, message)
    """
    global _gammastep_pid
    steps = ["Desativando luz noturna"]

    if _gammastep_pid:
        try:
            os.kill(_gammastep_pid, signal.SIGTERM)
            _gammastep_pid = None
        except ProcessLookupError:
            _gammastep_pid = None

    # Also kill any running gammastep/wlsunset
    try:
        subprocess.run(["pkill", "-f", "gammastep"], capture_output=True, timeout=3)
        subprocess.run(["pkill", "-f", "wlsunset"], capture_output=True, timeout=3)
    except Exception:
        pass

    return steps, True, "Luz noturna desativada."


def is_active() -> bool:
    """Check if night light is currently active."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "gammastep|wlsunset"],
            capture_output=True, timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def toggle_night_light(temperature: int = 3500) -> tuple[list[str], bool, str]:
    """Toggle night light on/off."""
    if is_active():
        return disable_night_light()
    return enable_night_light(temperature)
