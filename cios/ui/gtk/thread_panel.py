"""CIOS GTK4 Thread Panel — Conversation history.

Shows recent conversation threads below the prompt area.
"""

import time as _time

from gi.repository import Gtk

from cios.ui.theme import BG_CARD, BG_HOVER, FG_DIM, FG_SEC, SUCCESS


class ThreadPanel(Gtk.Box):
    """Scrollable conversation history panel."""

    def __init__(self, bridge=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("thread-panel")
        self.set_margin_start(48)
        self.set_margin_end(48)
        self.set_margin_bottom(8)
        self._bridge = bridge

        # Title
        title = Gtk.Label(label="Recentes")
        title.add_css_class("thread-title")
        title.set_halign(Gtk.Align.START)
        self.append(title)

        # Scrollable list
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_max_content_height(150)
        self._scroll.set_propagate_natural_height(True)
        self.append(self._scroll)

        self._list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._scroll.set_child(self._list_box)

    def set_bridge(self, bridge):
        """Set bridge after initialization."""
        self._bridge = bridge
        self.refresh()

    def refresh(self):
        """Reload threads from bridge."""
        # Clear existing
        child = self._list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._list_box.remove(child)
            child = next_child

        if not self._bridge:
            return

        try:
            threads = self._bridge._thread_manager.get_recent_threads(5)
        except Exception:
            threads = []

        if not threads:
            empty = Gtk.Label(label="Nenhuma conversa ainda")
            empty.add_css_class("thread-empty")
            self._list_box.append(empty)
            return

        for thread in threads:
            row = self._build_thread_row(thread)
            self._list_box.append(row)

    def _build_thread_row(self, thread) -> Gtk.Box:
        """Build a single thread entry."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("thread-row")

        # Status icon
        outcome = getattr(thread, "outcome", "") or ""
        icon = "✓" if outcome == "success" else "○"
        icon_label = Gtk.Label(label=icon)
        icon_label.add_css_class("thread-icon")
        row.append(icon_label)

        # Summary
        summary = getattr(thread, "summary", "") or "Nova conversa"
        summary_label = Gtk.Label(label=summary)
        summary_label.set_halign(Gtk.Align.START)
        summary_label.set_hexpand(True)
        summary_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        summary_label.add_css_class("thread-summary")
        row.append(summary_label)

        # Time
        created = getattr(thread, "created_at", None)
        time_str = self._format_time(created) if created else ""
        time_label = Gtk.Label(label=time_str)
        time_label.add_css_class("thread-time")
        row.append(time_label)

        return row

    def _format_time(self, timestamp) -> str:
        """Format timestamp as relative time."""
        try:
            diff = _time.time() - timestamp
            if diff < 60:
                return "agora"
            elif diff < 3600:
                return f"{int(diff / 60)}min"
            elif diff < 86400:
                return f"{int(diff / 3600)}h"
            else:
                return f"{int(diff / 86400)}d"
        except Exception:
            return ""

    @staticmethod
    def get_css() -> str:
        """Return CSS for thread panel."""
        return f"""
            .thread-panel {{
                margin-top: 8px;
            }}
            .thread-title {{
                color: {FG_DIM};
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
                text-transform: uppercase;
                margin-bottom: 4px;
            }}
            .thread-row {{
                background-color: {BG_CARD};
                border-radius: 6px;
                padding: 8px 12px;
            }}
            .thread-row:hover {{
                background-color: {BG_HOVER};
            }}
            .thread-icon {{
                color: {SUCCESS};
                font-size: 12px;
            }}
            .thread-summary {{
                color: {FG_SEC};
                font-size: 12px;
            }}
            .thread-time {{
                color: {FG_DIM};
                font-size: 10px;
            }}
            .thread-empty {{
                color: {FG_DIM};
                font-size: 12px;
                font-style: italic;
            }}
        """
