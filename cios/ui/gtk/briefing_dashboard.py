"""DCS9 — Briefing Dashboard for secondary monitor (GTK4).

A dedicated dashboard surface showing:
- Greeting + focus suggestion
- Next meeting countdown
- Email summary
- Time blocks for the day
- Quick actions

Designed for always-on display on secondary monitor.
Auto-refreshes every 5 minutes.
"""

import logging
import threading

from gi.repository import GLib, Gtk

from cios.ui.theme import ACCENT, BG, BG_CARD, FG, FG_DIM, FG_SEC

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_MS = 300_000  # 5 minutes


class BriefingDashboard(Gtk.Box):
    """Dashboard widget showing daily briefing data from Intelligence API."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_vexpand(True)
        self.add_css_class("briefing-dashboard")

        # Header
        self._greeting = Gtk.Label(label="Bom dia")
        self._greeting.add_css_class("briefing-greeting")
        self._greeting.set_halign(Gtk.Align.START)
        self.append(self._greeting)

        self._focus = Gtk.Label(label="")
        self._focus.add_css_class("briefing-focus")
        self._focus.set_halign(Gtk.Align.START)
        self._focus.set_visible(False)
        self.append(self._focus)

        self._next_meeting = Gtk.Label(label="")
        self._next_meeting.add_css_class("briefing-next-meeting")
        self._next_meeting.set_halign(Gtk.Align.START)
        self._next_meeting.set_visible(False)
        self.append(self._next_meeting)

        # Content grid
        grid = Gtk.Grid()
        grid.set_row_spacing(12)
        grid.set_column_spacing(16)
        grid.set_column_homogeneous(True)
        grid.set_vexpand(True)
        self.append(grid)

        # Meetings card
        self._meetings_card = self._create_card("📅 Reuniões")
        grid.attach(self._meetings_card["frame"], 0, 0, 1, 1)

        # Emails card
        self._emails_card = self._create_card("📧 Emails")
        grid.attach(self._emails_card["frame"], 1, 0, 1, 1)

        # Time blocks card
        self._time_card = self._create_card("⏱️ Hoje")
        grid.attach(self._time_card["frame"], 0, 1, 1, 1)

        # Insights card
        self._insights_card = self._create_card("💡 Descobertas")
        grid.attach(self._insights_card["frame"], 1, 1, 1, 1)

        # Quick actions row
        self._actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._actions_box.set_halign(Gtk.Align.START)
        self._actions_box.set_margin_top(8)
        self.append(self._actions_box)

        # Start auto-refresh
        GLib.timeout_add(REFRESH_INTERVAL_MS, self._auto_refresh)
        GLib.idle_add(self.refresh)

    def refresh(self) -> bool:
        """Fetch briefing data from Intelligence API and update UI."""
        threading.Thread(target=self._fetch_briefing, daemon=True).start()
        return False

    def _auto_refresh(self) -> bool:
        """Periodic refresh callback."""
        self.refresh()
        return True

    def _fetch_briefing(self):
        """Fetch briefing from API (background thread)."""
        try:
            from cios.core.intelligence import intelligence

            if not intelligence.is_logged_in:
                GLib.idle_add(self._show_offline)
                return

            data = intelligence.briefing()
            if data:
                GLib.idle_add(self._apply_data, data)
            else:
                GLib.idle_add(self._show_offline)
        except Exception as e:
            logger.debug("Briefing fetch failed: %s", e)
            GLib.idle_add(self._show_offline)

    def _apply_data(self, data: dict):
        """Apply briefing data to UI widgets (main thread)."""
        # Header
        self._greeting.set_label(data.get("greeting", "Bom dia"))

        focus = data.get("focus_suggestion")
        if focus:
            self._focus.set_label(f"🎯 {focus}")
            self._focus.set_visible(True)
        else:
            self._focus.set_visible(False)

        next_meeting = data.get("next_meeting_in_minutes")
        if next_meeting is not None:
            self._next_meeting.set_label(f"Próxima reunião em {next_meeting} min")
            self._next_meeting.set_visible(True)
        else:
            self._next_meeting.set_visible(False)

        # Meetings
        meetings = data.get("meetings", [])
        self._fill_card(
            self._meetings_card,
            [f"{m.get('time', '?')[:5]} — {m.get('title', '?')}" for m in meetings]
            or ["Nenhuma reunião hoje"],
        )

        # Emails
        emails = data.get("emails", [])
        self._fill_card(
            self._emails_card,
            [
                f"{'● ' if e.get('priority') == 'high' else ''}{e.get('subject', '?')}"
                for e in emails[:5]
            ]
            or ["Inbox limpa"],
        )

        # Time blocks
        blocks = data.get("time_blocks", [])
        self._fill_card(
            self._time_card,
            [f"{b.get('start', '?')} – {b.get('end', '?')}  {b.get('label', '')}" for b in blocks]
            or ["Sem blocos definidos"],
        )

        # Insights
        insights = data.get("insights", [])
        self._fill_card(
            self._insights_card,
            [f"{i.get('topic', '?')}: {i.get('summary', '')}" for i in insights]
            or ["Nenhuma descoberta recente"],
        )

        # Quick actions
        self._clear_box(self._actions_box)
        for action in data.get("quick_actions", [])[:4]:
            btn = Gtk.Button(label=action.get("label", "?"))
            btn.add_css_class("briefing-action-btn")
            self._actions_box.append(btn)

    def _show_offline(self):
        """Show offline state."""
        self._greeting.set_label("Intelligence offline")
        self._focus.set_visible(False)
        self._next_meeting.set_visible(False)

    def _create_card(self, title: str) -> dict:
        """Create a dashboard card."""
        frame = Gtk.Frame()
        frame.add_css_class("briefing-card")
        frame.set_vexpand(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        frame.set_child(box)

        title_lbl = Gtk.Label(label=title)
        title_lbl.add_css_class("briefing-card-title")
        title_lbl.set_halign(Gtk.Align.START)
        box.append(title_lbl)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.append(content_box)

        return {"frame": frame, "box": box, "content": content_box}

    def _fill_card(self, card: dict, items: list[str]):
        """Fill a card with text items."""
        self._clear_box(card["content"])
        for item in items[:6]:
            lbl = Gtk.Label(label=item)
            lbl.add_css_class("briefing-card-item")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_ellipsize(3)  # END
            card["content"].append(lbl)

    def _clear_box(self, box: Gtk.Box):
        """Remove all children from a box."""
        child = box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            box.remove(child)
            child = next_child

    @staticmethod
    def get_css() -> str:
        """CSS for briefing dashboard."""
        return f"""
            .briefing-dashboard {{
                background-color: {BG};
            }}
            .briefing-greeting {{
                color: {FG};
                font-size: 24px;
                font-weight: 300;
            }}
            .briefing-focus {{
                color: {ACCENT};
                font-size: 14px;
                font-weight: 500;
            }}
            .briefing-next-meeting {{
                color: {FG_DIM};
                font-size: 12px;
            }}
            .briefing-card {{
                background-color: {BG_CARD};
                border: 1px solid rgba(0,229,255,0.1);
                border-radius: 10px;
                box-shadow: 0 0 8px rgba(0,229,255,0.03);
            }}
            .briefing-card-title {{
                color: {FG_SEC};
                font-size: 12px;
                font-weight: 600;
            }}
            .briefing-card-item {{
                color: {FG};
                font-size: 11px;
            }}
            .briefing-action-btn {{
                background-color: rgba(0,229,255,0.08);
                border: 1px solid rgba(0,229,255,0.15);
                border-radius: 16px;
                color: {ACCENT};
                font-size: 11px;
                padding: 4px 12px;
            }}
            .briefing-action-btn:hover {{
                background-color: rgba(0,229,255,0.15);
                border-color: rgba(0,229,255,0.3);
            }}
        """
