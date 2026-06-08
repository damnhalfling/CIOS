"""Top bar — system status bar with live OS presence.

Shows: clock, cpu, wifi, volume, battery, mic, processing indicator.

Key design decisions:
- Reads ALL data from MCP cache — zero subprocess calls.
- Subscribes to MCP change events for instant reaction (< 300ms).
- Processing indicator glows when the system is working on a command.
- Mic indicator shows when STT is active.
- Fallback polling every 2s if MCP events aren't firing.
"""

import logging
import os
import subprocess
import threading
import time

from cios.ui.theme import (
    ACCENT,
    ACCENT_LT,
    BAR_HEIGHT,
    CYAN,
    ERROR,
    FG,
    FG_DIM,
    FG_SEC,
    SUCCESS,
    T_RING,
    WARNING,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  DESIGN TOKENS (topbar-specific overrides)
# ═══════════════════════════════════════════════════════════════════════════

_BAR_HEIGHT = BAR_HEIGHT
_BG = "#0d0d14"
_FG = FG_SEC
_FG_BRIGHT = FG
_ACCENT = ACCENT
_ACCENT_GLOW = ACCENT_LT
_DIM = FG_DIM
_GREEN = SUCCESS
_YELLOW = WARNING
_RED = ERROR
_CYAN = CYAN

_CLOCK_MS = 1000
_STATUS_MS = 2000
_GLOW_MS = T_RING  # processing glow animation frame rate

# Shared activity state file — written by bridge, read by topbar
_ACTIVITY_FILE = os.path.expanduser("~/.cios/.topbar_activity")


class TopBar:
    """System status bar with live OS presence."""

    def __init__(self) -> None:
        self._root = None
        self._running = False
        self._labels: dict = {}
        self._mcp_available = False
        # Processing glow state
        self._processing = False
        self._glow_phase = 0.0
        self._glow_dir = 1

    def start(self) -> None:
        """Start the top bar (blocks — run in thread or as main)."""
        try:
            import tkinter as tk
        except ImportError:
            logger.error("Tkinter not available for top bar")
            return

        self._tk = tk
        self._root = tk.Tk()
        self._root.title("CIOS Bar")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)

        # Position topbar on primary monitor
        from cios.infra.monitors import get_primary_monitor

        _primary = get_primary_monitor()
        if _primary:
            screen_w = _primary.width
            bar_x = _primary.x
            bar_y = _primary.y
        else:
            screen_w = self._root.winfo_screenwidth()
            bar_x = 0
            bar_y = 0
        self._root.geometry(f"{screen_w}x{_BAR_HEIGHT}+{bar_x}+{bar_y}")
        self._root.configure(bg=_BG)

        self._set_strut(screen_w)

        frame = tk.Frame(self._root, bg=_BG)
        frame.pack(fill=tk.BOTH, expand=True, padx=8)

        # ── Left: brand + processing indicator ──
        left = tk.Frame(frame, bg=_BG)
        left.pack(side=tk.LEFT)

        # Logo image (small, ~18px for topbar)
        from cios.core.config import get_logo_path

        logo_path = get_logo_path()
        self._logo_img = None
        if logo_path:
            try:
                raw = tk.PhotoImage(file=str(logo_path))
                scale = max(1, raw.width() // 18)
                self._logo_img = raw.subsample(scale, scale)
                tk.Label(left, image=self._logo_img, bg=_BG).pack(side=tk.LEFT, padx=(0, 4))
            except Exception:
                self._logo_img = None

        self._labels["brand"] = tk.Label(
            left,
            text="CIOS" if self._logo_img else "✦ CIOS",
            font=("Inter", 9, "bold"),
            fg=_ACCENT,
            bg=_BG,
        )
        self._labels["brand"].pack(side=tk.LEFT, padx=(0, 8))

        # Activity text (shows what's happening: "Conectando…", "Instalando…")
        self._labels["activity"] = tk.Label(
            left,
            text="",
            font=("Inter", 8),
            fg=_DIM,
            bg=_BG,
        )
        self._labels["activity"].pack(side=tk.LEFT, padx=(0, 0))

        # ── Right side: status items ──
        right = tk.Frame(frame, bg=_BG)
        right.pack(side=tk.RIGHT)

        # Clock (rightmost)
        self._labels["clock"] = tk.Label(
            right,
            text="--:--",
            font=("Inter", 9, "bold"),
            fg=_FG_BRIGHT,
            bg=_BG,
        )
        self._labels["clock"].pack(side=tk.RIGHT, padx=(12, 0))

        # Battery
        self._labels["battery"] = tk.Label(
            right,
            text="🔋 --",
            font=("Inter", 9),
            fg=_FG,
            bg=_BG,
        )
        self._labels["battery"].pack(side=tk.RIGHT, padx=(12, 0))

        # Mic indicator
        self._labels["mic"] = tk.Label(
            right,
            text="",
            font=("Inter", 9),
            fg=_RED,
            bg=_BG,
        )
        self._labels["mic"].pack(side=tk.RIGHT, padx=(8, 0))

        # Volume
        self._labels["volume"] = tk.Label(
            right,
            text="🔊 --",
            font=("Inter", 9),
            fg=_FG,
            bg=_BG,
        )
        self._labels["volume"].pack(side=tk.RIGHT, padx=(12, 0))

        # Wi-Fi
        self._labels["wifi"] = tk.Label(
            right,
            text="📶 --",
            font=("Inter", 9),
            fg=_FG,
            bg=_BG,
        )
        self._labels["wifi"].pack(side=tk.RIGHT, padx=(12, 0))

        # CPU
        self._labels["cpu"] = tk.Label(
            right,
            text="⚡ --",
            font=("Inter", 9),
            fg=_DIM,
            bg=_BG,
        )
        self._labels["cpu"].pack(side=tk.RIGHT, padx=(12, 0))

        # AI status (Ollama)
        self._labels["ai"] = tk.Label(
            right,
            text="🧠 --",
            font=("Inter", 9),
            fg=_DIM,
            bg=_BG,
        )
        self._labels["ai"].pack(side=tk.RIGHT, padx=(12, 0))

        # Init MCP + subscribe to change events
        self._init_mcp()

        self._running = True
        self._update_clock()
        self._update_status()
        self._poll_activity()
        self._root.mainloop()

    # ═══════════════════════════════════════════════════════════════════════
    #  MCP INTEGRATION + EVENT SUBSCRIPTION
    # ═══════════════════════════════════════════════════════════════════════

    def _init_mcp(self) -> None:
        """Initialize MCP and subscribe to change events for instant updates."""
        try:
            from cios.core.mcp import context

            if not context._running:
                context.start()
            self._mcp_available = True

            # Subscribe to MCP changes — topbar updates instantly when
            # wifi disconnects, volume changes, etc. (< 300ms latency)
            context.on_change(self._on_mcp_change)
        except Exception as e:
            logger.warning("TopBar: MCP not available: %s", e)
            self._mcp_available = False

    def _on_mcp_change(self, snap) -> None:
        """Called by MCP when system state changes (from watcher threads).

        Schedules a UI update on the main thread via root.after().
        """
        if not self._running or not self._root:
            return
        try:
            self._root.after(0, lambda: self._apply_snapshot(snap))
        except Exception:
            pass  # root may be destroyed

    def _get_snapshot(self):
        if not self._mcp_available:
            return None
        try:
            from cios.core.mcp import context

            return context.snapshot()
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════════════════
    #  UPDATE LOOPS
    # ═══════════════════════════════════════════════════════════════════════

    def _update_clock(self) -> None:
        if not self._running or not self._root:
            return
        self._labels["clock"].config(text=time.strftime("%H:%M"))
        self._root.after(_CLOCK_MS, self._update_clock)

    def _update_status(self) -> None:
        """Fallback polling — runs every 2s in case MCP events miss something."""
        if not self._running or not self._root:
            return
        try:
            snap = self._get_snapshot()
            if snap:
                self._apply_snapshot(snap)
            else:
                self._update_fallback()
            self._update_ai_status()
        except Exception as e:
            logger.debug("TopBar update error: %s", e)
        self._root.after(_STATUS_MS, self._update_status)

    def _apply_snapshot(self, snap) -> None:
        """Apply a full MCP snapshot to all indicators."""
        self._update_cpu(snap.system.cpu_percent)
        self._update_wifi(snap.wifi)
        self._update_volume(snap.audio)
        self._update_battery(snap.battery)

    def _poll_activity(self) -> None:
        """Poll the shared activity file for processing state + mic state."""
        if not self._running or not self._root:
            return

        was_processing = self._processing
        activity_text = ""
        mic_active = False

        try:
            if os.path.exists(_ACTIVITY_FILE):
                with open(_ACTIVITY_FILE) as f:
                    data = f.read().strip()
                # Format: "processing|activity_text" or "idle" or "mic"
                if data.startswith("processing|"):
                    self._processing = True
                    activity_text = data.split("|", 1)[1] if "|" in data else ""
                elif data == "mic":
                    mic_active = True
                    self._processing = False
                else:
                    self._processing = False
            else:
                self._processing = False
        except Exception:
            self._processing = False

        # Update activity text
        self._labels["activity"].config(
            text=activity_text[:30] if activity_text else "",
            fg=_ACCENT_GLOW if self._processing else _DIM,
        )

        # Update mic indicator
        self._labels["mic"].config(
            text="🎙" if mic_active else "",
            fg=_RED if mic_active else _BG,
        )

        # Start/stop glow animation
        if self._processing and not was_processing:
            self._glow_phase = 0.0
            self._animate_glow()
        elif not self._processing and was_processing:
            self._labels["brand"].config(fg=_ACCENT)

        self._root.after(200, self._poll_activity)

    # ═══════════════════════════════════════════════════════════════════════
    #  PROCESSING GLOW ANIMATION
    # ═══════════════════════════════════════════════════════════════════════

    def _animate_glow(self) -> None:
        """Subtle pulsing glow on the brand icon while processing."""
        if not self._processing or not self._running or not self._root:
            self._labels["brand"].config(fg=_ACCENT)
            return

        # Oscillate between ACCENT and ACCENT_GLOW
        self._glow_phase += self._glow_dir * 0.08
        if self._glow_phase >= 1.0:
            self._glow_phase = 1.0
            self._glow_dir = -1
        elif self._glow_phase <= 0.0:
            self._glow_phase = 0.0
            self._glow_dir = 1

        color = _lerp_color(_ACCENT, _ACCENT_GLOW, self._glow_phase)
        self._labels["brand"].config(fg=color)
        self._root.after(_GLOW_MS, self._animate_glow)

    # ═══════════════════════════════════════════════════════════════════════
    #  INDIVIDUAL UPDATERS
    # ═══════════════════════════════════════════════════════════════════════

    def _update_cpu(self, cpu_pct: float) -> None:
        if cpu_pct < 50:
            color = _FG
        elif cpu_pct < 75:
            color = _YELLOW
        else:
            color = _RED
        self._labels["cpu"].config(text=f"⚡ {cpu_pct:.0f}%", fg=color)

    def _update_wifi(self, wifi) -> None:
        if wifi.connected:
            ssid = wifi.ssid[:14] if wifi.ssid else "?"
            sig = wifi.signal
            if sig > 70:
                icon, color = "📶", _GREEN
            elif sig > 40:
                icon, color = "📶", _FG
            elif sig > 0:
                icon, color = "📡", _YELLOW
            else:
                icon, color = "📶", _FG
            self._labels["wifi"].config(text=f"{icon} {ssid}", fg=color)
        else:
            self._labels["wifi"].config(text="📵 Desconectado", fg=_DIM)

    def _update_volume(self, audio) -> None:
        vol = audio.volume
        if audio.muted or vol == 0:
            self._labels["volume"].config(text="🔇 Mudo", fg=_DIM)
        elif vol < 30:
            self._labels["volume"].config(text=f"🔈 {vol}%", fg=_FG)
        elif vol < 70:
            self._labels["volume"].config(text=f"🔉 {vol}%", fg=_FG)
        else:
            self._labels["volume"].config(text=f"🔊 {vol}%", fg=_FG)

    def _update_battery(self, battery) -> None:
        if not battery.present:
            self._labels["battery"].config(text="⚡ AC", fg=_FG)
            return
        pct = battery.percent
        if battery.charging:
            icon, color = "⚡", _GREEN
        elif pct > 50:
            icon, color = "🔋", _FG
        elif pct > 20:
            icon, color = "🔋", _YELLOW
        else:
            icon, color = "🪫", _RED
        text = f"{icon} {pct}%"
        if battery.time_remaining and not battery.charging:
            text += f" ({battery.time_remaining})"
        self._labels["battery"].config(text=text, fg=color)

    # ═══════════════════════════════════════════════════════════════════════
    #  FALLBACK
    # ═══════════════════════════════════════════════════════════════════════

    def _update_fallback(self) -> None:
        import psutil

        self._update_cpu(psutil.cpu_percent(interval=0))
        bat = psutil.sensors_battery()
        if bat:
            from cios.core.mcp import BatteryState

            self._update_battery(
                BatteryState(
                    present=True, percent=int(bat.percent), charging=bat.power_plugged or False
                )
            )
        else:
            self._labels["battery"].config(text="⚡ AC", fg=_FG)
        self._labels["volume"].config(text="🔊 --", fg=_DIM)
        self._labels["wifi"].config(text="📶 --", fg=_DIM)

    def _update_ai_status(self) -> None:
        """Update the AI/Ollama + Intelligence status indicator."""
        try:
            from cios.core.intelligence import intelligence

            # If logged into Intelligence, show plan + usage
            if intelligence.is_logged_in:
                usage = intelligence.usage
                plan = usage.plan.capitalize()
                used = usage.used_today
                limit = usage.limit_today

                if used >= limit:
                    self._labels["ai"].config(text=f"🧠 {plan} ⚠️", fg=_YELLOW)
                else:
                    self._labels["ai"].config(text=f"🧠 {plan} {used}/{limit}", fg=_GREEN)
                return
            else:
                # Not logged in — red indicator
                self._labels["ai"].config(text="🧠 offline", fg=_RED)
                return
        except Exception:
            pass

        # Fallback: show Ollama status
        try:
            from cios.core.config import get
            from cios.core.ollama_manager import get_ollama_status

            provider = get("llm_provider")
            if provider != "ollama":
                self._labels["ai"].config(text=f"🧠 {provider}", fg=_FG)
                return

            status = get_ollama_status()
            if not status["installed"]:
                self._labels["ai"].config(text="🧠 IA ausente", fg=_RED)
            elif not status["running"]:
                self._labels["ai"].config(text="🧠 IA offline", fg=_YELLOW)
            elif not status["model_available"]:
                self._labels["ai"].config(text="🧠 sem modelo", fg=_YELLOW)
            else:
                self._labels["ai"].config(text="🧠 IA", fg=_GREEN)
        except Exception:
            self._labels["ai"].config(text="🧠 --", fg=_DIM)

    # ═══════════════════════════════════════════════════════════════════════
    #  EWMH STRUT
    # ═══════════════════════════════════════════════════════════════════════

    def _set_strut(self, screen_w: int) -> None:
        try:
            self._root.update_idletasks()
            wid = self._root.winfo_id()
            subprocess.Popen(
                [
                    "xprop",
                    "-id",
                    str(wid),
                    "-f",
                    "_NET_WM_STRUT_PARTIAL",
                    "32c",
                    "-set",
                    "_NET_WM_STRUT_PARTIAL",
                    f"0, 0, {_BAR_HEIGHT}, 0, 0, 0, 0, 0, 0, {screen_w}, 0, 0",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.Popen(
                [
                    "xprop",
                    "-id",
                    str(wid),
                    "-f",
                    "_NET_WM_WINDOW_TYPE",
                    "32a",
                    "-set",
                    "_NET_WM_WINDOW_TYPE",
                    "_NET_WM_WINDOW_TYPE_DOCK",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.debug("Could not set strut: %s", e)

    # ═══════════════════════════════════════════════════════════════════════
    #  LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════════

    def stop(self) -> None:
        self._running = False
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
#  ACTIVITY SIGNALING (called by bridge/GUI to update topbar)
# ═══════════════════════════════════════════════════════════════════════════


def signal_topbar_processing(activity: str = "") -> None:
    """Signal the topbar that the system is processing a command."""
    try:
        os.makedirs(os.path.dirname(_ACTIVITY_FILE), exist_ok=True)
        with open(_ACTIVITY_FILE, "w") as f:
            f.write(f"processing|{activity}")
    except Exception:
        pass


def signal_topbar_mic() -> None:
    """Signal the topbar that the mic is active (STT listening)."""
    try:
        os.makedirs(os.path.dirname(_ACTIVITY_FILE), exist_ok=True)
        with open(_ACTIVITY_FILE, "w") as f:
            f.write("mic")
    except Exception:
        pass


def signal_topbar_idle() -> None:
    """Signal the topbar that the system is idle."""
    try:
        if os.path.exists(_ACTIVITY_FILE):
            os.unlink(_ACTIVITY_FILE)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  COLOR UTILITY
# ═══════════════════════════════════════════════════════════════════════════


def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linear interpolation between two hex colors."""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINTS
# ═══════════════════════════════════════════════════════════════════════════


def run_topbar() -> None:
    bar = TopBar()
    bar.start()


def start_topbar_thread() -> threading.Thread:
    t = threading.Thread(target=run_topbar, daemon=True)
    t.start()
    return t
