"""CIOS GTK4 Sidebar — System status + history + maestro login.

Layout (top to bottom):
- System metrics (icon + value, compact)
- Separator
- Message history (scrollable)
- Separator
- Maestro login link (always at bottom)
"""

import time as _time

from gi.repository import GLib, Gtk

from cios.ui.theme import (
    ACCENT,
    ACCENT_LT,
    BG_CARD,
    BG_HOVER,
    BG_PANEL,
    BORDER,
    FG,
    FG_DIM,
    FG_SEC,
    SUCCESS,
)


class Sidebar(Gtk.Box):
    """Right sidebar: metrics (icons) + history + maestro login."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_size_request(220, -1)
        self.set_hexpand(False)
        self.add_css_class("sidebar")
        self.set_margin_top(12)
        self.set_margin_end(12)
        self.set_margin_bottom(12)
        self._bridge = None

        # ── System metrics (compact, icon-based) ──
        metrics_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        metrics_box.set_margin_start(12)
        metrics_box.set_margin_end(12)
        metrics_box.set_margin_top(8)
        metrics_box.set_margin_bottom(8)
        self.append(metrics_box)

        self._cpu_metric = self._create_icon_metric("⚡", "0%")
        metrics_box.append(self._cpu_metric["box"])

        self._mem_metric = self._create_icon_metric("◈", "0%")
        metrics_box.append(self._mem_metric["box"])

        self._disk_metric = self._create_icon_metric("◉", "0%")
        metrics_box.append(self._disk_metric["box"])

        # Separator
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep1.add_css_class("sidebar-sep")
        self.append(sep1)

        # ── Message history (scrollable, fills available space) ──
        self._history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._history_box.set_margin_start(8)
        self._history_box.set_margin_end(8)
        self._history_box.set_margin_top(8)

        history_title = Gtk.Label(label="Histórico")
        history_title.add_css_class("sidebar-title")
        history_title.set_halign(Gtk.Align.START)
        history_title.set_margin_bottom(4)
        self._history_box.append(history_title)

        self._history_scroll = Gtk.ScrolledWindow()
        self._history_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._history_scroll.set_vexpand(True)
        self._history_box.append(self._history_scroll)

        self._history_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._history_scroll.set_child(self._history_list)

        self.append(self._history_box)

        # Separator
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep2.add_css_class("sidebar-sep")
        self.append(sep2)

        # ── Maestro login (always at bottom) ──
        login_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        login_box.set_margin_start(12)
        login_box.set_margin_end(12)
        login_box.set_margin_top(10)
        login_box.set_margin_bottom(10)
        login_box.add_css_class("maestro-login")

        login_icon = Gtk.Label(label="⬡")
        login_icon.add_css_class("maestro-icon")
        login_box.append(login_icon)

        login_label = Gtk.Label(label="Maestro")
        login_label.add_css_class("maestro-label")
        login_label.set_hexpand(True)
        login_label.set_halign(Gtk.Align.START)
        login_box.append(login_label)

        self._maestro_status = Gtk.Label(label="offline")
        self._maestro_status.add_css_class("maestro-status")
        login_box.append(self._maestro_status)

        # Make clickable
        click_ctrl = Gtk.GestureClick()
        click_ctrl.connect("released", self._on_maestro_click)
        login_box.add_controller(click_ctrl)

        self.append(login_box)

        # Start polling metrics
        GLib.timeout_add(5000, self._update_metrics)
        self._update_metrics()

    def set_bridge(self, bridge):
        """Set bridge for history access."""
        self._bridge = bridge
        self.refresh_history()

    def refresh_history(self):
        """Reload thread history."""
        # Clear existing
        child = self._history_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._history_list.remove(child)
            child = next_child

        if not self._bridge:
            empty = Gtk.Label(label="Nenhuma conversa")
            empty.add_css_class("history-empty")
            self._history_list.append(empty)
            return

        try:
            threads = self._bridge._thread_manager.get_recent_threads(10)
        except Exception:
            threads = []

        if not threads:
            empty = Gtk.Label(label="Nenhuma conversa")
            empty.add_css_class("history-empty")
            self._history_list.append(empty)
            return

        for thread in threads:
            row = self._build_history_row(thread)
            self._history_list.append(row)

    def _build_history_row(self, thread) -> Gtk.Box:
        """Build a compact history entry."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("history-row")

        # Status icon
        outcome = getattr(thread, "outcome", "") or ""
        icon = "✓" if outcome == "success" else "○"
        icon_lbl = Gtk.Label(label=icon)
        icon_lbl.add_css_class("history-icon")
        if outcome == "success":
            icon_lbl.add_css_class("history-icon-ok")
        row.append(icon_lbl)

        # Summary
        summary = getattr(thread, "summary", "") or "…"
        summary_lbl = Gtk.Label(label=summary)
        summary_lbl.set_halign(Gtk.Align.START)
        summary_lbl.set_hexpand(True)
        summary_lbl.set_ellipsize(3)
        summary_lbl.add_css_class("history-summary")
        row.append(summary_lbl)

        # Time
        created = getattr(thread, "created_at", None)
        if created:
            time_str = self._format_time(created)
            time_lbl = Gtk.Label(label=time_str)
            time_lbl.add_css_class("history-time")
            row.append(time_lbl)

        return row

    def _format_time(self, timestamp) -> str:
        """Format timestamp as relative time."""
        try:
            diff = _time.time() - timestamp
            if diff < 60:
                return "agora"
            elif diff < 3600:
                return f"{int(diff / 60)}m"
            elif diff < 86400:
                return f"{int(diff / 3600)}h"
            else:
                return f"{int(diff / 86400)}d"
        except Exception:
            return ""

    def _create_icon_metric(self, icon: str, value: str) -> dict:
        """Create a compact icon + value metric."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_halign(Gtk.Align.CENTER)
        box.set_hexpand(True)

        icon_lbl = Gtk.Label(label=icon)
        icon_lbl.add_css_class("metric-icon")
        box.append(icon_lbl)

        val_lbl = Gtk.Label(label=value)
        val_lbl.add_css_class("metric-value")
        box.append(val_lbl)

        return {"box": box, "icon": icon_lbl, "value": val_lbl}

    def _update_metrics(self):
        """Poll system metrics."""
        try:
            with open("/proc/loadavg") as f:
                load = float(f.read().split()[0])
                import os

                cpus = os.cpu_count() or 1
                cpu_pct = min(int(load / cpus * 100), 100)
                self._cpu_metric["value"].set_label(f"{cpu_pct}%")
        except Exception:
            pass

        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
                total = int(lines[0].split()[1])
                avail = int(lines[2].split()[1])
                mem_pct = int((1 - avail / total) * 100)
                self._mem_metric["value"].set_label(f"{mem_pct}%")
        except Exception:
            pass

        try:
            import shutil

            usage = shutil.disk_usage("/")
            disk_pct = int(usage.used / usage.total * 100)
            self._disk_metric["value"].set_label(f"{disk_pct}%")
        except Exception:
            pass

        return True

    def _on_maestro_click(self, gesture, n_press, x, y):
        """Handle maestro login click."""
        # TODO: open maestro connection dialog
        self._maestro_status.set_label("conectando…")

    @staticmethod
    def get_css() -> str:
        """Return CSS for sidebar styling."""
        return f"""
            .sidebar {{
                background-color: {BG_PANEL};
                border-left: 1px solid {BORDER};
                border-radius: 0;
            }}
            .sidebar-title {{
                color: {FG_DIM};
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            .sidebar-sep {{
                background-color: {BORDER};
                min-height: 1px;
                margin: 0 8px;
            }}
            .metric-icon {{
                color: {ACCENT_LT};
                font-size: 18px;
            }}
            .metric-value {{
                color: {FG_SEC};
                font-size: 11px;
                font-weight: bold;
            }}
            .history-empty {{
                color: {FG_DIM};
                font-size: 11px;
                font-style: italic;
                padding: 8px 0;
            }}
            .history-row {{
                padding: 4px 6px;
                border-radius: 4px;
            }}
            .history-row:hover {{
                background-color: {BG_HOVER};
            }}
            .history-icon {{
                color: {FG_DIM};
                font-size: 11px;
            }}
            .history-icon-ok {{
                color: {SUCCESS};
            }}
            .history-summary {{
                color: {FG_SEC};
                font-size: 11px;
            }}
            .history-time {{
                color: {FG_DIM};
                font-size: 10px;
            }}
            .maestro-login {{
                padding: 8px;
                border-radius: 6px;
                cursor: pointer;
            }}
            .maestro-login:hover {{
                background-color: {BG_CARD};
            }}
            .maestro-icon {{
                color: {ACCENT};
                font-size: 16px;
            }}
            .maestro-label {{
                color: {FG};
                font-size: 12px;
                font-weight: bold;
            }}
            .maestro-status {{
                color: {FG_DIM};
                font-size: 10px;
            }}
        """
