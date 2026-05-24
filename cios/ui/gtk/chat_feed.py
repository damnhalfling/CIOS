"""Chat Feed — Conversational message display for CIOS.

Replaces the static result label with a scrollable feed of message bubbles.
User messages appear on the right, system responses on the left.
Supports streaming (token-by-token), progress updates, and metadata.
"""

import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from cios.ui.theme import ACCENT, BG_CARD, BORDER, FG, FG_DIM, FG_SEC  # noqa: E402


class MessageBubble(Gtk.Box):
    """A single message in the chat feed."""

    def __init__(self, role: str, content: str, timestamp: float | None = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._role = role
        self._content = content

        # Alignment: user on right, assistant on left
        if role == "user":
            self.set_halign(Gtk.Align.END)
            self.set_margin_start(80)
            css_class = "msg-user"
        else:
            self.set_halign(Gtk.Align.START)
            self.set_margin_end(80)
            css_class = "msg-assistant"

        # Bubble container
        bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        bubble.add_css_class("msg-bubble")
        bubble.add_css_class(css_class)
        self.append(bubble)

        # Content label
        self._label = Gtk.Label(label=content)
        self._label.set_wrap(True)
        self._label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._label.set_halign(Gtk.Align.START)
        self._label.set_selectable(True)
        self._label.set_max_width_chars(60)
        self._label.add_css_class("msg-text")
        bubble.append(self._label)

        # Timestamp (subtle)
        if timestamp:
            ts_str = time.strftime("%H:%M", time.localtime(timestamp))
            ts_label = Gtk.Label(label=ts_str)
            ts_label.add_css_class("msg-time")
            ts_label.set_halign(Gtk.Align.END if role == "user" else Gtk.Align.START)
            bubble.append(ts_label)

        self.set_margin_bottom(8)

    def set_content(self, text: str) -> None:
        """Update the message content (used for streaming)."""
        self._content = text
        self._label.set_label(text)

    def append_text(self, text: str) -> None:
        """Append text to the message (streaming token-by-token)."""
        self._content += text
        self._label.set_label(self._content)

    def add_metadata(self, metadata: dict) -> None:
        """Add cognitive indicator metadata below the message."""
        indicators = []
        if metadata.get("memory_used"):
            indicators.append("🧠")
        if metadata.get("honesty_modified"):
            indicators.append("⚖️")

        if indicators:
            meta_label = Gtk.Label(label=" ".join(indicators))
            meta_label.add_css_class("msg-meta")
            meta_label.set_halign(Gtk.Align.START)
            self.append(meta_label)


class ChatFeed(Gtk.Box):
    """Scrollable chat feed with message bubbles.

    Replaces the old greeting + result_label pattern with a conversational
    feed that persists messages and supports streaming.
    """

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_vexpand(True)

        # Scrolled window
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_vexpand(True)
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(self._scroll)

        # Message container
        self._messages_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._messages_box.set_margin_start(24)
        self._messages_box.set_margin_end(24)
        self._messages_box.set_margin_top(16)
        self._messages_box.set_margin_bottom(16)
        self._scroll.set_child(self._messages_box)

        # Greeting (shown when empty)
        self._greeting = Gtk.Label(label="O que você quer fazer?")
        self._greeting.add_css_class("greeting")
        self._greeting.set_halign(Gtk.Align.CENTER)
        self._greeting.set_valign(Gtk.Align.CENTER)
        self._greeting.set_vexpand(True)
        self._messages_box.append(self._greeting)

        # Track current streaming bubble
        self._streaming_bubble: MessageBubble | None = None
        self._message_count = 0

    def add_user_message(self, text: str) -> None:
        """Add a user message to the feed."""
        self._hide_greeting()
        bubble = MessageBubble("user", text, timestamp=time.time())
        self._messages_box.append(bubble)
        self._message_count += 1
        self._scroll_to_bottom()

    def add_assistant_message(self, text: str, metadata: dict | None = None) -> None:
        """Add a complete assistant message to the feed."""
        self._hide_greeting()
        bubble = MessageBubble("assistant", text, timestamp=time.time())
        if metadata:
            bubble.add_metadata(metadata)
        self._messages_box.append(bubble)
        self._message_count += 1
        self._scroll_to_bottom()

    def start_streaming(self) -> None:
        """Start a new streaming assistant message (empty bubble that fills up)."""
        self._hide_greeting()
        self._streaming_bubble = MessageBubble("assistant", "")
        self._streaming_bubble.add_css_class("streaming")
        self._messages_box.append(self._streaming_bubble)
        self._scroll_to_bottom()

    def append_stream_token(self, token: str) -> None:
        """Append a token to the current streaming message."""
        if self._streaming_bubble:
            self._streaming_bubble.append_text(token)
            self._scroll_to_bottom()

    def finish_streaming(self, metadata: dict | None = None) -> None:
        """Finalize the streaming message."""
        if self._streaming_bubble:
            self._streaming_bubble.remove_css_class("streaming")
            if metadata:
                self._streaming_bubble.add_metadata(metadata)
            self._streaming_bubble = None
            self._message_count += 1

    def add_progress_message(self, text: str) -> MessageBubble:
        """Add a progress/status message (can be updated)."""
        self._hide_greeting()
        bubble = MessageBubble("assistant", f"⟳ {text}")
        bubble.add_css_class("msg-progress")
        self._messages_box.append(bubble)
        self._scroll_to_bottom()
        return bubble

    def update_progress(self, bubble: MessageBubble, text: str) -> None:
        """Update an existing progress message."""
        bubble.set_content(f"⟳ {text}")

    def clear(self) -> None:
        """Clear all messages and show greeting."""
        child = self._messages_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            if child != self._greeting:
                self._messages_box.remove(child)
            child = next_child
        self._greeting.set_visible(True)
        self._message_count = 0
        self._streaming_bubble = None

    def _hide_greeting(self) -> None:
        """Hide the greeting when first message appears."""
        if self._greeting.get_visible():
            self._greeting.set_visible(False)

    def _scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the feed."""
        GLib.idle_add(self._do_scroll)

    def _do_scroll(self) -> bool:
        adj = self._scroll.get_vadjustment()
        adj.set_value(adj.get_upper() - adj.get_page_size())
        return False


# ═══════════════════════════════════════════════════════════════
#  CSS for chat feed
# ═══════════════════════════════════════════════════════════════

CHAT_FEED_CSS = f"""
.msg-bubble {{
    padding: 10px 14px;
    border-radius: 16px;
    min-width: 40px;
}}

.msg-user .msg-bubble,
.msg-user {{
}}

.msg-bubble.msg-user {{
    background: rgba(0,229,255,0.12);
    border: 1px solid rgba(0,229,255,0.3);
    border-radius: 16px 16px 4px 16px;
}}

.msg-bubble.msg-assistant {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 16px 16px 16px 4px;
}}

.msg-text {{
    color: {FG};
    font-size: 14px;
    line-height: 1.5;
}}

.msg-time {{
    color: {FG_DIM};
    font-size: 10px;
    margin-top: 2px;
}}

.msg-meta {{
    font-size: 12px;
    margin-top: 4px;
    opacity: 0.7;
}}

.msg-progress .msg-bubble {{
    background: transparent;
    border: 1px dashed {BORDER};
    opacity: 0.8;
}}

.streaming .msg-bubble {{
    border: 1px solid {ACCENT};
}}

.greeting {{
    color: {FG_SEC};
    font-size: 18px;
    font-weight: 300;
    padding: 64px 0;
}}
"""
