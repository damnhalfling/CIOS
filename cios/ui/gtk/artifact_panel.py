"""Artifact Panel — Split view for long-form content and web views.

When the system generates long content (text, code, posts, articles),
it opens in a side panel instead of inline in the chat. Also supports
loading URLs (like Maestro) as embedded web views.
"""

import gi

gi.require_version("Gtk", "4.0")

try:
    gi.require_version("WebKit", "6.0")
    from gi.repository import WebKit  # noqa: E402

    HAS_WEBKIT = True
except (ValueError, ImportError):
    try:
        gi.require_version("WebKit2", "5.0")
        from gi.repository import WebKit2 as WebKit  # noqa: E402

        HAS_WEBKIT = True
    except (ValueError, ImportError):
        HAS_WEBKIT = False

from gi.repository import Gtk  # noqa: E402

from cios.ui.theme import BG, BG_CARD, BORDER, FG, FG_DIM, FG_SEC  # noqa: E402

# Threshold: content longer than this goes to artifact panel
ARTIFACT_THRESHOLD = 400

# Patterns that indicate multi-section content
ARTIFACT_PATTERNS = ["=== ", "---\n", "## ", "### ", "```"]


def is_artifact(content: str) -> bool:
    """Determine if content should be displayed as an artifact."""
    if len(content) > ARTIFACT_THRESHOLD:
        return True
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

        # Web view (for URLs like Maestro)
        self._web_view = None
        if HAS_WEBKIT:
            self._web_view = WebKit.WebView()
            self._web_view.set_vexpand(True)

        self._scroll = scroll
        self._content = ""
        self._mode = "text"  # "text" or "web"
        self.set_visible(False)

    def show_artifact(self, content: str, title: str = "Artefato") -> None:
        """Display text content in the artifact panel."""
        self._content = content
        self._title.set_label(title)
        self._switch_to_text()
        buf = self._content_view.get_buffer()
        buf.set_text(content)
        self.set_visible(True)

    def show_url(self, url: str, title: str = "Maestro") -> None:
        """Load a URL in the artifact panel using WebKit."""
        self._title.set_label(title)
        self._content = url

        if self._web_view and HAS_WEBKIT:
            self._switch_to_web()
            self._web_view.load_uri(url)
            self.set_visible(True)
        else:
            # Fallback: open in browser if no WebKit
            import subprocess

            try:
                subprocess.Popen(
                    ["xdg-open", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def _switch_to_text(self) -> None:
        """Switch panel to text mode."""
        if self._mode == "web" and self._web_view:
            self.remove(self._web_view)
            self.append(self._scroll)
        self._mode = "text"

    def _switch_to_web(self) -> None:
        """Switch panel to web view mode."""
        if self._mode == "text":
            self.remove(self._scroll)
            self.append(self._web_view)
        self._mode = "web"

    def close(self) -> None:
        """Close the artifact panel."""
        self.set_visible(False)
        self._content = ""
        if self._mode == "web" and self._web_view:
            self._web_view.load_uri("about:blank")

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
