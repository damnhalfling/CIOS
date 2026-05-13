"""CIOS GTK4 Sidebar — System status panel (right side).

Shows: CPU, Memory, Disk metrics + quick action suggestions.
"""

from gi.repository import GLib, Gtk

from cios.ui.theme import ACCENT_LT, BG_CARD, BG_PANEL, BORDER, FG, FG_DIM, FG_SEC


class Sidebar(Gtk.Box):
    """Right sidebar with system metrics and suggestions."""

    def __init__(self, on_suggestion=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_size_request(240, -1)
        self.add_css_class("sidebar")
        self.set_margin_top(16)
        self.set_margin_end(16)
        self.set_margin_bottom(16)
        self._on_suggestion = on_suggestion

        # System status section
        status_title = Gtk.Label(label="Sistema")
        status_title.add_css_class("sidebar-title")
        status_title.set_halign(Gtk.Align.START)
        self.append(status_title)

        self._cpu_bar = self._create_metric("CPU", 0)
        self.append(self._cpu_bar["box"])

        self._mem_bar = self._create_metric("Memória", 0)
        self.append(self._mem_bar["box"])

        self._disk_bar = self._create_metric("Disco", 0)
        self.append(self._disk_bar["box"])

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.add_css_class("sidebar-sep")
        self.append(sep)

        # Suggestions section
        sug_title = Gtk.Label(label="Sugestões")
        sug_title.add_css_class("sidebar-title")
        sug_title.set_halign(Gtk.Align.START)
        self.append(sug_title)

        suggestions = [
            ("📁 Organizar", "organize my downloads"),
            ("📊 Diagnóstico", "my computer is slow"),
            ("🚀 Projeto", "start my backend"),
        ]

        for label, cmd in suggestions:
            btn = Gtk.Button(label=label)
            btn.add_css_class("suggestion-btn")
            btn.set_halign(Gtk.Align.START)
            btn.connect(
                "clicked", lambda _, c=cmd: self._on_suggestion(c) if self._on_suggestion else None
            )
            self.append(btn)

        # Start polling
        GLib.timeout_add(5000, self._update_metrics)
        self._update_metrics()

    def _create_metric(self, name: str, value: int) -> dict:
        """Create a metric row with label + progress bar."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        label = Gtk.Label(label=name)
        label.add_css_class("metric-label")
        label.set_halign(Gtk.Align.START)
        row.append(label)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        row.append(spacer)

        value_label = Gtk.Label(label=f"{value}%")
        value_label.add_css_class("metric-value")
        row.append(value_label)

        box.append(row)

        bar = Gtk.ProgressBar()
        bar.set_fraction(value / 100.0)
        bar.add_css_class("metric-bar")
        box.append(bar)

        return {"box": box, "bar": bar, "value_label": value_label}

    def _update_metrics(self):
        """Poll system metrics."""
        try:
            # CPU load
            with open("/proc/loadavg") as f:
                load = float(f.read().split()[0])
                import os

                cpus = os.cpu_count() or 1
                cpu_pct = min(int(load / cpus * 100), 100)
                self._cpu_bar["bar"].set_fraction(cpu_pct / 100.0)
                self._cpu_bar["value_label"].set_label(f"{cpu_pct}%")
        except Exception:
            pass

        try:
            # Memory
            with open("/proc/meminfo") as f:
                lines = f.readlines()
                total = int(lines[0].split()[1])
                avail = int(lines[2].split()[1])
                mem_pct = int((1 - avail / total) * 100)
                self._mem_bar["bar"].set_fraction(mem_pct / 100.0)
                self._mem_bar["value_label"].set_label(f"{mem_pct}%")
        except Exception:
            pass

        try:
            # Disk
            import shutil

            usage = shutil.disk_usage("/")
            disk_pct = int(usage.used / usage.total * 100)
            self._disk_bar["bar"].set_fraction(disk_pct / 100.0)
            self._disk_bar["value_label"].set_label(f"{disk_pct}%")
        except Exception:
            pass

        return True  # Keep polling

    @staticmethod
    def get_css() -> str:
        """Return CSS for sidebar styling."""
        return f"""
            .sidebar {{
                background-color: {BG_PANEL};
                border-left: 1px solid {BORDER};
                padding: 0 12px;
            }}
            .sidebar-title {{
                color: {FG_SEC};
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            .sidebar-sep {{
                background-color: {BORDER};
                min-height: 1px;
            }}
            .metric-label {{
                color: {FG_DIM};
                font-size: 12px;
            }}
            .metric-value {{
                color: {FG_SEC};
                font-size: 12px;
            }}
            .metric-bar {{
                min-height: 4px;
                border-radius: 2px;
            }}
            .metric-bar trough {{
                background-color: {BG_CARD};
                min-height: 4px;
            }}
            .metric-bar progress {{
                background-color: {ACCENT_LT};
                min-height: 4px;
                border-radius: 2px;
            }}
            .suggestion-btn {{
                background: {BG_CARD};
                color: {FG_SEC};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                box-shadow: none;
                text-shadow: none;
            }}
            .suggestion-btn:hover {{
                background: {BORDER};
                color: {FG};
            }}
        """
