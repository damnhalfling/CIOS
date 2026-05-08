"""MCP — Model Context Protocol.

Maintains a live state of the system: wifi, volume, battery, cpu, disk,
running apps, known networks. Updated continuously via lightweight polling
and reactive watchers.

This is the "eyes" of the system. Every skill and the MCO consult this
before making decisions.

Features:
- Reactive watchers: nmcli monitor (wifi), pactl subscribe (audio)
- Adaptive polling: 1s active, 5s normal, 15s idle
- Force update: instant re-scan after skill execution
- Post-action validation: confirm state actually changed
- Parallel warmup: all scans run concurrently on boot
- Boot timing: measures and logs startup performance

Usage:
    from cios.core.mcp import context
    context.start()
    state = context.snapshot()
    context.notify_activity()   # after user action → fast polling
    context.force_update()      # instant re-scan
"""

import logging
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import psutil

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class WifiState:
    connected: bool = False
    ssid: str = ""
    signal: int = 0  # 0-100
    ip: str = ""
    device: str = ""


@dataclass
class AudioState:
    volume: int = 0  # 0-100
    muted: bool = False
    sink_name: str = ""  # active output device


@dataclass
class BatteryState:
    present: bool = False
    percent: int = 100
    charging: bool = False
    time_remaining: str = ""


@dataclass
class SystemState:
    cpu_percent: float = 0.0
    cpu_cores: int = 1
    mem_percent: float = 0.0
    mem_used_gb: float = 0.0
    mem_total_gb: float = 0.0
    disk_percent: float = 0.0
    disk_free_gb: float = 0.0


@dataclass
class BluetoothState:
    available: bool = False
    powered: bool = False
    connected_devices: list[str] = field(default_factory=list)


@dataclass
class ContextSnapshot:
    """Complete system state at a point in time."""

    wifi: WifiState = field(default_factory=WifiState)
    audio: AudioState = field(default_factory=AudioState)
    battery: BatteryState = field(default_factory=BatteryState)
    system: SystemState = field(default_factory=SystemState)
    bluetooth: BluetoothState = field(default_factory=BluetoothState)
    running_apps: list[str] = field(default_factory=list)
    known_networks: list[str] = field(default_factory=list)
    timestamp: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  SCANNERS (lightweight, no LLM)
# ═══════════════════════════════════════════════════════════════════════════


