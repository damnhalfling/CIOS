"""CIOS GTK4 Hotkey Overlay — Quick command input (Ctrl+Space).

A floating input bar that appears on hotkey press.
In the GTK4 version, this is triggered via compositor IPC
(the compositor sends key_intercepted event).
"""

from gi.repository import Gtk

from cios.ui.theme import ACCENT_LT, BG_CARD, BG_INPUT, BORDER, FG


class HotkeyOverlay(Gtk.Box):
    """Floating command input overlay."""

    def __init__(self, on_submit=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.add_css_class("hotkey-overlay")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.START)
        self.set_margin_top(100)
        self.set_size_request(500, -1)
        self.set_visible(False)
        self._on_submit = on_submit

        # Input
        self._input = Gtk.Entry()
        self._input.set_placeholder_text("Comando rápido…")
        self._input.set_hexpand(True)
        self._input.add_css_class("hotkey-input")
        self._input.connect("activate", self._on_activate)
        self.append(self._input)

    def show_overlay(self):
        """Show the overlay and focus input."""
        self.set_visible(True)
        self._input.set_text("")
        self._input.grab_focus()

    def hide_overlay(self):
        """Hide the overlay."""
        self.set_visible(False)

    def _on_activate(self, entry):
        """Submit command and hide."""
        text = entry.get_text().strip()
        if text and self._on_submit:
            self._on_submit(text)
        self.hide_overlay()

    @staticmethod
    def get_css() -> str:
        """Return CSS for hotkey overlay."""
        return f"""
            .hotkey-overlay {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 12px;
                padding: 12px 16px;
                box-shadow: 0 4px 24px rgba(0,0,0,0.5);
            }}
            .hotkey-input {{
                background: {BG_INPUT};
                color: {FG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 16px;
                box-shadow: none;
            }}
            .hotkey-input:focus {{
                border-color: {ACCENT_LT};
            }}
        """
