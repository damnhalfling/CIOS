"""Secondary screen — system context panel.

Displays live system state on secondary monitors.
No interaction — pure perception. Updates via MCP.

Panels:
- System vitals (CPU, memory, disk)
- Network status
- Audio status
- Battery
- Active apps
- Recent activity
- Suggestions
"""

import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional

from harmoni.core.mcp import context as mcp, ContextSnapshot
from harmoni.infra.monitors import Monitor

# Reuse design tokens from main GUI
BG         = "#0b0f14"
BG_PANEL   = "#0f1319"
BG_CARD    = "#111827"
BORDER     = "#1f2937"
FG         = "#e5e7eb"
FG_SEC     = "#9ca3af"
FG_DIM     = "#6b7280"
ACCENT     = "#7c3aed"
ACCENT_LT  = "#a78bfa"
SUCCESS    = "#22c55e"
WARNING    = "#eab308"
ERROR      = "#ef4444"
CYAN       = "#06b6d4"


def _size_human(b: int) -> str:
    if b >= 1024 ** 3:
        return f"{b / (1024 ** 3):.1f}GB"
    if b >= 1024 ** 2:
        return f"{b / (1024 ** 2):.0f}MB"
    return f"{b / 1024:.0f}KB"


class SecondaryPanel:
    """Cognitive context panel for a secondary monitor."""

    def __init__(self, root: tk.Tk, monitor: Monitor) -> None:
        self._root = root
        self._monitor = monitor
        self._labels: dict[str, tk.Label] = {}
        self._bars: dict[str, tk.Frame] = {}
        self._apps_frame: Optional[tk.Frame] = None
        self._win: Optional[tk.Toplevel] = None
        self._build()

    def _build(self) -> None:
        self._win = tk.Toplevel(self._root)
        self._win.title("Harmoni — Context")
        self._win.configure(bg=BG)
        self._win.overrideredirect(True)  # no window decorations

        # Position on secondary monitor
        geo = (f"{self._monitor.width}x{self._monitor.height}"
               f"+{self._monitor.x}+{self._monitor.y}")
        self._win.geometry(geo)

        # Fonts
        self._f = {
            "title":   tkfont.Font(family="Helvetica", size=18, weight="bold"),
            "section": tkfont.Font(family="Helvetica", size=12, weight="bold"),
            "label":   tkfont.Font(family="Helvetica", size=11),
            "value":   tkfont.Font(family="Helvetica", size=11, weight="bold"),
            "big":     tkfont.Font(family="Helvetica", size=28, weight="bold"),
            "small":   tkfont.Font(family="Helvetica", size=9),
            "app":     tkfont.Font(family="Helvetica", size=10),
        }

        # Two-column layout
        self._win.columnconfigure(0, weight=1)
        self._win.columnconfigure(1, weight=1)
        self._win.rowconfigure(0, weight=1)

        left = tk.Frame(self._win, bg=BG, padx=40, pady=40)
        left.grid(row=0, column=0, sticky="nsew")

        right = tk.Frame(self._win, bg=BG, padx=40, pady=40)
        right.grid(row=0, column=1, sticky="nsew")

        # ── LEFT COLUMN ──

        # Logo + Title
        from harmoni.core.config import get_logo_path
        logo_path = get_logo_path()
        self._logo_img = None
        if logo_path:
            try:
                raw = tk.PhotoImage(file=str(logo_path))
                scale = max(1, raw.width() // 48)
                self._logo_img = raw.subsample(scale, scale)
                tk.Label(left, image=self._logo_img, bg=BG).pack(anchor="w", pady=(0, 8))
            except Exception:
                self._logo_img = None

        if not self._logo_img:
            tk.Label(left, text="Harmoni", font=self._f["title"],
                     fg=ACCENT_LT, bg=BG).pack(anchor="w")

        tk.Label(left, text="System Context", font=self._f["small"],
                 fg=FG_DIM, bg=BG).pack(anchor="w", pady=(0, 32))

        # System vitals
        self._section(left, "📊 System")
        for key, label, color in [
            ("cpu", "CPU", ACCENT),
            ("mem", "Memory", CYAN),
            ("disk", "Disk", SUCCESS),
        ]:
            self._metric_bar(left, key, label, color)

        # Battery
        self._section(left, "🔋 Battery", top=24)
        self._labels["battery"] = tk.Label(
            left, text="--", font=self._f["big"],
            fg=FG, bg=BG)
        self._labels["battery"].pack(anchor="w")
        self._labels["battery_status"] = tk.Label(
            left, text="", font=self._f["small"],
            fg=FG_DIM, bg=BG)
        self._labels["battery_status"].pack(anchor="w")

        # ── RIGHT COLUMN ──

        # Network
        self._section(right, "🌐 Network")
        self._labels["wifi_ssid"] = tk.Label(
            right, text="--", font=self._f["value"],
            fg=FG, bg=BG)
        self._labels["wifi_ssid"].pack(anchor="w")
        self._labels["wifi_detail"] = tk.Label(
            right, text="", font=self._f["small"],
            fg=FG_DIM, bg=BG)
        self._labels["wifi_detail"].pack(anchor="w")

        # Audio
        self._section(right, "🔊 Audio", top=24)
        self._labels["volume"] = tk.Label(
            right, text="--", font=self._f["big"],
            fg=FG, bg=BG)
        self._labels["volume"].pack(anchor="w")
        self._labels["audio_status"] = tk.Label(
            right, text="", font=self._f["small"],
            fg=FG_DIM, bg=BG)
        self._labels["audio_status"].pack(anchor="w")

        # Active apps
        self._section(right, "📱 Active Apps", top=24)
        self._apps_frame = tk.Frame(right, bg=BG)
        self._apps_frame.pack(fill="x")

        # Start refresh loop
        self._refresh()

    def _section(self, parent: tk.Frame, title: str, top: int = 16) -> None:
        tk.Label(parent, text=title, font=self._f["section"],
                 fg=FG_SEC, bg=BG).pack(anchor="w", pady=(top, 8))

    def _metric_bar(self, parent: tk.Frame, key: str, label: str,
                    color: str) -> None:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=4)

        header = tk.Frame(frame, bg=BG)
        header.pack(fill="x")
        tk.Label(header, text=label, font=self._f["label"],
                 fg=FG_SEC, bg=BG).pack(side="left")
        val = tk.Label(header, text="--", font=self._f["value"],
                       fg=FG, bg=BG)
        val.pack(side="right")
        self._labels[key] = val

        bar_bg = tk.Frame(frame, bg=BORDER, height=6)
        bar_bg.pack(fill="x", pady=(4, 0))
        bar_fill = tk.Frame(bar_bg, bg=color, height=6)
        bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0.005)
        self._bars[key] = bar_fill

    def _refresh(self) -> None:
        """Update all panels from MCP state."""
        if not self._win or not self._win.winfo_exists():
            return

        try:
            state = mcp.snapshot()
            self._update_system(state)
            self._update_battery(state)
            self._update_network(state)
            self._update_audio(state)
            self._update_apps(state)
        except Exception:
            pass

        # Refresh every 2 seconds
        self._root.after(2000, self._refresh)

    def _update_system(self, state: ContextSnapshot) -> None:
        s = state.system

        self._labels["cpu"].configure(text=f"{s.cpu_percent:.0f}%")
        self._bars["cpu"].place(relwidth=max(0.005, s.cpu_percent / 100))

        self._labels["mem"].configure(
            text=f"{s.mem_used_gb:.1f}/{s.mem_total_gb:.0f} GB")
        self._bars["mem"].place(relwidth=max(0.005, s.mem_percent / 100))

        self._labels["disk"].configure(text=f"{s.disk_free_gb:.0f} GB free")
        self._bars["disk"].place(relwidth=max(0.005, s.disk_percent / 100))

        # Color coding
        for key, pct in [("cpu", s.cpu_percent), ("mem", s.mem_percent),
                         ("disk", s.disk_percent)]:
            color = ERROR if pct > 90 else WARNING if pct > 70 else SUCCESS
            self._labels[key].configure(fg=color if pct > 70 else FG)

    def _update_battery(self, state: ContextSnapshot) -> None:
        b = state.battery
        if not b.present:
            self._labels["battery"].configure(text="AC", fg=FG_DIM)
            self._labels["battery_status"].configure(text="No battery")
            return

        color = ERROR if b.percent < 15 else WARNING if b.percent < 30 else SUCCESS
        self._labels["battery"].configure(text=f"{b.percent}%", fg=color)

        status = "⚡ Charging" if b.charging else b.time_remaining or "On battery"
        self._labels["battery_status"].configure(text=status)

    def _update_network(self, state: ContextSnapshot) -> None:
        w = state.wifi
        if w.connected:
            self._labels["wifi_ssid"].configure(text=w.ssid, fg=SUCCESS)
            detail = f"Signal: {w.signal}%"
            if w.ip:
                detail += f" · {w.ip}"
            self._labels["wifi_detail"].configure(text=detail)
        else:
            self._labels["wifi_ssid"].configure(text="Disconnected", fg=ERROR)
            self._labels["wifi_detail"].configure(text="No network")

    def _update_audio(self, state: ContextSnapshot) -> None:
        a = state.audio
        if a.muted:
            self._labels["volume"].configure(text="🔇", fg=FG_DIM)
            self._labels["audio_status"].configure(text=f"Muted ({a.volume}%)")
        else:
            self._labels["volume"].configure(text=f"{a.volume}%", fg=FG)
            self._labels["audio_status"].configure(
                text=a.sink_name[:30] if a.sink_name else "Default output")

    def _update_apps(self, state: ContextSnapshot) -> None:
        if not self._apps_frame:
            return
        # Clear
        for w in self._apps_frame.winfo_children():
            w.destroy()
        # Show top 8 apps
        for app in state.running_apps[:8]:
            tk.Label(self._apps_frame, text=f"  • {app}",
                     font=self._f["app"], fg=FG_SEC, bg=BG,
                     anchor="w").pack(fill="x")

    def close(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.destroy()
