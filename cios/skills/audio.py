"""Audio skill — volume control via pactl or wpctl.

Supports both PulseAudio (pactl) and PipeWire (wpctl).
Auto-detects which is available. All execution is direct (no LLM).
"""

import logging
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  BACKEND DETECTION
# ═══════════════════════════════════════════════════════════════════════════

_backend: str | None = None  # "pactl", "wpctl", or None


def _detect_backend() -> str:
    """Detect available audio backend. Prefers pactl, falls back to wpctl."""
    global _backend
    if _backend is not None:
        return _backend

    # Try pactl first (works with both PulseAudio and PipeWire-pulse)
    if shutil.which("pactl"):
        try:
            r = subprocess.run(["pactl", "info"], capture_output=True, timeout=3)
            if r.returncode == 0:
                _backend = "pactl"
                logger.info("Audio backend: pactl")
                return _backend
        except Exception:
            pass

    # Try wpctl (PipeWire native)
    if shutil.which("wpctl"):
        try:
            r = subprocess.run(
                ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if r.returncode == 0:
                _backend = "wpctl"
                logger.info("Audio backend: wpctl")
                return _backend
        except Exception:
            pass

    _backend = ""
    logger.warning("No audio backend found (pactl or wpctl)")
    return _backend


def _run(cmd: list[str], timeout: int = 5) -> tuple[bool, str, str]:
    """Run a command. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return False, "", "Audio operation timed out"
    except Exception as e:
        return False, "", str(e)


# ═══════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════


def is_available() -> bool:
    """Check if any audio backend is available."""
    return bool(_detect_backend())


def get_volume() -> int:
    """Get current volume (0-100). Returns -1 if unavailable."""
    backend = _detect_backend()

    if backend == "pactl":
        ok, stdout, _ = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        if ok:
            match = re.search(r"(\d+)%", stdout)
            if match:
                return int(match.group(1))

    elif backend == "wpctl":
        ok, stdout, _ = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        if ok:
            # Output: "Volume: 0.64" or "Volume: 0.64 [MUTED]"
            match = re.search(r"Volume:\s+([\d.]+)", stdout)
            if match:
                return min(100, round(float(match.group(1)) * 100))

    return -1


def is_muted() -> bool:
    """Check if audio is muted."""
    backend = _detect_backend()

    if backend == "pactl":
        ok, stdout, _ = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
        if ok:
            return "yes" in stdout.lower()

    elif backend == "wpctl":
        ok, stdout, _ = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        if ok:
            return "[MUTED]" in stdout.upper()

    return False


def set_volume(level: int) -> tuple[list[str], bool, str]:
    """Set volume to a specific level (0-100)."""
    level = max(0, min(100, level))
    backend = _detect_backend()

    if backend == "pactl":
        ok, _, stderr = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
    elif backend == "wpctl":
        # wpctl uses 0.0-1.0 scale (not percentage)
        ok, _, stderr = _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{level / 100:.2f}"])
    else:
        return ["Adjusting volume"], False, _no_backend_msg()

    if ok:
        return [f"Setting volume to {level}%"], True, f"Volume: {level}%"
    return ["Adjusting volume"], False, _humanize_error(stderr)


def change_volume(delta: int) -> tuple[list[str], bool, str]:
    """Change volume by delta (positive = up, negative = down)."""
    backend = _detect_backend()

    if backend == "pactl":
        sign = "+" if delta > 0 else "-"
        amount = abs(delta)
        ok, _, stderr = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{amount}%"])

    elif backend == "wpctl":
        amount = abs(delta)
        if delta > 0:
            ok, _, stderr = _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{amount}%+"])
        else:
            ok, _, stderr = _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{amount}%-"])
    else:
        return ["Adjusting volume"], False, _no_backend_msg()

    if ok:
        new_vol = get_volume()
        direction = "up" if delta > 0 else "down"
        return [f"Volume {direction}"], True, f"Volume: {new_vol}%"
    return ["Adjusting volume"], False, _humanize_error(stderr)


def mute(state: bool | None = None) -> tuple[list[str], bool, str]:
    """Mute, unmute, or toggle mute.

    Args:
        state: True=mute, False=unmute, None=toggle
    """
    backend = _detect_backend()

    if backend == "pactl":
        if state is None:
            arg = "toggle"
        elif state:
            arg = "1"
        else:
            arg = "0"
        ok, _, stderr = _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", arg])

    elif backend == "wpctl":
        if state is None:
            ok, _, stderr = _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
        elif state:
            ok, _, stderr = _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"])
        else:
            ok, _, stderr = _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
    else:
        return ["Toggling mute"], False, _no_backend_msg()

    if ok:
        muted_now = is_muted()
        vol = get_volume()
        if muted_now:
            return ["Muting audio"], True, "Audio muted 🔇"
        return ["Unmuting audio"], True, f"Audio unmuted — Volume: {vol}%"
    return ["Toggling mute"], False, _humanize_error(stderr)


def list_sinks() -> list[dict]:
    """List available audio output devices."""
    backend = _detect_backend()

    if backend == "pactl":
        ok, stdout, _ = _run(["pactl", "list", "sinks", "short"])
        if not ok:
            return []
        sinks = []
        for line in stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                sinks.append(
                    {
                        "id": parts[0],
                        "name": parts[1],
                        "state": parts[4] if len(parts) > 4 else "unknown",
                    }
                )
        return sinks

    elif backend == "wpctl":
        # wpctl doesn't have a clean list command, use pw-cli
        ok, stdout, _ = _run(["wpctl", "status"])
        if not ok:
            return []
        sinks = []
        in_sinks = False
        for line in stdout.splitlines():
            if "Sinks:" in line or "Audio/Sink" in line:
                in_sinks = True
                continue
            if in_sinks:
                if not line.strip() or (line.strip() and not line.startswith(" ")):
                    break
                # Parse lines like " *  47. Built-in Audio Analog Stereo [vol: 0.64]"
                match = re.match(r"\s+[*│ ]*\s*(\d+)\.\s+(.+?)(?:\s+\[|$)", line)
                if match:
                    sinks.append(
                        {
                            "id": match.group(1),
                            "name": match.group(2).strip(),
                            "state": "active" if "*" in line else "idle",
                        }
                    )
        return sinks

    return []


def set_default_sink(sink_name: str) -> tuple[list[str], bool, str]:
    """Switch audio output to a different device."""
    backend = _detect_backend()

    if backend == "pactl":
        ok, _, stderr = _run(["pactl", "set-default-sink", sink_name])
    elif backend == "wpctl":
        ok, _, stderr = _run(["wpctl", "set-default", sink_name])
    else:
        return ["Switching audio output"], False, _no_backend_msg()

    if ok:
        return [f"Switching to {sink_name}"], True, f"Audio output: {sink_name}"
    return ["Switching audio output"], False, _humanize_error(stderr)


# ═══════════════════════════════════════════════════════════════════════════
#  ERROR MESSAGES
# ═══════════════════════════════════════════════════════════════════════════


def _no_backend_msg() -> str:
    return "Audio system not available. Install pulseaudio-utils or pipewire."


def _humanize_error(stderr: str) -> str:
    """Convert audio errors to human language."""
    s = stderr.lower()
    if "not found" in s:
        return "Audio system not available"
    if "connection refused" in s:
        return "Audio server not running"
    if "invalid" in s:
        return "Invalid audio operation"
    return stderr[:100] if stderr else "Audio operation failed"
