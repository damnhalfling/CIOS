"""Artifact Panel — Universal content viewer.

Displays: text artifacts, web pages (reader mode), PDFs.
Opens as side panel (left of sidebar) or fullscreen on expand.
No WebKit — fetches and extracts text content server-side.
"""

import threading

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk  # noqa: E402

from cios.ui.theme import ACCENT, ACCENT_LT, BG, BG_CARD, BORDER, FG, FG_DIM  # noqa: E402

# Threshold: content longer than this goes to artifact panel
ARTIFACT_THRESHOLD = 600

# Patterns that indicate multi-section content (generated artifacts)
ARTIFACT_PATTERNS = ["=== ", "---\n", "## ", "### ", "```"]

# Patterns that indicate conversational content (NOT artifacts)
CONVERSATIONAL_PATTERNS = [
    "?",
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
    """Determine if content should be displayed as an artifact."""
    if len(content) < ARTIFACT_THRESHOLD:
        return False

    content_lower = content.lower()
    question_marks = content_lower.count("?")
    if question_marks >= 2:
        return False

    for pattern in CONVERSATIONAL_PATTERNS:
        if pattern in content_lower[:200]:
            has_artifact_signal = any(p in content for p in ARTIFACT_PATTERNS)
            if not has_artifact_signal:
                return False

    return any(p in content for p in ARTIFACT_PATTERNS)


class ArtifactPanel(Gtk.Box):
    """Universal content viewer — text, URLs (reader mode), PDFs."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_size_request(400, -1)
        self.add_css_class("artifact-panel")
        self._expanded = False
        self._original_size = 400

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.add_css_class("artifact-header")
        header.set_margin_start(12)
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

        # Source indicator (URL/PDF/text)
        self._source_label = Gtk.Label(label="")
        self._source_label.add_css_class("artifact-source")
        header.append(self._source_label)

        # Copy button
        copy_btn = Gtk.Button(label="⊡")
        copy_btn.set_tooltip_text("Copiar")
        copy_btn.add_css_class("artifact-btn")
        copy_btn.connect("clicked", self._on_copy)
        header.append(copy_btn)

        # Expand/collapse button
        self._expand_btn = Gtk.Button(label="⛶")
        self._expand_btn.set_tooltip_text("Expandir")
        self._expand_btn.add_css_class("artifact-btn")
        self._expand_btn.connect("clicked", self._on_toggle_expand)
        header.append(self._expand_btn)

        # Close button
        close_btn = Gtk.Button(label="✕")
        close_btn.add_css_class("artifact-btn")
        close_btn.connect("clicked", self._on_close)
        header.append(close_btn)

        # Separator
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(sep)

        # Loading indicator
        self._loading_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._loading_box.set_margin_start(16)
        self._loading_box.set_margin_top(12)
        self._loading_box.set_visible(False)
        loading_dot = Gtk.Label(label="●")
        loading_dot.add_css_class("artifact-loading-dot")
        self._loading_box.append(loading_dot)
        loading_text = Gtk.Label(label="Carregando…")
        loading_text.add_css_class("artifact-loading-text")
        self._loading_box.append(loading_text)
        self.append(self._loading_box)

        # Content area (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
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
        """Display text content."""
        self._content = content
        self._title.set_label(title)
        self._source_label.set_label("")
        self._loading_box.set_visible(False)
        buf = self._content_view.get_buffer()
        buf.set_text(content)
        self.set_visible(True)

    def show_url(self, url: str, title: str = "") -> None:
        """Fetch URL content in reader mode and display as text."""
        display_title = title or self._url_to_title(url)
        self._title.set_label(display_title)
        self._source_label.set_label("🌐")
        self._content = ""
        self._loading_box.set_visible(True)
        buf = self._content_view.get_buffer()
        buf.set_text("")
        self.set_visible(True)

        # Fetch in background
        threading.Thread(target=self._fetch_url, args=(url,), daemon=True).start()

    def show_pdf(self, path: str, title: str = "") -> None:
        """Extract PDF text and display."""
        display_title = title or path.split("/")[-1]
        self._title.set_label(display_title)
        self._source_label.set_label("📄")
        self._content = ""
        self._loading_box.set_visible(True)
        buf = self._content_view.get_buffer()
        buf.set_text("")
        self.set_visible(True)

        # Extract in background
        threading.Thread(target=self._extract_pdf, args=(path,), daemon=True).start()

    def close(self) -> None:
        """Close the artifact panel."""
        self.set_visible(False)
        self._content = ""
        if self._expanded:
            self._on_toggle_expand()

    def _fetch_url(self, url: str) -> None:
        """Fetch URL and extract readable text (reader mode)."""
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(url, timeout=15, headers={"User-Agent": "CIOS/2.0 (reader mode)"})
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove scripts, styles, nav, footer
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            # Try to find main content
            main = soup.find("main") or soup.find("article") or soup.find("body")
            if not main:
                main = soup

            # Extract text with some structure
            lines = []
            for elem in main.find_all(
                ["h1", "h2", "h3", "h4", "p", "li", "pre", "code", "blockquote"]
            ):
                tag = elem.name
                text = elem.get_text(strip=True)
                if not text:
                    continue

                if tag in ("h1", "h2", "h3", "h4"):
                    prefix = "#" * int(tag[1])
                    lines.append(f"\n{prefix} {text}\n")
                elif tag == "li":
                    lines.append(f"  • {text}")
                elif tag == "blockquote":
                    lines.append(f"  > {text}")
                elif tag in ("pre", "code"):
                    lines.append(f"\n```\n{text}\n```\n")
                else:
                    lines.append(text)

            content = "\n".join(lines).strip()
            if not content:
                content = main.get_text(separator="\n", strip=True)

            self._content = content
            GLib.idle_add(self._set_content, content)

        except ImportError:
            error = "Instale: pip install requests beautifulsoup4"
            GLib.idle_add(self._set_content, error)
        except Exception as e:
            GLib.idle_add(self._set_content, f"Erro ao carregar: {e}")

    def _extract_pdf(self, path: str) -> None:
        """Extract text from PDF."""
        try:
            import fitz  # pymupdf

            doc = fitz.open(path)
            pages = []
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    pages.append(f"--- Página {i + 1} ---\n{text}")
            doc.close()

            content = "\n\n".join(pages)
            self._content = content
            GLib.idle_add(self._set_content, content)

        except ImportError:
            error = "Instale: pip install pymupdf"
            GLib.idle_add(self._set_content, error)
        except Exception as e:
            GLib.idle_add(self._set_content, f"Erro ao ler PDF: {e}")

    def _set_content(self, text: str) -> None:
        """Set content in the text view (must be called from main thread)."""
        self._loading_box.set_visible(False)
        buf = self._content_view.get_buffer()
        buf.set_text(text)
        self._content = text

    def _url_to_title(self, url: str) -> str:
        """Extract a readable title from URL."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        path = parsed.path.strip("/").split("/")[-1] if parsed.path.strip("/") else ""
        if path:
            return f"{domain} — {path.replace('_', ' ').replace('-', ' ')}"
        return domain

    def _on_toggle_expand(self, *args) -> None:
        """Toggle between side panel and fullscreen."""
        if self._expanded:
            # Collapse back to side panel
            self.set_size_request(self._original_size, -1)
            self.set_hexpand(False)
            self._expand_btn.set_label("⛶")
            self._expand_btn.set_tooltip_text("Expandir")
            self._expanded = False
        else:
            # Expand to fill available space
            self._original_size = self.get_width() or 400
            self.set_size_request(-1, -1)
            self.set_hexpand(True)
            self._expand_btn.set_label("⊟")
            self._expand_btn.set_tooltip_text("Recolher")
            self._expanded = True

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
    border-right: 1px solid rgba(0,229,255,0.08);
}}

.artifact-header {{
    min-height: 36px;
}}

.artifact-title {{
    color: {FG};
    font-size: 12px;
    font-weight: 600;
}}

.artifact-source {{
    color: {FG_DIM};
    font-size: 12px;
    margin-end: 4px;
}}

.artifact-btn {{
    background: transparent;
    border: 1px solid {BORDER};
    border-radius: 6px;
    color: {FG_DIM};
    font-size: 13px;
    padding: 2px 8px;
    min-width: 28px;
    min-height: 28px;
}}

.artifact-btn:hover {{
    background: {BG_CARD};
    color: {ACCENT_LT};
    border-color: rgba(0,229,255,0.2);
}}

.artifact-loading-dot {{
    color: {ACCENT};
    font-size: 8px;
}}

.artifact-loading-text {{
    color: {FG_DIM};
    font-size: 11px;
}}

.artifact-content {{
    color: {FG};
    font-family: monospace;
    font-size: 13px;
    background: transparent;
}}
"""