def _scan_wifi() -> WifiState:
    """Get current Wi-Fi state via nmcli.

    Returns safe default (disconnected) if nmcli is not installed.
    """
    state = WifiState()
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,DEVICE", "dev", "wifi"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split(":")
                if len(parts) >= 4 and parts[0].lower() in ("yes", "sim"):
                    state.connected = True
                    state.ssid = parts[1]
                    state.signal = int(parts[2]) if parts[2].isdigit() else 0
                    state.device = parts[3]
                    break

        # Get IP if connected
        if state.connected and state.device:
            ip_result = subprocess.run(
                ["nmcli", "-t", "-f", "IP4.ADDRESS", "dev", "show", state.device],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if ip_result.returncode == 0:
                for line in ip_result.stdout.strip().splitlines():
                    if ":" in line:
                        addr = line.split(":", 1)[1].strip()
                        state.ip = addr.split("/")[0] if "/" in addr else addr
                        break
    except FileNotFoundError:
        logger.debug("nmcli not found — Wi-Fi features unavailable")
    except Exception as e:
        logger.debug("Wi-Fi scan failed: %s", e)
    return state


def _scan_audio() -> AudioState:
    """Get current audio state via pactl or wpctl (PipeWire fallback)."""
    state = AudioState()

    # Try pactl first
    try:
        result = subprocess.run(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            match = re.search(r"(\d+)%", result.stdout)
            if match:
                state.volume = int(match.group(1))

            mute_result = subprocess.run(
                ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if mute_result.returncode == 0:
                state.muted = "yes" in mute_result.stdout.lower()

            sink_result = subprocess.run(
                ["pactl", "get-default-sink"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if sink_result.returncode == 0:
                state.sink_name = sink_result.stdout.strip()
            return state
    except FileNotFoundError:
        pass  # pactl not installed, try wpctl
    except Exception as e:
        logger.debug("pactl scan failed: %s", e)

    # Fallback: wpctl (PipeWire native)
    try:
        result = subprocess.run(
            ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Output: "Volume: 0.64" or "Volume: 0.64 [MUTED]"
            match = re.search(r"Volume:\s+([\d.]+)", result.stdout)
            if match:
                state.volume = min(100, round(float(match.group(1)) * 100))
            state.muted = "[MUTED]" in result.stdout.upper()
            state.sink_name = "pipewire"
    except FileNotFoundError:
        logger.debug("Neither pactl nor wpctl found")
    except Exception as e:
        logger.debug("wpctl scan failed: %s", e)

    return state


def _scan_battery() -> BatteryState:
    """Get battery state from /sys or psutil."""
    state = BatteryState()
    battery = psutil.sensors_battery()
    if battery:
        state.present = True
        state.percent = int(battery.percent)
        state.charging = battery.power_plugged or False
        if battery.secsleft > 0 and not battery.power_plugged:
            mins = battery.secsleft // 60
            state.time_remaining = f"{mins // 60}h{mins % 60:02d}m"
    return state


def _scan_system() -> SystemState:
    """Get CPU, memory, disk metrics.

    Uses interval=0 for non-blocking CPU read (returns since-last-call delta).
    First call may return 0.0 — that's fine, next poll will have real data.
    """
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return SystemState(
        cpu_percent=psutil.cpu_percent(interval=0),
        cpu_cores=psutil.cpu_count() or 1,
        mem_percent=round(mem.percent, 1),
        mem_used_gb=round(mem.used / (1024**3), 1),
        mem_total_gb=round(mem.total / (1024**3), 1),
        disk_percent=round(disk.percent, 1),
        disk_free_gb=round(disk.free / (1024**3), 1),
    )


def _scan_running_apps() -> list[str]:
    """Get list of running GUI apps (simplified)."""
    apps = set()
    try:
        for proc in psutil.process_iter(["name", "pid"]):
            name = proc.info["name"]
            if name and name not in (
                "python3",
                "bash",
                "sh",
                "openbox",
                "Xephyr",
                "systemd",
                "dbus-daemon",
                "pipewire",
                "pulseaudio",
                "xdg-desktop-portal",
                "gvfsd",
                "at-spi-bus-launcher",
            ):
                clean = name.lower().replace("-", " ").replace("_", " ")
                if len(clean) > 2:
                    apps.add(name)
    except Exception:
        pass
    return sorted(apps)[:20]


def _scan_known_networks() -> list[str]:
    """Get list of saved Wi-Fi networks.

    Returns empty list if nmcli is not installed.
    """
    networks = []
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE", "con", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split(":")
                if len(parts) >= 2 and "wireless" in parts[1].lower():
                    networks.append(parts[0])
    except FileNotFoundError:
        logger.debug("nmcli not found — known networks unavailable")
    except Exception:
        pass
    return networks


def _scan_bluetooth() -> BluetoothState:
    """Get Bluetooth state via bluetoothctl (lightweight, no scan)."""
    state = BluetoothState()
    try:
        result = subprocess.run(
            ["bluetoothctl", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return state
        state.available = True
        state.powered = "Powered: yes" in result.stdout

        if state.powered:
            # Get connected devices (fast — no scan)
            dev_result = subprocess.run(
                ["bluetoothctl", "devices", "Connected"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if dev_result.returncode == 0:
                for line in dev_result.stdout.strip().splitlines():
                    match = re.match(r"Device\s+[0-9A-Fa-f:]{17}\s+(.+)", line.strip())
                    if match:
                        state.connected_devices.append(match.group(1).strip())
    except FileNotFoundError:
        pass  # bluetoothctl not installed
    except Exception as e:
        logger.debug("Bluetooth scan failed: %s", e)
    return state


# ═══════════════════════════════════════════════════════════════════════════
#  CONTEXT MANAGER (singleton)
# ═══════════════════════════════════════════════════════════════════════════

# Polling intervals (adaptive)
_POLL_ACTIVE = 1.0  # after user action
_POLL_NORMAL = 5.0  # default
_POLL_IDLE = 15.0  # no activity for 60s
_IDLE_THRESHOLD = 60  # seconds before switching to idle polling


class SystemContext:
    """Live system context — the MCP.

    Features:
    - Adaptive polling (1s/5s/15s based on activity)
    - Reactive watchers (nmcli monitor, pactl subscribe)
    - Force update (instant re-scan on demand)
    - Post-action validation
    - Parallel warmup (all scans concurrent on boot)
    - Boot timing (measures startup performance)
    """

    def __init__(self) -> None:
        self._state = ContextSnapshot()
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._watcher_threads: list[threading.Thread] = []
        self._watcher_procs: list[subprocess.Popen] = []
        # Adaptive polling
        self._poll_interval = _POLL_NORMAL
        self._last_activity = time.time()
        # Force update event
        self._force_event = threading.Event()
        # Boot timing
        self._boot_times: dict[str, float] = {}
        # Thread pool for parallel execution
        self._pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="mcp")
        # Progress callback for splash
        self._on_progress: Callable[[str, int, int], None] | None = None

    def start(self, on_progress: Callable[[str, int, int], None] | None = None) -> None:
        """Start background polling and reactive watchers.

        Args:
            on_progress: Optional callback(stage_name, current, total) for boot progress.
        """
        if self._running:
            return
        self._running = True
        self._on_progress = on_progress

        # Parallel warmup — all scans run concurrently
        boot_start = time.monotonic()
        self._warmup_parallel()
        warmup_ms = (time.monotonic() - boot_start) * 1000
        self._boot_times["warmup_total"] = warmup_ms
        logger.info("MCP warmup completed in %.0fms (parallel)", warmup_ms)

        # Start adaptive polling
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

        # Start reactive watchers
        self._start_watchers()
        self._on_progress = None
        logger.info("MCP started — adaptive polling + reactive watchers")

    def _warmup_parallel(self) -> None:
        """Run all initial scans in parallel for fastest boot."""
        scanners = {
            "wifi": _scan_wifi,
            "audio": _scan_audio,
            "battery": _scan_battery,
            "system": _scan_system,
            "apps": _scan_running_apps,
            "networks": _scan_known_networks,
            "bluetooth": _scan_bluetooth,
        }
        results = {}
        total = len(scanners)
        done_count = 0

        if self._on_progress:
            self._on_progress("Detectando sistema…", 0, total)

        futures = {self._pool.submit(fn): name for name, fn in scanners.items()}

        for future in as_completed(futures):
            name = futures[future]
            t0 = time.monotonic()
            try:
                results[name] = future.result(timeout=5)
            except Exception as e:
                logger.warning("MCP warmup scan '%s' failed: %s", name, e)
                results[name] = None
            elapsed = (time.monotonic() - t0) * 1000
            self._boot_times[f"scan_{name}"] = elapsed
            done_count += 1
            if self._on_progress:
                self._on_progress(f"Detectando {name}…", done_count, total)

        # Assemble snapshot from parallel results
        with self._lock:
            self._state = ContextSnapshot(
                wifi=results.get("wifi") or WifiState(),
                audio=results.get("audio") or AudioState(),
                battery=results.get("battery") or BatteryState(),
                system=results.get("system") or SystemState(),
                bluetooth=results.get("bluetooth") or BluetoothState(),
                running_apps=results.get("apps") or [],
                known_networks=results.get("networks") or [],
                timestamp=time.time(),
            )

    @property
    def boot_times(self) -> dict[str, float]:
        """Boot timing data (ms). Available after start()."""
        return dict(self._boot_times)

    def stop(self) -> None:
        """Stop background polling, watchers, and thread pool."""
        self._running = False
        self._force_event.set()  # unblock poll loop
        # Kill watcher subprocesses
        for proc in self._watcher_procs:
            try:
                proc.terminate()
            except Exception:
                pass
        self._watcher_procs.clear()
        # Shutdown thread pool
        try:
            self._pool.shutdown(wait=False)
        except Exception:
            pass

    # ─── Adaptive Polling ─────────────────────────────────────────────

    def notify_activity(self) -> None:
        """Called after user action — switches to fast polling temporarily."""
        self._last_activity = time.time()
        self._poll_interval = _POLL_ACTIVE

    def _poll_loop(self) -> None:
        """Background polling loop with adaptive interval."""
        while self._running:
            # Wait for interval OR force event
            self._force_event.wait(timeout=self._poll_interval)
            self._force_event.clear()

            if not self._running:
                break

            try:
                self._update()
                self._notify_listeners()
            except Exception as e:
                logger.debug("MCP poll error: %s", e)

            # Adapt interval based on activity
            idle_time = time.time() - self._last_activity
            if idle_time < 10:
                self._poll_interval = _POLL_ACTIVE
            elif idle_time < _IDLE_THRESHOLD:
                self._poll_interval = _POLL_NORMAL
            else:
                self._poll_interval = _POLL_IDLE

    # ─── Force Update ─────────────────────────────────────────────────

    def force_update(self) -> None:
        """Force an immediate re-scan of all system state. Blocks until done."""
        self._update()
        # Also wake up the poll loop to reset its timer
        self._force_event.set()

    def force_update_wifi(self) -> None:
        """Force re-scan of wifi only (fast)."""
        wifi = _scan_wifi()
        with self._lock:
            self._state.wifi = wifi
            self._state.timestamp = time.time()
        self._notify_listeners()

    def force_update_audio(self) -> None:
        """Force re-scan of audio only (fast)."""
        audio = _scan_audio()
        with self._lock:
            self._state.audio = audio
            self._state.timestamp = time.time()
        self._notify_listeners()

    # ─── Reactive Watchers ────────────────────────────────────────────

    def _start_watchers(self) -> None:
        """Start reactive watchers for real-time state changes."""
        # Network watcher (nmcli monitor)
        if shutil.which("nmcli"):
            t = threading.Thread(target=self._watch_network, daemon=True)
            t.start()
            self._watcher_threads.append(t)

        # Audio watcher (pactl subscribe or polling for wpctl)
        if shutil.which("pactl"):
            t = threading.Thread(target=self._watch_audio, daemon=True)
            t.start()
            self._watcher_threads.append(t)
        elif shutil.which("wpctl"):
            # wpctl doesn't have a subscribe command, but the polling loop
            # handles it via adaptive polling (1s after activity)
            logger.info("Audio: using wpctl (no watcher, polling only)")

    def _watch_network(self) -> None:
        """Monitor NetworkManager for connectivity changes in real-time."""
        try:
            proc = subprocess.Popen(
                ["nmcli", "monitor"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._watcher_procs.append(proc)

            for line in proc.stdout:
                if not self._running:
                    break
                # nmcli monitor outputs lines like:
                # "wlp3s0: disconnected"
                # "Connectivity is now 'full'"
                # "wlp3s0: using connection 'MyWifi'"
                lower = line.lower()
                if any(
                    kw in lower
                    for kw in (
                        "disconnect",
                        "connect",
                        "connectivity",
                        "using connection",
                        "unavailable",
                        "activated",
                    )
                ):
                    logger.debug("Network change detected: %s", line.strip())
                    # Small delay to let NetworkManager settle
                    time.sleep(0.3)
                    self.force_update_wifi()

        except Exception as e:
            logger.debug("Network watcher stopped: %s", e)

    def _watch_audio(self) -> None:
        """Monitor PulseAudio for volume/mute changes in real-time."""
        try:
            proc = subprocess.Popen(
                ["pactl", "subscribe"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._watcher_procs.append(proc)

            for line in proc.stdout:
                if not self._running:
                    break
                # pactl subscribe outputs lines like:
                # "Event 'change' on sink #0"
                # "Event 'new' on sink-input #3"
                if "'change' on sink" in line:
                    logger.debug("Audio change detected: %s", line.strip())
                    self.force_update_audio()

        except Exception as e:
            logger.debug("Audio watcher stopped: %s", e)

    # ─── Full Update ──────────────────────────────────────────────────

    def _update(self) -> None:
        """Scan all system state (parallel for speed)."""
        scanners = {
            "wifi": _scan_wifi,
            "audio": _scan_audio,
            "battery": _scan_battery,
            "system": _scan_system,
            "apps": _scan_running_apps,
            "networks": _scan_known_networks,
            "bluetooth": _scan_bluetooth,
        }
        results = {}
        futures = {self._pool.submit(fn): name for name, fn in scanners.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result(timeout=8)
            except Exception as e:
                logger.debug("MCP scan '%s' failed: %s", name, e)
                results[name] = None

        with self._lock:
            self._state = ContextSnapshot(
                wifi=results.get("wifi") or self._state.wifi,
                audio=results.get("audio") or self._state.audio,
                battery=results.get("battery") or self._state.battery,
                system=results.get("system") or self._state.system,
                bluetooth=results.get("bluetooth") or self._state.bluetooth,
                running_apps=results.get("apps") or self._state.running_apps,
                known_networks=results.get("networks") or self._state.known_networks,
                timestamp=time.time(),
            )

    # ─── Read Access (non-blocking) ──────────────────────────────────

    def snapshot(self) -> ContextSnapshot:
        """Get current system state (non-blocking)."""
        with self._lock:
            return self._state

    @property
    def wifi(self) -> WifiState:
        with self._lock:
            return self._state.wifi

    @property
    def audio(self) -> AudioState:
        with self._lock:
            return self._state.audio

    @property
    def battery(self) -> BatteryState:
        with self._lock:
            return self._state.battery

    @property
    def system(self) -> SystemState:
        with self._lock:
            return self._state.system

    @property
    def running_apps(self) -> list[str]:
        with self._lock:
            return list(self._state.running_apps)

    @property
    def known_networks(self) -> list[str]:
        with self._lock:
            return list(self._state.known_networks)

    @property
    def bluetooth(self) -> BluetoothState:
        with self._lock:
            return self._state.bluetooth

    @property
    def poll_interval(self) -> float:
        """Current polling interval (for diagnostics)."""
        return self._poll_interval

    # ─── Change Listeners ─────────────────────────────────────────────

    def on_change(self, callback: Callable[["ContextSnapshot"], None]) -> None:
        """Register a callback that fires whenever system state changes.

        Used by the topbar to react instantly to MCP watcher events
        instead of polling on a timer.
        """
        if not hasattr(self, "_listeners"):
            self._listeners: list[Callable] = []
        self._listeners.append(callback)

    def _notify_listeners(self) -> None:
        """Notify all registered change listeners."""
        if not hasattr(self, "_listeners"):
            return
        snap = self.snapshot()
        for cb in self._listeners:
            try:
                cb(snap)
            except Exception as e:
                logger.debug("MCP listener error: %s", e)


# Global singleton
context = SystemContext()
