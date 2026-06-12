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

        # DCS11: Condensed daily summary ("2 meetings, 3 emails, foco: CIOS")
        self._daily_summary = Gtk.Label(label="")
        self._daily_summary.add_css_class("topbar-summary")
        self._daily_summary.set_visible(False)
        self.append(self._daily_summary)

        # Media: now playing indicator (hidden by default)
        self._media_label = Gtk.Label(label="")
        self._media_label.add_css_class("topbar-media")
        self._media_label.set_visible(False)
        self.append(self._media_label)

        # Spacer after media
        spacer2 = Gtk.Box()
        spacer2.set_hexpand(True)
        self.append(spacer2)

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

        # Power actions available via intent: "desligar", "reiniciar", "bloquear", "deslogar"
        # No visual button — popover/dropdown breaks Wayland input

        # Start polling
        GLib.timeout_add(10000, self._update)
        self._update()

    def _lock_screen(self):
        """Show lock screen with clock (Apple-style)."""
        from cios.ui.gtk.lock_screen import show_lock_screen

        win = self.get_root()
        if win:
            show_lock_screen(win)

    def _do_logout(self):
        """Logout — send IPC logout to compositor."""
        import json
        import socket

        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        sock_path = os.path.join(runtime_dir, "cios-shell.sock")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(3)
                sock.connect(sock_path)
                msg = json.dumps({"v": 1, "id": "logout-1", "command": "logout"}) + "\n"
                sock.sendall(msg.encode())
        except OSError:
            pass

    def _do_reboot(self):
        """Reboot the system."""
        import subprocess

        subprocess.Popen(["systemctl", "reboot"])

    def _do_shutdown(self):
        """Shutdown the system."""
        import subprocess

        subprocess.Popen(["systemctl", "poweroff"])

    def _update(self):
        """Update time, date, and media state."""
        now = time.localtime()

        # Time
        self._time_label.set_label(time.strftime("%H:%M", now))

        # Day of week (abbreviated, pt)
        days_pt = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
        self._day_label.set_label(days_pt[now.tm_wday])

        # Date
        self._date_label.set_label(time.strftime("%d/%m", now))

        # Media state (read from state file)
        self._update_media()

        # DCS11: Daily summary (read from briefing cache)
        self._update_daily_summary()

        return True

    def _update_media(self):
        """Update now-playing indicator from media state file."""
        import json
        from pathlib import Path

        state_file = Path.home() / ".cios" / ".media_state"
        try:
            if state_file.exists():
                data = json.loads(state_file.read_text(encoding="utf-8"))
                title = data.get("title", "")
                playing = data.get("playing", False)
                paused = data.get("paused", False)

                if title and (playing or paused):
                    icon = "▶" if playing else "⏸"
                    truncated = title[:25] + "…" if len(title) > 25 else title
                    self._media_label.set_label(f"♫ {truncated} ({icon})")
                    self._media_label.set_visible(True)
                    return

        except (json.JSONDecodeError, OSError):
            pass

        self._media_label.set_visible(False)

    def _update_daily_summary(self):
        """DCS11: Update condensed daily summary from briefing cache.

        Shows something like: "2 meetings, 3 emails, foco: CIOS"
        Reads from the cached briefing file written by Intelligence module.
        """
        import json
        from pathlib import Path

        cache_file = Path.home() / ".cios" / ".briefing_cache"
        try:
            if not cache_file.exists():
                self._daily_summary.set_visible(False)
                return

            data = json.loads(cache_file.read_text(encoding="utf-8"))
            parts = []

            meetings = len(data.get("meetings", []))
            if meetings > 0:
                parts.append(f"{meetings} {'reunião' if meetings == 1 else 'reuniões'}")

            emails = len(data.get("emails", []))
            if emails > 0:
                parts.append(f"{emails} {'email' if emails == 1 else 'emails'}")

            focus = data.get("focus_suggestion", "")
            if focus:
                parts.append(f"foco: {focus[:20]}")

            if parts:
                self._daily_summary.set_label(" · ".join(parts))
                self._daily_summary.set_visible(True)
            else:
                self._daily_summary.set_visible(False)

        except (json.JSONDecodeError, OSError):
            self._daily_summary.set_visible(False)

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
            .topbar-media {{
                color: {ACCENT_LT};
                font-size: 10px;
                font-weight: 500;
                opacity: 0.9;
            }}
            .topbar-summary {{
                color: {FG_DIM};
                font-size: 10px;
                font-weight: 400;
                opacity: 0.8;
            }}
            .topbar-power {{
                color: {FG_DIM};
                font-size: 12px;
                min-width: 24px;
                min-height: 24px;
                padding: 0 4px;
                border-radius: 4px;
            }}
            .topbar-power:hover {{
                color: {FG};
                background-color: rgba(255,255,255,0.05);
            }}
            .power-option {{
                font-size: 12px;
                padding: 6px 12px;
                border-radius: 4px;
                min-width: 120px;
            }}
            .power-option:hover {{
                background-color: rgba(255,255,255,0.08);
            }}
        """
