"""CIOS GTK4 Update Indicator — Shows update availability in the UI.

Checks for updates periodically (every 6 hours) and shows a notification
badge in the topbar when a new version is available. Clicking it triggers
the update flow via the bridge.

Integration:
- Topbar shows "⬆" indicator when update available
- Sidebar shows version + update button
- Bridge handles the actual download/install via self_update skill
"""

import logging
import threading

from gi.repository import GLib, Gtk

from cios.ui.theme import ACCENT_LT, FG_DIM

logger = logging.getLogger(__name__)

# Check interval: 6 hours
_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000


class UpdateIndicator(Gtk.Box):
    """Update notification widget for the topbar."""

    def __init__(self, on_update_click=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._on_update_click = on_update_click
        self._has_update = False
        self._latest_version = ""

        # Update button (hidden by default)
        self._btn = Gtk.Button(label="⬆")
        self._btn.add_css_class("update-btn")
        self._btn.set_visible(False)
        self._btn.set_tooltip_text("Atualização disponível")
        self._btn.connect("clicked", self._on_click)
        self.append(self._btn)

        # Check for updates in background after 30s (don't slow boot)
        GLib.timeout_add(30000, self._initial_check)

    def _initial_check(self):
        """First check after boot."""
        self._check_async()
        # Schedule periodic checks
        GLib.timeout_add(_CHECK_INTERVAL_MS, self._periodic_check)
        return False  # One-shot

    def _periodic_check(self):
        """Periodic update check."""
        self._check_async()
        return True  # Keep repeating

    def _check_async(self):
        """Check for updates in background thread."""

        def do_check():
            try:
                from cios.skills.self_update import check_update

                info = check_update(use_cache=True)
                if info.has_update:
                    GLib.idle_add(self._show_update, info.latest_version)
                else:
                    GLib.idle_add(self._hide_update)
            except Exception as e:
                logger.debug("Update check failed: %s", e)

        threading.Thread(target=do_check, daemon=True).start()

    def _show_update(self, version: str):
        """Show update indicator."""
        self._has_update = True
        self._latest_version = version
        self._btn.set_label(f"⬆ v{version}")
        self._btn.set_tooltip_text(f"CIOS v{version} disponível — clique para atualizar")
        self._btn.set_visible(True)

    def _hide_update(self):
        """Hide update indicator."""
        self._has_update = False
        self._btn.set_visible(False)

    def _on_click(self, btn):
        """Handle click on update button."""
        if self._on_update_click:
            self._on_update_click(self._latest_version)

    @property
    def has_update(self) -> bool:
        return self._has_update

    @property
    def latest_version(self) -> str:
        return self._latest_version

    @staticmethod
    def get_css() -> str:
        """Return CSS for update indicator."""
        return f"""
            .update-btn {{
                background: transparent;
                color: {ACCENT_LT};
                border: 1px solid {ACCENT_LT};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
                min-height: 16px;
            }}
            .update-btn:hover {{
                background: {ACCENT_LT};
                color: white;
            }}
        """


class UpdatePanel(Gtk.Box):
    """Update panel for the sidebar — shows version info and update button."""

    def __init__(self, on_update=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._on_update = on_update
        self.add_css_class("update-panel")

        # Version label
        try:
            from cios import __version__

            version = __version__
        except ImportError:
            version = "?"

        self._version_label = Gtk.Label(label=f"CIOS v{version}")
        self._version_label.add_css_class("version-label")
        self._version_label.set_halign(Gtk.Align.START)
        self.append(self._version_label)

        # Status label (hidden by default)
        self._status_label = Gtk.Label(label="")
        self._status_label.add_css_class("update-status")
        self._status_label.set_halign(Gtk.Align.START)
        self._status_label.set_visible(False)
        self.append(self._status_label)

        # Update button (hidden by default)
        self._update_btn = Gtk.Button(label="⬆ Atualizar")
        self._update_btn.add_css_class("sidebar-update-btn")
        self._update_btn.set_visible(False)
        self._update_btn.connect("clicked", self._on_update_click)
        self.append(self._update_btn)

        # Check in background
        GLib.timeout_add(5000, self._check)

    def _check(self):
        """Check for updates."""

        def do_check():
            try:
                from cios.skills.self_update import check_update

                info = check_update(use_cache=True)
                if info.has_update:
                    GLib.idle_add(self._show_available, info.latest_version)
                else:
                    GLib.idle_add(self._show_up_to_date)
            except Exception:
                pass

        threading.Thread(target=do_check, daemon=True).start()
        return False  # One-shot

    def _show_available(self, version: str):
        """Show that an update is available."""
        self._status_label.set_label(f"Nova versão: v{version}")
        self._status_label.set_visible(True)
        self._update_btn.set_visible(True)

    def _show_up_to_date(self):
        """Show that system is up to date."""
        self._status_label.set_label("✓ Atualizado")
        self._status_label.set_visible(True)
        self._update_btn.set_visible(False)

    def _on_update_click(self, btn):
        """Trigger update via bridge."""
        if self._on_update:
            self._on_update()
        else:
            # Fallback: submit "atualizar cios" as command
            btn.set_label("Atualizando…")
            btn.set_sensitive(False)

    @staticmethod
    def get_css() -> str:
        """Return CSS for update panel."""
        return f"""
            .update-panel {{
                padding: 8px 0;
            }}
            .version-label {{
                color: {FG_DIM};
                font-size: 11px;
            }}
            .update-status {{
                color: {ACCENT_LT};
                font-size: 11px;
            }}
            .sidebar-update-btn {{
                background: transparent;
                color: {ACCENT_LT};
                border: 1px solid {ACCENT_LT};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
            }}
            .sidebar-update-btn:hover {{
                background: {ACCENT_LT};
                color: white;
            }}
        """
