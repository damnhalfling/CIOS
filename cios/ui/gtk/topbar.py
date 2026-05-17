"""CIOS GTK4 Topbar — System status bar.

Displays: time, CPU, memory, network status, AI indicator.
Positioned at the top of the main window (32px height).
"""

import time

from gi.repository import GLib, Gtk

from cios.ui.theme import ACCENT_LT, BG_PANEL, BORDER, FG_DIM, FG_SEC


class Topbar(Gtk.Box):
    """System status bar widget."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.set_size_request(-1, 32)
        self.add_css_class("topbar")
        self.set_margin_start(16)
        self.set_margin_end(16)

        # Left: CIOS brand
        brand = Gtk.Label(label="CIOS")
        brand.add_css_class("topbar-brand")
        self.append(brand)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.append(spacer)

        # Right: status indicators
        self._cpu_label = Gtk.Label(label="CPU --")
        self._cpu_label.add_css_class("topbar-item")
        self.append(self._cpu_label)

        self._mem_label = Gtk.Label(label="MEM --")
        self._mem_label.add_css_class("topbar-item")
        self.append(self._mem_label)

        self._ai_label = Gtk.Label(label="🧠")
        self._ai_label.add_css_class("topbar-item")
        self.append(self._ai_label)

        self._time_label = Gtk.Label(label="--:--")
        self._time_label.add_css_class("topbar-time")
        self.append(self._time_label)

        # Start polling
        GLib.timeout_add(2000, self._update)
        self._update()

    def _update(self):
        """Update status indicators."""
        # Time
        self._time_label.set_label(time.strftime("%H:%M"))

        # CPU/Memory (lightweight)
        try:
            with open("/proc/loadavg") as f:
                load = f.read().split()[0]
                self._cpu_label.set_label(f"CPU {load}")
        except Exception:
            pass

        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
                total = int(lines[0].split()[1]) / 1024 / 1024
                avail = int(lines[2].split()[1]) / 1024 / 1024
                used_pct = int((1 - avail / total) * 100)
                self._mem_label.set_label(f"MEM {used_pct}%")
        except Exception:
            pass

        return True  # Keep polling

    @staticmethod
    def get_css() -> str:
        """Return CSS for topbar styling."""
        return f"""
            .topbar {{
                background-color: {BG_PANEL};
                border-bottom: 1px solid {BORDER};
                padding: 4px 0;
            }}
            .topbar-brand {{
                color: {ACCENT_LT};
                font-size: 12px;
                font-weight: bold;
                letter-spacing: 2px;
            }}
            .topbar-item {{
                color: {FG_DIM};
                font-size: 11px;
            }}
            .topbar-time {{
                color: {FG_SEC};
                font-size: 12px;
                font-weight: bold;
            }}
        """
