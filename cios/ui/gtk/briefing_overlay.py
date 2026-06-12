"""DCS10 — Briefing Overlay: shows daily context via intent trigger.

Triggered when user says "meu dia", "briefing", "minha agenda" via the
OS command detection (intent=briefing in pipeline_unified.py).

Shows a compact overlay with the same data as the full dashboard but
in a temporary popup format that auto-dismisses or closes on click/Escape.
"""

import logging
import threading

from gi.repository import GLib, Gtk

from cios.ui.theme import ACCENT, BG_CARD, FG, FG_DIM, FG_SEC

logger = logging.getLogger(__name__)


class BriefingOverlay(Gtk.Box):
    """Compact briefing popup overlay — shows daily summary on intent trigger."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add_css_class("briefing-overlay")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.START)
        self.set_margin_top(60)
        self.set_size_request(420, -1)
        self.set_visible(False)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._greeting_label = Gtk.Label(label="Carregando...")
        self._greeting_label.add_css_class("briefing-overlay-greeting")
        self._greeting_label.set_halign(Gtk.Align.START)
        self._greeting_label.set_hexpand(True)
        header.append(self._greeting_label)

        close_btn = Gtk.Button(label="✕")
        close_btn.add_css_class("briefing-overlay-close")
        close_btn.connect("clicked", lambda _: self.hide_overlay())
        header.append(close_btn)
        self.append(header)

        # Focus
        self._focus_label = Gtk.Label(label="")
        self._focus_label.add_css_class("briefing-overlay-focus")
        self._focus_label.set_halign(Gtk.Align.START)
        self._focus_label.set_visible(False)
        self.append(self._focus_label)

        # Content (meetings + emails compact)
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self._content_box)

        # Keyboard: Escape to close
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

    def show_overlay(self):
        """Show the briefing overlay and fetch data."""
        self.set_visible(True)
        threading.Thread(target=self._fetch_data, daemon=True).start()

    def hide_overlay(self):
        """Hide the overlay."""
        self.set_visible(False)

    def _on_key(self, controller, keyval, keycode, state):
        """Handle Escape to close."""
        if keyval == 65307:  # Escape
            self.hide_overlay()
            return True
        return False

    def _fetch_data(self):
        """Fetch briefing data from Intelligence API."""
        try:
            from cios.core.intelligence import intelligence

            if not intelligence.is_logged_in:
                GLib.idle_add(self._show_error, "Intelligence offline")
                return

            data = intelligence.briefing()
            if data:
                GLib.idle_add(self._apply_data, data)
            else:
                GLib.idle_add(self._show_error, "Sem dados disponíveis")
        except Exception as e:
            logger.debug("Briefing overlay fetch failed: %s", e)
            GLib.idle_add(self._show_error, "Erro ao carregar")

    def _apply_data(self, data: dict):
        """Apply briefing data to overlay UI."""
        self._greeting_label.set_label(data.get("greeting", "Bom dia"))

        focus = data.get("focus_suggestion")
        if focus:
            self._focus_label.set_label(f"🎯 {focus}")
            self._focus_label.set_visible(True)
        else:
            self._focus_label.set_visible(False)

        # Clear content
        child = self._content_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._content_box.remove(child)
            child = next_child

        # Next meeting
        next_meeting = data.get("next_meeting_in_minutes")
        if next_meeting is not None:
            lbl = Gtk.Label(label=f"⏰ Próxima reunião em {next_meeting} min")
            lbl.add_css_class("briefing-overlay-item")
            lbl.set_halign(Gtk.Align.START)
            self._content_box.append(lbl)

        # Meetings (compact list)
        meetings = data.get("meetings", [])
        if meetings:
            for m in meetings[:3]:
                time_str = m.get("time", "")[:5] if m.get("time") else "?"
                lbl = Gtk.Label(label=f"📅 {time_str} — {m.get('title', '?')}")
                lbl.add_css_class("briefing-overlay-item")
                lbl.set_halign(Gtk.Align.START)
                lbl.set_ellipsize(3)
                self._content_box.append(lbl)

        # Email count
        emails = data.get("emails", [])
        if emails:
            high_priority = sum(1 for e in emails if e.get("priority") == "high")
            text = f"📧 {len(emails)} email{'s' if len(emails) > 1 else ''}"
            if high_priority:
                text += f" ({high_priority} urgente{'s' if high_priority > 1 else ''})"
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("briefing-overlay-item")
            lbl.set_halign(Gtk.Align.START)
            self._content_box.append(lbl)

        # Auto-hide after 15s
        GLib.timeout_add(15000, self._auto_hide)

    def _show_error(self, message: str):
        """Show error state."""
        self._greeting_label.set_label(message)
        self._focus_label.set_visible(False)

    def _auto_hide(self) -> bool:
        """Auto-hide the overlay after timeout."""
        if self.get_visible():
            self.hide_overlay()
        return False

    @staticmethod
    def get_css() -> str:
        """CSS for briefing overlay."""
        return f"""
            .briefing-overlay {{
                background: {BG_CARD};
                border: 1px solid rgba(0,229,255,0.15);
                border-radius: 14px;
                padding: 16px 20px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.6), 0 0 16px rgba(0,229,255,0.05);
            }}
            .briefing-overlay-greeting {{
                color: {FG};
                font-size: 16px;
                font-weight: 300;
            }}
            .briefing-overlay-focus {{
                color: {ACCENT};
                font-size: 12px;
                font-weight: 500;
            }}
            .briefing-overlay-item {{
                color: {FG_SEC};
                font-size: 12px;
            }}
            .briefing-overlay-close {{
                color: {FG_DIM};
                font-size: 12px;
                min-width: 24px;
                min-height: 24px;
                padding: 0;
                border-radius: 12px;
                background: transparent;
                border: none;
            }}
            .briefing-overlay-close:hover {{
                color: {FG};
                background: rgba(255,255,255,0.05);
            }}
        """
