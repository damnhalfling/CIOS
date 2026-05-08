"""Screen capture skill — screenshots and screen recording.

Provides:
- Screenshot (full screen, active window, or region)
- Screen recording (start/stop, with optional audio)
- Saves to ~/Pictures/Screenshots/ or ~/Videos/Recordings/

Dependencies:
- scrot or maim (screenshot)
- ffmpeg (screen recording)
- xdotool (active window detection)
"""

import logging
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  PATHS
# ═══════════════════════════════════════════════════════════════════════════


def _screenshots_dir() -> Path:
    """Get screenshots directory, creating if needed."""
    d = Path.home() / "Pictures" / "Screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _recordings_dir() -> Path:
    """Get recordings directory, creating if needed."""
    d = Path.home() / "Videos" / "Recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _timestamp() -> str:
    """Generate a timestamp string for filenames."""
    return time.strftime("%Y-%m-%d_%H-%M-%S")


# ═══════════════════════════════════════════════════════════════════════════
#  SCREENSHOT
# ═══════════════════════════════════════════════════════════════════════════


def take_screenshot(mode: str = "full", delay: int = 0) -> tuple[bool, str]:
    """Take a screenshot.

    Args:
        mode: "full" (entire screen), "window" (active window), "region" (select area)
        delay: Seconds to wait before capturing (0 = immediate)

    Returns:
        (success, message_or_path)
    """
    output = str(_screenshots_dir() / f"screenshot_{_timestamp()}.png")

    # Try maim first (modern, supports all modes)
    if shutil.which("maim"):
        return _screenshot_maim(output, mode, delay)

    # Fallback to scrot
    if shutil.which("scrot"):
        return _screenshot_scrot(output, mode, delay)

    # Fallback to import (ImageMagick)
    if shutil.which("import"):
        return _screenshot_import(output, mode)

    return False, "Nenhuma ferramenta de captura encontrada. Instale com: instalar maim"


def _screenshot_maim(output: str, mode: str, delay: int) -> tuple[bool, str]:
    """Take screenshot using maim."""
    cmd = ["maim"]

    if delay > 0:
        cmd.extend(["--delay", str(delay)])

    if mode == "window":
        # Get active window ID
        wid = _get_active_window_id()
        if wid:
            cmd.extend(["--window", wid])
        else:
            cmd.append("--window=$(xdotool getactivewindow)")
    elif mode == "region":
        cmd.append("--select")

    cmd.append(output)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and os.path.isfile(output):
            return True, output
        return False, f"Falha na captura: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "Tempo esgotado"
    except Exception as e:
        return False, f"Erro: {e}"


def _screenshot_scrot(output: str, mode: str, delay: int) -> tuple[bool, str]:
    """Take screenshot using scrot."""
    cmd = ["scrot"]

    if delay > 0:
        cmd.extend(["--delay", str(delay)])

    if mode == "window":
        cmd.append("--focused")
    elif mode == "region":
        cmd.append("--select")

    cmd.append(output)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and os.path.isfile(output):
            return True, output
        return False, f"Falha na captura: {result.stderr.strip()}"
    except Exception as e:
        return False, f"Erro: {e}"


def _screenshot_import(output: str, mode: str) -> tuple[bool, str]:
    """Take screenshot using ImageMagick import."""
    cmd = ["import"]

    if mode == "full":
        cmd.extend(["-window", "root"])
    elif mode == "window":
        wid = _get_active_window_id()
        if wid:
            cmd.extend(["-window", wid])
        else:
            cmd.extend(["-window", "root"])
    # region mode: import without -window lets user select

    cmd.append(output)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and os.path.isfile(output):
            return True, output
        return False, "Falha na captura"
    except Exception as e:
        return False, f"Erro: {e}"


# ═══════════════════════════════════════════════════════════════════════════
#  SCREEN RECORDING
# ═══════════════════════════════════════════════════════════════════════════

# Global state for active recording
_recording_process: subprocess.Popen | None = None
_recording_path: str | None = None


def start_recording(with_audio: bool = True) -> tuple[bool, str]:
    """Start screen recording.

    Args:
        with_audio: Include system audio (via PulseAudio/PipeWire).

    Returns:
        (success, message)
    """
    global _recording_process, _recording_path

    if _recording_process is not None:
        return False, "Já está gravando. Diga 'parar gravação' para finalizar."

    if not shutil.which("ffmpeg"):
        return False, "ffmpeg não encontrado. Instale com: instalar ffmpeg"

    # Get screen resolution
    resolution = _get_screen_resolution()
    if not resolution:
        resolution = "1920x1080"

    output = str(_recordings_dir() / f"recording_{_timestamp()}.mp4")
    _recording_path = output

    cmd = [
        "ffmpeg",
        "-video_size",
        resolution,
        "-framerate",
        "30",
        "-f",
        "x11grab",
        "-i",
        os.environ.get("DISPLAY", ":0"),
    ]

    if with_audio:
        # Try PulseAudio/PipeWire
        cmd.extend(["-f", "pulse", "-i", "default"])

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
        ]
    )

    if with_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    cmd.extend(["-y", output])

    try:
        _recording_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            start_new_session=True,
        )
        return True, "Gravando… Diga 'parar gravação' para finalizar."
    except Exception as e:
        _recording_process = None
        _recording_path = None
        return False, f"Erro ao iniciar gravação: {e}"


def stop_recording() -> tuple[bool, str]:
    """Stop the active screen recording.

    Returns:
        (success, path_or_message)
    """
    global _recording_process, _recording_path

    if _recording_process is None:
        return False, "Nenhuma gravação ativa."

    try:
        # Send 'q' to ffmpeg stdin (graceful stop)
        _recording_process.stdin.write(b"q")
        _recording_process.stdin.flush()
        _recording_process.wait(timeout=10)
    except Exception:
        # Force kill if graceful stop fails
        try:
            _recording_process.send_signal(signal.SIGINT)
            _recording_process.wait(timeout=5)
        except Exception:
            _recording_process.kill()

    path = _recording_path
    _recording_process = None
    _recording_path = None

    if path and os.path.isfile(path):
        size = os.path.getsize(path)
        size_str = _format_size(size)
        return True, f"Gravação salva: {os.path.basename(path)} ({size_str})"
    else:
        return False, "Gravação falhou — arquivo não gerado."


def is_recording() -> bool:
    """Check if a recording is currently active."""
    return _recording_process is not None


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _get_active_window_id() -> str | None:
    """Get the active window ID using xdotool."""
    if not shutil.which("xdotool"):
        return None
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _get_screen_resolution() -> str | None:
    """Get screen resolution (e.g., '1920x1080')."""
    if shutil.which("xrandr"):
        try:
            result = subprocess.run(
                ["xrandr", "--current"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                import re

                match = re.search(r"(\d+x\d+)\+0\+0", result.stdout)
                if match:
                    return match.group(1)
                # Fallback: find "current" in first line
                match = re.search(r"current (\d+) x (\d+)", result.stdout)
                if match:
                    return f"{match.group(1)}x{match.group(2)}"
        except Exception:
            pass
    return None


def _format_size(bytes_val: int) -> str:
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    else:
        return f"{bytes_val / (1024 * 1024):.1f} MB"


def check_dependencies() -> dict:
    """Check which capture tools are available."""
    return {
        "maim": shutil.which("maim") is not None,
        "scrot": shutil.which("scrot") is not None,
        "import": shutil.which("import") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "xdotool": shutil.which("xdotool") is not None,
    }
