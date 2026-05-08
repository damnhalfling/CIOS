"""Power skill — battery status and brightness control.

No LLM. Direct execution via /sys and brightnessctl.
"""

import logging
import os
import subprocess

import psutil

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  BATTERY
# ═══════════════════════════════════════════════════════════════════════════


def get_battery() -> dict:
    """Get battery status.

    Returns dict with: present, percent, charging, time_remaining, plugged
    """
    battery = psutil.sensors_battery()
    if not battery:
        return {
            "present": False,
            "percent": 100,
            "charging": False,
            "time_remaining": "",
            "plugged": True,
        }

    time_str = ""
    if battery.secsleft > 0 and not battery.power_plugged:
        mins = battery.secsleft // 60
        hours = mins // 60
        remaining = mins % 60
        time_str = f"{hours}h{remaining:02d}m"

    return {
        "present": True,
        "percent": int(battery.percent),
        "charging": bool(battery.power_plugged),
        "time_remaining": time_str,
        "plugged": bool(battery.power_plugged),
    }


def battery_summary() -> tuple[list[str], str]:
    """Get human-friendly battery summary.

    Returns: (plan_steps, summary)
    """
    info = get_battery()
    steps = ["Checking battery"]

    if not info["present"]:
        return steps, "No battery detected — running on AC power"

    pct = info["percent"]
    if info["charging"]:
        summary = f"Battery: {pct}% ⚡ Charging"
    elif info["time_remaining"]:
        summary = f"Battery: {pct}% — {info['time_remaining']} remaining"
    else:
        summary = f"Battery: {pct}%"

    if pct < 15:
        summary += "\n⚠ Battery critically low!"
    elif pct < 30:
        summary += "\n⚠ Battery getting low"

    return steps, summary


# ═══════════════════════════════════════════════════════════════════════════
#  BRIGHTNESS
# ═══════════════════════════════════════════════════════════════════════════


def _run_brightness(*args: str) -> tuple[bool, str, str]:
    """Run brightnessctl command."""
    try:
        result = subprocess.run(
            ["brightnessctl"] + list(args),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", "brightnessctl not found"
    except Exception as e:
        return False, "", str(e)


def brightness_available() -> bool:
    """Check if brightness control is available."""
    ok, _, _ = _run_brightness("info")
    return ok


def get_brightness() -> int:
    """Get current brightness (0-100). Returns -1 if unavailable."""
    ok, stdout, _ = _run_brightness("info")
    if not ok:
        return -1
    # Parse: "Current brightness: 1234 (56%)"
    for line in stdout.splitlines():
        if "%" in line:
            import re

            match = re.search(r"\((\d+)%\)", line)
            if match:
                return int(match.group(1))
    return -1


def set_brightness(level: int) -> tuple[list[str], bool, str]:
    """Set brightness to a specific level (0-100)."""
    level = max(1, min(100, level))  # never go to 0 (black screen)
    ok, _, stderr = _run_brightness("set", f"{level}%")
    if ok:
        return [f"Setting brightness to {level}%"], True, f"Brightness: {level}%"
    return ["Adjusting brightness"], False, _humanize_error(stderr)


def change_brightness(delta: int) -> tuple[list[str], bool, str]:
    """Change brightness by delta (positive = up, negative = down)."""
    if delta > 0:
        ok, _, stderr = _run_brightness("set", f"+{delta}%")
    else:
        ok, _, stderr = _run_brightness("set", f"{abs(delta)}%-")
    if ok:
        new = get_brightness()
        direction = "up" if delta > 0 else "down"
        return [f"Brightness {direction}"], True, f"Brightness: {new}%"
    return ["Adjusting brightness"], False, _humanize_error(stderr)


# ═══════════════════════════════════════════════════════════════════════════
#  POWER SAVING
# ═══════════════════════════════════════════════════════════════════════════


def enable_power_saving() -> tuple[list[str], bool, str]:
    """Enable power saving mode: reduce brightness + set CPU to powersave."""
    steps = ["Enabling power saving mode"]
    errors = []

    # Reduce brightness to 30%
    ok, _, _ = _run_brightness("set", "30%")
    if ok:
        steps.append("Brightness reduced to 30%")
    else:
        errors.append("Could not reduce brightness")

    # Try to set CPU governor to powersave
    try:
        gov_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        if os.path.exists(gov_path):
            subprocess.run(
                ["sudo", "-n", "tee", gov_path],
                input="powersave",
                capture_output=True,
                text=True,
                timeout=5,
            )
            steps.append("CPU set to power saving mode")
    except Exception:
        pass  # non-critical

    if errors:
        return steps, False, ". ".join(errors)
    return steps, True, "Power saving mode enabled — brightness reduced, CPU throttled"


def _humanize_error(stderr: str) -> str:
    s = stderr.lower()
    if "not found" in s:
        return "Brightness control not available"
    if "permission" in s:
        return "Permission needed for brightness control"
    return stderr[:100] if stderr else "Brightness operation failed"
