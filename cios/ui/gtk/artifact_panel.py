"""Artifact Panel — Split view for long-form content.

When the system generates long content (text, code, posts, articles),
it opens in a side panel instead of inline in the chat.
No WebKit/browser — text only. Lightweight and safe.
"""

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from cios.ui.theme import BG, BG_CARD, BORDER, FG, FG_DIM, FG_SEC  # noqa: E402

# Threshold: content longer than this goes to artifact panel
ARTIFACT_THRESHOLD = 600

# Patterns that indicate multi-section content (generated artifacts)
ARTIFACT_PATTERNS = ["=== ", "---\n", "## ", "### ", "```"]

# Patterns that indicate conversational content (NOT artifacts)
CONVERSATIONAL_PATTERNS = [
    "?",  # Questions
    "preciso de",
    "posso",
    "você quer",
    "me diga",
    "qual",
    "como",
    "antes de",
    "para que",
    "com essas",
    "o que você",
    "poderia",
]


def is_artifact(content: str) -> bool:
    """Determine if content should be displayed as an artifact.

    Artifacts are generated content (code, articles, plans, tables).
    Conversational responses (questions, clarifications) stay inline.
    """
    # Too short → never artifact
    if len(content) < ARTIFACT_THRESHOLD:
        return False

    # Check if it's conversational (questions, clarifications)
    content_lower = content.lower()
    question_marks = content_lower.count("?")
    if question_marks >= 2:
        return False

    # If most of the content is questions/clarification, not artifact
    for pattern in CONVERSATIONAL_PATTERNS:
        if pattern in content_lower[:200]:
            # Only exclude if there's no strong artifact signal
            has_artifact_signal = any(p in content for p in ARTIFACT_PATTERNS)
            if not has_artifact_signal:
                return False

    # Has structural patterns → artifact
    return any(p in content for p in ARTIFACT_PATTERNS)


class ArtifactPanel(Gtk.Box):
    """Side panel for displaying long-form generated content."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_size_request(400, -1)
        self.add_css_class("artifact-panel")

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.add_css_class("artifact-header")
        header.set_margin_start(16)
        header.set_margin_end(8)
        header.set_margin_top(8)
        header.set_margin_bottom(8)
        self.append(header)

        title = Gtk.Label(label="Artefato")
        title.add_css_class("artifact-title")
        title.set_hexpand(True)
        title.set_halign(Gtk.Align.START)
        header.append(title)
        self._title = title

        # Copy button
        copy_btn = Gtk.Button(label="Copiar")
        copy_btn.add_css_class("artifact-copy-btn")
        copy_btn.connect("clicked", self._on_copy)
        header.append(copy_btn)

        # Close button
        close_btn = Gtk.Button(label="✕")
        close_btn.add_css_class("artifact-close-btn")
        close_btn.connect("clicked", self._on_close)
        header.append(close_btn)

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        # Content area (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        self._content_view = Gtk.TextView()
        self._content_view.set_editable(False)
        self._content_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._content_view.set_margin_start(16)
        self._content_view.set_margin_end(16)
        self._content_view.set_margin_top(12)
        self._content_view.set_margin_bottom(12)
        self._content_view.add_css_class("artifact-content")
        scroll.set_child(self._content_view)

        self._scroll = scroll
        self._content = ""
        self.set_visible(False)

    def show_artifact(self, content: str, title: str = "Artefato") -> None:
        """Display text content in the artifact panel."""
        self._content = content
        self._title.set_label(title)
        buf = self._content_view.get_buffer()
        buf.set_text(content)
        self.set_visible(True)

    def close(self) -> None:
        """Close the artifact panel."""
        self.set_visible(False)
        self._content = ""

    def _on_copy(self, *args) -> None:
        """Copy artifact content to clipboard."""
        display = self.get_display()
        clipboard = display.get_clipboard()
        clipboard.set(self._content)

    def _on_close(self, *args) -> None:
        """Close button handler."""
        self.close()


ARTIFACT_PANEL_CSS = f"""
.artifact-panel {{
    background: {BG};
    border-left: 1px solid {BORDER};
}}

.artifact-header {{
    min-height: 40px;
}}

.artifact-title {{
    color: {FG};
    font-size: 13px;
    font-weight: 600;
}}

.artifact-copy-btn {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {FG_SEC};
    font-size: 11px;
    padding: 4px 10px;
    margin-end: 4px;
}}

.artifact-close-btn {{
    background: transparent;
    border: none;
    color: {FG_DIM};
    font-size: 14px;
    padding: 4px 8px;
}}

.artifact-content {{
    color: {FG};
    font-family: monospace;
    font-size: 13px;
    background: transparent;
}}
"""
