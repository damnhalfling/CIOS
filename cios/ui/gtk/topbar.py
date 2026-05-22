"""CIOS GTK4 Topbar — Contextual info bar.

Displays: time, day of week, date, user, notifications.
System metrics moved to sidebar.
"""

import os
import time

from gi.repository import GLib, Gtk

from cios.ui.theme import ACCENT_LT, BG_PANEL, BORDER, FG, FG_DIM, FG_SEC


class Topbar(Gtk.Box):
    """Minimal contextual status bar."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.set_size_request(-1, 28)
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

        # Right: contextual info
        self._day_label = Gtk.Label(label="")
        self._day_label.add_css_class("topbar-item")
        self.append(self._day_label)

        self._date_label = Gtk.Label(label="")
        self._date_label.add_css_class("topbar-item")
        self.append(self._date_label)

        self._time_label = Gtk.Label(label="--:--")
        self._time_label.add_css_class("topbar-time")
        self.append(self._time_label)

        # Separator
        sep = Gtk.Label(label="·")
        sep.add_css_class("topbar-sep")
        self.append(sep)

        # User
        username = os.environ.get("USER", "user")
        self._user_label = Gtk.Label(label=username)
        self._user_label.add_css_class("topbar-user")
        self.append(self._user_label)

        # Start polling
        GLib.timeout_add(10000, self._update)
        self._update()

    def _update(self):
        """Update time and date."""
        now = time.localtime()

        # Time
        self._time_label.set_label(time.strftime("%H:%M", now))

        # Day of week (abbreviated, pt)
        days_pt = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
        self._day_label.set_label(days_pt[now.tm_wday])

        # Date
        self._date_label.set_label(time.strftime("%d/%m", now))

        return True

    @staticmethod
    def get_css() -> str:
        """Return CSS for topbar styling."""
        return f"""
            .topbar {{
                background-color: {BG_PANEL};
                border-bottom: 1px solid {BORDER};
                padding: 2px 0;
            }}
            .topbar-brand {{
                color: {ACCENT_LT};
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 3px;
            }}
            .topbar-item {{
                color: {FG_DIM};
                font-size: 11px;
            }}
            .topbar-time {{
                color: {FG};
                font-size: 11px;
                font-weight: bold;
            }}
            .topbar-sep {{
                color: {FG_DIM};
                font-size: 11px;
                opacity: 0.5;
            }}
            .topbar-user {{
                color: {FG_SEC};
                font-size: 11px;
            }}
        """
