"""CIOS Secondary Window — Extended display with independent prompt.

Shown on secondary monitors when in extended mode.
Has: topbar + chat feed + prompt (no sidebar).
Shares the bridge with the main window but has its own conversation feed.
"""

import logging
import threading

from gi.repository import GLib, Gtk

logger = logging.getLogger(__name__)


class SecondaryWindow(Gtk.Window):
    """Independent window for secondary monitor — prompt + feed, no sidebar."""

    def __init__(self, app, bridge, monitor_name: str, width: int, height: int):
        super().__init__()
        self.set_application(app)
        self.set_title("CIOS — Extended")
        self.set_decorated(False)
        self.set_default_size(width, height)

        self._bridge = bridge
        self._monitor_name = monitor_name
        self._busy = False

        self._build_ui()

    def _build_ui(self):
        """Build the secondary window UI: topbar + feed + prompt."""
        from cios.ui.gtk.chat_feed import CHAT_FEED_CSS, ChatFeed
        from cios.ui.gtk.topbar import Topbar

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        # Topbar
        topbar = Topbar()
        root.append(topbar)

        # Chat feed
        self._chat_feed = ChatFeed()
        root.append(self._chat_feed)

        # Apply chat CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CHAT_FEED_CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Prompt area (bottom)
        prompt_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        prompt_container.set_margin_start(48)
        prompt_container.set_margin_end(48)
        prompt_container.set_margin_bottom(12)
        prompt_container.set_margin_top(8)

        prompt_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        prompt_box.add_css_class("prompt-area")

        self._input = Gtk.Entry()
        self._input.set_placeholder_text("Fale o que quer fazer…")
        self._input.set_hexpand(True)
        self._input.add_css_class("prompt-input")
        self._input.connect("activate", self._on_submit)
        prompt_box.append(self._input)

        send_btn = Gtk.Button(label="→")
        send_btn.add_css_class("send-btn")
        send_btn.connect("clicked", self._on_submit)
        prompt_box.append(send_btn)

        prompt_container.append(prompt_box)
        root.append(prompt_container)

    def _on_submit(self, *args):
        """Handle command submission on secondary window."""
        text = self._input.get_text().strip()
        if not text or self._busy or not self._bridge:
            return

        self._busy = True
        self._input.set_text("")
        self._input.set_sensitive(False)

        # Show user message
        self._chat_feed.add_user_message(text)

        # Execute in background
        threading.Thread(target=self._execute, args=(text,), daemon=True).start()

    def _execute(self, text: str):
        """Execute command via bridge (background thread)."""
        try:
            result = self._bridge.execute_command(text, confirmed=False)
            summary = result.get("result", result.get("summary", ""))
            status = result.get("status", "success")
            GLib.idle_add(self._show_result, summary, status)
        except Exception as e:
            logger.warning("Secondary window execution error: %s", e)
            GLib.idle_add(self._show_result, f"Erro: {e}", "error")

    def _show_result(self, result: str, status: str):
        """Show result in the chat feed."""
        self._chat_feed.add_assistant_message(result)
        self._busy = False
        self._input.set_sensitive(True)
        self._input.grab_focus()
