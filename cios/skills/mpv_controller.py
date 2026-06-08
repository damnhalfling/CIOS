"""mpv IPC Controller — Programmatic control of mpv via JSON IPC socket.

Provides reliable media control without xdotool hacks.
Uses mpv's --input-ipc-server for bidirectional communication.

Features:
- Launch mpv with IPC socket
- Play/pause/stop/next/prev via JSON commands
- Get current track info (title, duration, position)
- Playlist management (add, clear, list)
- Fullscreen toggle
- Volume control
- Adaptive sidebar geometry based on screen size

Usage:
    from cios.skills.mpv_controller import MpvController

    ctrl = MpvController.instance()
    ctrl.play("https://youtube.com/watch?v=...", mode="sidebar")
    ctrl.toggle_pause()
    ctrl.next_track()
    ctrl.quit()
"""

import json
import logging
import os
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SOCKET_PATH = Path.home() / ".cios" / "mpv.sock"
_STATE_FILE = Path.home() / ".cios" / ".media_state"
_CONNECT_TIMEOUT = 5.0
_COMMAND_TIMEOUT = 2.0


# ═══════════════════════════════════════════════════════════════════════════
#  DATA
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class MediaState:
    """Current media playback state."""

    playing: bool = False
    paused: bool = False
    title: str = ""
    url: str = ""
    mode: str = ""  # "sidebar", "fullscreen", "foreground"
    duration: float = 0.0
    position: float = 0.0
    volume: int = 100
    playlist_count: int = 0
    playlist_pos: int = 0
    pid: int = 0

    def to_dict(self) -> dict:
        return {
            "playing": self.playing,
            "paused": self.paused,
            "title": self.title,
            "url": self.url,
            "mode": self.mode,
            "duration": self.duration,
            "position": self.position,
            "volume": self.volume,
            "playlist_count": self.playlist_count,
            "playlist_pos": self.playlist_pos,
            "pid": self.pid,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MediaState":
        return cls(
            playing=d.get("playing", False),
            paused=d.get("paused", False),
            title=d.get("title", ""),
            url=d.get("url", ""),
            mode=d.get("mode", ""),
            duration=d.get("duration", 0.0),
            position=d.get("position", 0.0),
            volume=d.get("volume", 100),
            playlist_count=d.get("playlist_count", 0),
            playlist_pos=d.get("playlist_pos", 0),
            pid=d.get("pid", 0),
        )


# ═══════════════════════════════════════════════════════════════════════════
#  GEOMETRY HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _get_screen_size() -> tuple[int, int]:
    """Detect screen resolution. Returns (width, height)."""
    # Try wlr-randr first (Wayland)
    try:
        result = subprocess.run(
            ["wlr-randr"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                # Look for current mode line like "1920x1080 px, 60.000000 Hz (current)"
                if "current" in line and "x" in line:
                    parts = line.split()
                    for part in parts:
                        if "x" in part and part[0].isdigit():
                            w, h = part.split("x")
                            return int(w), int(h.split()[0] if " " in h else h)
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

    # Try xdpyinfo (X11/XWayland)
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
                    # "  dimensions:    1920x1080 pixels"
                    parts = line.split()
                    for part in parts:
                        if "x" in part and part[0].isdigit():
                            w, h = part.split("x")
                            return int(w), int(h)
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

    # Fallback: assume 1920x1080
    return 1920, 1080


def _sidebar_geometry() -> str:
    """Calculate adaptive sidebar geometry string for mpv.

    Places the window in the bottom-right, above the topbar (32px),
    sized proportionally to the screen.
    """
    w, h = _get_screen_size()
    # Sidebar: ~22% of screen width, 16:9 aspect ratio
    sidebar_w = max(360, int(w * 0.22))
    sidebar_h = int(sidebar_w * 9 / 16)
    # Position: 20px from right, 52px from bottom (20 margin + 32 topbar)
    x_offset = 20
    y_offset = 52
    return f"{sidebar_w}x{sidebar_h}+{x_offset}-{y_offset}"


# ═══════════════════════════════════════════════════════════════════════════
#  MPV CONTROLLER (Singleton)
# ═══════════════════════════════════════════════════════════════════════════


class MpvController:
    """Singleton controller for the CIOS media player (mpv via IPC)."""

    _instance: "MpvController | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._mode: str = ""
        self._url: str = ""
        self._request_id: int = 0
        self._state = MediaState()
        self._poll_thread: threading.Thread | None = None
        self._running = False

    @classmethod
    def instance(cls) -> "MpvController":
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────

    def play(
        self,
        target: str,
        mode: str = "foreground",
        append: bool = False,
    ) -> tuple[bool, str]:
        """Play a URL or file.

        Args:
            target: URL (YouTube, etc.) or local file path
            mode: "sidebar", "fullscreen", "foreground"
            append: If True and player is active, add to playlist instead of replacing

        Returns (success, message).
        """
        if not shutil.which("mpv"):
            return False, "mpv não instalado. Instale com: instalar mpv"

        is_url = target.startswith("http://") or target.startswith("https://")
        if is_url and not shutil.which("yt-dlp"):
            return False, "yt-dlp não instalado. Instale com: instalar yt-dlp"

        if not is_url and not os.path.exists(target):
            return False, "Arquivo não encontrado"

        # If player is already running, add to playlist
        if append and self.is_alive():
            return self._append_to_playlist(target)

        # If player is running with different mode, stop first
        if self.is_alive() and self._mode != mode:
            self.quit()
            time.sleep(0.3)

        # If player is running in same mode, replace playlist
        if self.is_alive():
            return self._replace_playlist(target)

        # Launch new mpv instance
        return self._launch(target, mode)

    def play_search(self, query: str, mode: str = "sidebar", count: int = 10) -> tuple[bool, str]:
        """Search YouTube via yt-dlp and play results as playlist.

        Args:
            query: Search terms (e.g., "techno work playlist")
            mode: Display mode
            count: Number of results to fetch

        Returns (success, message).
        """
        if not shutil.which("yt-dlp"):
            return False, "yt-dlp não instalado"
        if not shutil.which("mpv"):
            return False, "mpv não instalado"

        # Use yt-dlp to search and get URLs
        search_term = f"ytsearch{count}:{query}"

        # Launch mpv directly with ytdl search — mpv handles yt-dlp internally
        return self._launch(search_term, mode, shuffle=False)

    def toggle_pause(self) -> tuple[bool, str]:
        """Toggle pause/resume."""
        result = self._command("cycle", "pause")
        if result is not None:
            return True, "Pause/Resume"
        return False, "Nenhum media ativo"

    def next_track(self) -> tuple[bool, str]:
        """Skip to next track in playlist."""
        result = self._command("playlist-next")
        if result is not None:
            return True, "Próxima"
        return False, "Nenhum media ativo"

    def prev_track(self) -> tuple[bool, str]:
        """Go to previous track in playlist."""
        result = self._command("playlist-prev")
        if result is not None:
            return True, "Anterior"
        return False, "Nenhum media ativo"

    def toggle_fullscreen(self) -> tuple[bool, str]:
        """Toggle fullscreen mode."""
        result = self._command("cycle", "fullscreen")
        if result is not None:
            return True, "Tela cheia"
        return False, "Nenhum media ativo"

    def set_volume(self, volume: int) -> tuple[bool, str]:
        """Set volume (0-150)."""
        vol = max(0, min(150, volume))
        result = self._set_property("volume", vol)
        if result is not None:
            return True, f"Volume: {vol}%"
        return False, "Nenhum media ativo"

    def quit(self) -> tuple[bool, str]:
        """Stop playback and quit mpv."""
        if not self.is_alive():
            return True, "Nenhuma reprodução ativa"

        self._command("quit")
        self._running = False

        # Wait for process to terminate
        if self._process:
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

        self._state = MediaState()
        self._write_state()
        self._cleanup_socket()
        return True, "Reprodução parada"

    def get_state(self) -> MediaState:
        """Get current media state."""
        if self.is_alive():
            self._poll_state()
        return self._state

    def is_alive(self) -> bool:
        """Check if mpv process is still running."""
        if self._process is None:
            return False
        return self._process.poll() is None

    # ── Internal ──────────────────────────────────────────────────────────

    def _launch(self, target: str, mode: str, shuffle: bool = False) -> tuple[bool, str]:
        """Launch a new mpv instance with IPC socket."""
        self._cleanup_socket()
        _SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "mpv",
            "--force-window=yes",
            "--osd-level=1",
            f"--input-ipc-server={_SOCKET_PATH}",
            "--idle=once",  # Don't quit when playlist ends (wait for next command)
            "--ytdl-raw-options=retries=3",
        ]

        if mode == "sidebar":
            geometry = _sidebar_geometry()
            cmd.extend(
                [
                    f"--geometry={geometry}",
                    "--ontop=yes",
                    "--border=no",
                    "--title=CIOS Media (sidebar)",
                    "--no-terminal",
                ]
            )
        elif mode == "fullscreen":
            cmd.extend(["--fullscreen=yes"])
        else:
            cmd.extend(["--title=CIOS Media"])

        if shuffle:
            cmd.append("--shuffle")

        cmd.append(target)

        # Environment
        env = os.environ.copy()
        if "WAYLAND_DISPLAY" not in env:
            env["WAYLAND_DISPLAY"] = "wayland-1"
        if "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
            self._mode = mode
            self._url = target

            # Wait for socket to appear
            if not self._wait_for_socket():
                logger.warning("mpv socket did not appear in time")

            # Start state polling
            self._start_poll_thread()

            # Get initial title (may take a moment for yt-dlp to resolve)
            time.sleep(0.5)
            self._poll_state()

            title = self._state.title or target[:60]
            mode_label = {"sidebar": "em segundo plano", "fullscreen": "em tela cheia"}.get(
                mode, ""
            )
            msg = f"Tocando {mode_label}: {title}" if mode_label else f"Tocando: {title}"
            return True, msg.strip()

        except Exception as e:
            logger.warning("Failed to launch mpv: %s", e)
            return False, f"Erro ao abrir player: {e}"

    def _append_to_playlist(self, target: str) -> tuple[bool, str]:
        """Append a track to the current playlist."""
        result = self._command("loadfile", target, "append-play")
        if result is not None:
            return True, f"Adicionado à fila: {target[:60]}"
        return False, "Não consegui adicionar à fila"

    def _replace_playlist(self, target: str) -> tuple[bool, str]:
        """Replace current playlist with new target."""
        result = self._command("loadfile", target, "replace")
        if result is not None:
            self._url = target
            time.sleep(0.5)
            self._poll_state()
            return True, f"Tocando: {self._state.title or target[:60]}"
        return False, "Não consegui trocar a playlist"

    def _wait_for_socket(self, timeout: float = _CONNECT_TIMEOUT) -> bool:
        """Wait for mpv IPC socket to become available."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if _SOCKET_PATH.exists():
                # Try connecting
                try:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.settimeout(0.5)
                    sock.connect(str(_SOCKET_PATH))
                    sock.close()
                    return True
                except (ConnectionRefusedError, OSError):
                    pass
            time.sleep(0.1)
        return False

    def _command(self, *args: Any) -> Any:
        """Send a command to mpv via IPC and return the result."""
        if not self.is_alive():
            return None

        self._request_id += 1
        payload = {"command": list(args), "request_id": self._request_id}
        return self._send(payload)

    def _get_property(self, name: str) -> Any:
        """Get a property value from mpv."""
        if not self.is_alive():
            return None

        self._request_id += 1
        payload = {"command": ["get_property", name], "request_id": self._request_id}
        result = self._send(payload)
        if isinstance(result, dict):
            return result.get("data")
        return result

    def _set_property(self, name: str, value: Any) -> Any:
        """Set a property on mpv."""
        if not self.is_alive():
            return None

        self._request_id += 1
        payload = {"command": ["set_property", name, value], "request_id": self._request_id}
        return self._send(payload)

    def _send(self, payload: dict) -> Any:
        """Send JSON to mpv IPC socket and read response."""
        if not _SOCKET_PATH.exists():
            return None

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(_COMMAND_TIMEOUT)
            sock.connect(str(_SOCKET_PATH))

            msg = json.dumps(payload) + "\n"
            sock.sendall(msg.encode())

            # Read response (may contain event lines before our response)
            response_data = b""
            req_id = payload.get("request_id")
            deadline = time.monotonic() + _COMMAND_TIMEOUT

            while time.monotonic() < deadline:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                    # Parse lines — look for our response
                    for line in response_data.split(b"\n"):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            if obj.get("request_id") == req_id:
                                sock.close()
                                if obj.get("error") == "success":
                                    return obj
                                return None
                        except json.JSONDecodeError:
                            continue
                except TimeoutError:
                    break

            sock.close()
            return None

        except (ConnectionRefusedError, OSError, TimeoutError) as e:
            logger.debug("mpv IPC send failed: %s", e)
            return None

    def _poll_state(self) -> None:
        """Poll mpv for current state and update self._state."""
        if not self.is_alive():
            if self._state.playing:
                self._state = MediaState()
                self._write_state()
            return

        title = self._get_property("media-title") or ""
        paused = self._get_property("pause")
        duration = self._get_property("duration") or 0.0
        position = self._get_property("time-pos") or 0.0
        volume = self._get_property("volume") or 100
        playlist_count = self._get_property("playlist-count") or 0
        playlist_pos = self._get_property("playlist-pos") or 0
        path = self._get_property("path") or ""

        # Handle property responses
        if isinstance(title, dict):
            title = title.get("data", "")
        if isinstance(paused, dict):
            paused = paused.get("data", False)
        if isinstance(duration, dict):
            duration = duration.get("data", 0.0)
        if isinstance(position, dict):
            position = position.get("data", 0.0)
        if isinstance(volume, dict):
            volume = volume.get("data", 100)
        if isinstance(playlist_count, dict):
            playlist_count = playlist_count.get("data", 0)
        if isinstance(playlist_pos, dict):
            playlist_pos = playlist_pos.get("data", 0)
        if isinstance(path, dict):
            path = path.get("data", "")

        self._state = MediaState(
            playing=not bool(paused),
            paused=bool(paused),
            title=str(title)[:100] if title else "",
            url=str(path) if path else self._url,
            mode=self._mode,
            duration=float(duration) if duration else 0.0,
            position=float(position) if position else 0.0,
            volume=int(volume) if volume else 100,
            playlist_count=int(playlist_count) if playlist_count else 0,
            playlist_pos=int(playlist_pos) if playlist_pos else 0,
            pid=self._process.pid if self._process else 0,
        )

        self._write_state()

    def _write_state(self) -> None:
        """Write current state to file for topbar/other processes to read."""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _STATE_FILE.write_text(json.dumps(self._state.to_dict()), encoding="utf-8")
        except OSError as e:
            logger.debug("Failed to write media state: %s", e)

    def _start_poll_thread(self) -> None:
        """Start a background thread that polls mpv state every 2 seconds."""
        self._running = True
        if self._poll_thread and self._poll_thread.is_alive():
            return

        def _poll_loop():
            while self._running and self.is_alive():
                try:
                    self._poll_state()
                except Exception as e:
                    logger.debug("Poll error: %s", e)
                time.sleep(2)
            # Final state write on exit
            self._state = MediaState()
            self._write_state()

        self._poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="mpv-poll")
        self._poll_thread.start()

    def _cleanup_socket(self) -> None:
        """Remove stale socket file."""
        try:
            if _SOCKET_PATH.exists():
                _SOCKET_PATH.unlink()
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  MODULE-LEVEL CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


def get_media_state() -> MediaState | None:
    """Get current media state (reads from state file if controller not active).

    Safe to call from any thread/process (reads file, not socket).
    """
    ctrl = MpvController.instance()
    if ctrl.is_alive():
        return ctrl.get_state()

    # Fallback: read state file (topbar, other processes)
    try:
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            state = MediaState.from_dict(data)
            if state.playing or state.paused:
                return state
    except (json.JSONDecodeError, OSError):
        pass

    return None


def play(target: str, mode: str = "foreground", append: bool = False) -> tuple[bool, str]:
    """Play a URL or file via the singleton controller."""
    return MpvController.instance().play(target, mode=mode, append=append)


def play_search(query: str, mode: str = "sidebar", count: int = 10) -> tuple[bool, str]:
    """Search and play via yt-dlp."""
    return MpvController.instance().play_search(query, mode=mode, count=count)


def toggle_pause() -> tuple[bool, str]:
    """Toggle pause/resume."""
    return MpvController.instance().toggle_pause()


def next_track() -> tuple[bool, str]:
    """Next track."""
    return MpvController.instance().next_track()


def prev_track() -> tuple[bool, str]:
    """Previous track."""
    return MpvController.instance().prev_track()


def toggle_fullscreen() -> tuple[bool, str]:
    """Toggle fullscreen."""
    return MpvController.instance().toggle_fullscreen()


def set_volume(volume: int) -> tuple[bool, str]:
    """Set volume."""
    return MpvController.instance().set_volume(volume)


def stop() -> tuple[bool, str]:
    """Stop playback."""
    return MpvController.instance().quit()


def is_playing() -> bool:
    """Check if media is currently playing."""
    state = get_media_state()
    return state is not None and state.playing
