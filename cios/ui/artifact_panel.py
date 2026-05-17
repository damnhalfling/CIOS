"""Artifact Panel — Split view for multi-section content in CIOS OS.

When the Intelligence generates an artifact (multi-target content like
LinkedIn EN/PT + Twitter EN/PT), this panel replaces the right sidebar
with copy-ready blocks in accordion style.

Each section has:
- Collapsible header with label
- Copy button that copies to system clipboard
- Content area with monospace text
"""

import tkinter as tk
import tkinter.font as tkfont
import re
from typing import Callable, Optional


# Colors (matching CIOS theme)
BG = "#0a0a0f"
BG_PANEL = "#0e0e16"
BG_CARD = "#161622"
BG_HOVER = "#1e1e2e"
FG = "#e6e6ee"
FG_SEC = "#a0a0b4"
FG_DIM = "#606070"
ACCENT = "#0c8de9"
BORDER = "#262634"
SUCCESS = "#4ade80"


class ArtifactSection:
    """A single collapsible section with copy button."""

    def __init__(
        self,
        parent: tk.Frame,
        label: str,
        content: str,
        fonts: dict,
        is_open: bool = False,
    ):
        self._content = content
        self._is_open = is_open

        # Container
        self.frame = tk.Frame(parent, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        self.frame.pack(fill="x", padx=8, pady=4)

        # Header (clickable)
        header = tk.Frame(self.frame, bg=BG_CARD, padx=12, pady=8)
        header.pack(fill="x")
        header.bind("<Button-1>", lambda _: self.toggle())

        # Chevron
        self._chevron = tk.Label(
            header, text="▶" if not is_open else "▼",
            font=fonts.get("small", None), fg=FG_DIM, bg=BG_CARD,
        )
        self._chevron.pack(side="left", padx=(0, 6))
        self._chevron.bind("<Button-1>", lambda _: self.toggle())

        # Label
        lbl = tk.Label(
            header, text=label.upper(),
            font=fonts.get("metric", None), fg=FG_SEC, bg=BG_CARD,
        )
        lbl.pack(side="left")
        lbl.bind("<Button-1>", lambda _: self.toggle())

        # Copy button
        self._copy_btn = tk.Label(
            header, text="📋 Copiar",
            font=fonts.get("small", None), fg=ACCENT, bg=BG_CARD,
            cursor="hand2",
        )
        self._copy_btn.pack(side="right")
        self._copy_btn.bind("<Button-1>", lambda _: self._copy())

        # Content area (collapsible)
        self._content_frame = tk.Frame(self.frame, bg=BG_CARD)
        if is_open:
            self._content_frame.pack(fill="x", padx=12, pady=(0, 8))

        self._text = tk.Text(
            self._content_frame,
            bg=BG,
            fg=FG,
            font=fonts.get("small", None),
            wrap="word",
            height=min(15, content.count("\n") + 3),
            borderwidth=0,
            highlightthickness=0,
            padx=8,
            pady=8,
            insertbackground=FG,
        )
        self._text.pack(fill="x")
        self._text.insert("1.0", content)
        self._text.config(state="disabled")

    def toggle(self):
        """Toggle section open/closed."""
        self._is_open = not self._is_open
        if self._is_open:
            self._content_frame.pack(fill="x", padx=12, pady=(0, 8))
            self._chevron.config(text="▼")
        else:
            self._content_frame.pack_forget()
            self._chevron.config(text="▶")

    def _copy(self):
        """Copy content to system clipboard."""
        self._text.config(state="normal")
        content = self._text.get("1.0", "end-1c")
        self._text.config(state="disabled")

        root = self.frame.winfo_toplevel()
        root.clipboard_clear()
        root.clipboard_append(content)

        # Visual feedback
        self._copy_btn.config(text="✓ Copiado", fg=SUCCESS)
        root.after(2000, lambda: self._copy_btn.config(text="📋 Copiar", fg=ACCENT))


class ArtifactPanel:
    """Full artifact panel that replaces the right sidebar."""

    def __init__(self, parent: tk.Frame, fonts: dict, on_close: Optional[Callable] = None):
        self._parent = parent
        self._fonts = fonts
        self._on_close = on_close
        self._frame: Optional[tk.Frame] = None
        self._sections: list[ArtifactSection] = []

    def show(self, content: str) -> None:
        """Parse content into sections and display the panel."""
        self.hide()

        self._frame = tk.Frame(self._parent, bg=BG_PANEL)
        self._frame.pack(fill="both", expand=True)

        # Header
        header = tk.Frame(self._frame, bg=BG_PANEL, padx=12, pady=10)
        header.pack(fill="x")

        tk.Label(
            header, text="📄 Artefato",
            font=self._fonts.get("sec", None), fg=FG, bg=BG_PANEL,
        ).pack(side="left")

        # Close button
        close_btn = tk.Label(
            header, text="✕",
            font=self._fonts.get("metric", None), fg=FG_DIM, bg=BG_PANEL,
            cursor="hand2",
        )
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda _: self._close())

        # Separator
        tk.Frame(self._frame, bg=BORDER, height=1).pack(fill="x")

        # Scrollable content
        scroll = ScrollableFrame(self._frame)
        scroll.pack(fill="both", expand=True)

        # Parse sections
        sections = self._parse_sections(content)
        for i, (label, section_content) in enumerate(sections):
            sec = ArtifactSection(
                scroll.interior,
                label=label,
                content=section_content,
                fonts=self._fonts,
                is_open=(i == 0),  # First section open by default
            )
            self._sections.append(sec)

    def hide(self) -> None:
        """Hide and destroy the panel."""
        if self._frame:
            self._frame.destroy()
            self._frame = None
        self._sections = []

    def is_visible(self) -> bool:
        return self._frame is not None

    def _close(self) -> None:
        self.hide()
        if self._on_close:
            self._on_close()

    def _parse_sections(self, content: str) -> list[tuple[str, str]]:
        """Parse content into (label, content) tuples."""
        sections = []

        # Try === separators first
        sep_pattern = r'^={3,}\s*\[?\s*(.+?)\s*\]?\s*={3,}$'
        matches = list(re.finditer(sep_pattern, content, re.MULTILINE))

        if matches:
            for i, match in enumerate(matches):
                label = match.group(1).strip()
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                section_content = content[start:end].strip()
                if section_content:
                    sections.append((label, section_content))
            if sections:
                return sections

        # Try ## headers
        header_pattern = r'^##\s+(.+)$'
        matches = list(re.finditer(header_pattern, content, re.MULTILINE))

        if len(matches) > 1:
            for i, match in enumerate(matches):
                label = match.group(1).strip()
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                section_content = content[start:end].strip()
                if section_content:
                    sections.append((label, section_content))
            if sections:
                return sections

        # Try bold headers like **LinkedIn EN**
        bold_pattern = r'^\*\*(.+?)\*\*\s*$'
        matches = list(re.finditer(bold_pattern, content, re.MULTILINE))

        if len(matches) > 1:
            for i, match in enumerate(matches):
                label = match.group(1).strip()
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
                section_content = content[start:end].strip()
                if section_content:
                    sections.append((label, section_content))
            if sections:
                return sections

        # Single block fallback
        return [("Content", content)]


class ScrollableFrame(tk.Frame):
    """Scrollable frame for the artifact content."""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG_PANEL, **kw)

        self._canvas = tk.Canvas(self, bg=BG_PANEL, highlightthickness=0)
        self._scrollbar = tk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self.interior = tk.Frame(self._canvas, bg=BG_PANEL)

        self.interior.bind("<Configure>", self._on_configure)
        self._canvas_window = self._canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        self._canvas.pack(side="left", fill="both", expand=True)
        # Hide scrollbar for cleaner look (scroll with mousewheel)

        self._canvas.bind_all("<MouseWheel>", self._on_wheel)
        self._canvas.bind_all("<Button-4>", self._on_wheel)
        self._canvas.bind_all("<Button-5>", self._on_wheel)

    def _on_configure(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._canvas_window, width=e.width)

    def _on_wheel(self, e):
        if e.num == 4 or e.delta > 0:
            self._canvas.yview_scroll(-1, "units")
        elif e.num == 5 or e.delta < 0:
            self._canvas.yview_scroll(1, "units")
