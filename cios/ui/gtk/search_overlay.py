"""CIOS GTK4 Search Overlay — History search (Ctrl+K).

A floating search bar with live results from conversation history.
Triggered via compositor IPC (Ctrl+K) or intent "busca no histórico".
"""

import logging

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from cios.ui.theme import (
    ACCENT,
    ACCENT_LT,
    BG,
    BG_CARD,
    BG_HOVER,
    BG_INPUT,
    BORDER,
    FG,
    FG_DIM,
    FG_SEC,
    SUCCESS,
)

logger = logging.getLogger(__name__)


class SearchOverlay(Gtk.Box):
    """Floating search overlay with live results from thread history."""

    def __init__(self, bridge=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("search-overlay")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.START)
        self.set_margin_top(80)
        self.set_size_request(560, -1)
        self.set_visible(False)
        self._bridge = bridge
        self._debounce_id = None

        # Search input row
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_row.add_css_class("search-input-row")
        self.append(input_row)

        # Search icon
        icon = Gtk.Label(label="🔍")
        icon.add_css_class("search-icon")
        input_row.append(icon)

        # Input
        self._input = Gtk.Entry()
        self._input.set_placeholder_text("Buscar no histórico…")
        self._input.set_hexpand(True)
        self._input.add_css_class("search-input")
        self._input.connect("activate", self._on_activate)
        self._input.connect("changed", self._on_text_changed)
        input_row.append(self._input)

        # Shortcut hint
        hint = Gtk.Label(label="Esc para fechar")
        hint.add_css_class("search-hint")
        input_row.append(hint)

        # Results container (scrollable)
        self._results_scroll = Gtk.ScrolledWindow()
        self._results_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._results_scroll.set_max_content_height(320)
        self._results_scroll.set_propagate_natural_height(True)
        self._results_scroll.set_visible(False)
        self.append(self._results_scroll)

        self._results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._results_box.add_css_class("search-results")
        self._results_scroll.set_child(self._results_box)

        # Key controller for Escape
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self._input.add_controller(key_ctrl)

    def set_bridge(self, bridge):
        """Set bridge after initialization."""
        self._bridge = bridge

    def show_overlay(self):
        """Show the search overlay and focus input."""
        self.set_visible(True)
        self._input.set_text("")
        self._clear_results()
        self._input.grab_focus()

    def hide_overlay(self):
        """Hide the search overlay."""
        self.set_visible(False)
        self._clear_results()
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
            self._debounce_id = None

    def toggle(self):
        """Toggle visibility."""
        if self.get_visible():
            self.hide_overlay()
        else:
            self.show_overlay()

    def _on_key_pressed(self, controller, keyval, keycode, state):
        """Handle Escape to close overlay."""
        if keyval == 65307:  # Escape
            self.hide_overlay()
            return True
        return False

    def _on_text_changed(self, entry):
        """Debounced search on text change (300ms delay)."""
        if self._debounce_id:
            GLib.source_remove(self._debounce_id)
        text = entry.get_text().strip()
        if len(text) >= 2:
            self._debounce_id = GLib.timeout_add(300, self._do_search, text)
        else:
            self._clear_results()

    def _on_activate(self, entry):
        """Immediate search on Enter."""
        text = entry.get_text().strip()
        if text:
            self._do_search(text)

    def _do_search(self, query: str) -> bool:
        """Execute search against thread store."""
        self._debounce_id = None

        if not self._bridge:
            return False

        try:
            results = self._bridge.search_history(query, limit=8)
        except Exception as e:
            logger.debug("Search failed: %s", e)
            results = []

        self._render_results(results, query)
        return False  # Don't repeat GLib timeout

    def _clear_results(self):
        """Remove all result widgets."""
        self._results_scroll.set_visible(False)
        child = self._results_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._results_box.remove(child)
            child = next_child

    def _render_results(self, results: list[dict], query: str):
        """Render search results."""
        self._clear_results()

        if not results:
            empty = Gtk.Label(label=f"Nenhum resultado para '{query}'")
            empty.add_css_class("search-empty")
            self._results_box.append(empty)
            self._results_scroll.set_visible(True)
            return

        # Header
        header = Gtk.Label(label=f"{len(results)} resultado(s)")
        header.add_css_class("search-header")
        header.set_halign(Gtk.Align.START)
        self._results_box.append(header)

        for result in results:
            row = self._build_result_row(result)
            self._results_box.append(row)

        self._results_scroll.set_visible(True)

    def _build_result_row(self, result: dict) -> Gtk.Box:
        """Build a single search result row."""
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row.add_css_class("search-result-row")

        # Top: icon + summary + time
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(top)

        # Outcome icon
        outcome = result.get("outcome", "")
        icon = "✓" if outcome == "success" else "○"
        icon_label = Gtk.Label(label=icon)
        icon_label.add_css_class("search-result-icon")
        top.append(icon_label)

        # Summary
        summary = result.get("summary", "")[:60]
        summary_label = Gtk.Label(label=summary)
        summary_label.set_halign(Gtk.Align.START)
        summary_label.set_hexpand(True)
        summary_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        summary_label.add_css_class("search-result-summary")
        top.append(summary_label)

        # Time
        created = result.get("created_at", 0)
        time_str = self._format_time(created) if created else ""
        time_label = Gtk.Label(label=time_str)
        time_label.add_css_class("search-result-time")
        top.append(time_label)

        # Preview of first turn
        turns = result.get("turns", [])
        if turns:
            first_input = turns[0].get("input", "")
            first_result = turns[0].get("result", "")
            preview = first_result[:80] if first_result else first_input[:80]
            if preview:
                preview_label = Gtk.Label(label=f"  → {preview}")
                preview_label.set_halign(Gtk.Align.START)
                preview_label.set_ellipsize(3)
                preview_label.add_css_class("search-result-preview")
                row.append(preview_label)

        return row

    @staticmethod
    def _format_time(ts: float) -> str:
        """Format timestamp as relative time."""
        import time

        diff = time.time() - ts
        if diff < 60:
            return "agora"
        elif diff < 3600:
            return f"{int(diff // 60)}min"
        elif diff < 86400:
            return f"{int(diff // 3600)}h"
        else:
            return f"{int(diff // 86400)}d"

    @staticmethod
    def get_css() -> str:
        """Return CSS for search overlay."""
        return f"""
            .search-overlay {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 14px;
                padding: 0;
                box-shadow: 0 8px 32px rgba(0,0,0,0.6);
            }}
            .search-input-row {{
                padding: 12px 16px;
                border-bottom: 1px solid {BORDER};
            }}
            .search-icon {{
                font-size: 16px;
                opacity: 0.6;
            }}
            .search-input {{
                background: {BG_INPUT};
                color: {FG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 15px;
                box-shadow: none;
            }}
            .search-input:focus {{
                border-color: {ACCENT_LT};
            }}
            .search-hint {{
                color: {FG_DIM};
                font-size: 11px;
            }}
            .search-results {{
                padding: 8px 12px;
            }}
            .search-empty {{
                color: {FG_DIM};
                font-size: 13px;
                padding: 16px;
            }}
            .search-header {{
                color: {FG_DIM};
                font-size: 11px;
                padding: 4px 8px;
                margin-bottom: 4px;
            }}
            .search-result-row {{
                padding: 8px 12px;
                border-radius: 8px;
                transition: background 150ms;
            }}
            .search-result-row:hover {{
                background: {BG_HOVER};
            }}
            .search-result-icon {{
                color: {SUCCESS};
                font-size: 12px;
            }}
            .search-result-summary {{
                color: {FG};
                font-size: 13px;
            }}
            .search-result-time {{
                color: {FG_DIM};
                font-size: 11px;
            }}
            .search-result-preview {{
                color: {FG_SEC};
                font-size: 12px;
                margin-left: 20px;
            }}
        """
