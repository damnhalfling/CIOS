"""CIOS GTK4 Image Viewer — Full-size image display with navigation.

Shows images fullscreen with keyboard navigation (Left/Right),
slideshow mode, and close on Escape.
"""

import logging
import os

from gi.repository import GLib, Gtk

from cios.ui.theme import BG, FG, FG_DIM

logger = logging.getLogger(__name__)


class ImageViewer(Gtk.Box):
    """Full-size image viewer overlay."""

    def __init__(self, files: list, start_index: int = 0, on_close=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("image-viewer")
        self._files = files
        self._current_index = start_index
        self._on_close = on_close
        self._slideshow_active = False
        self._slideshow_id = None

        # Image display
        self._picture = Gtk.Picture()
        self._picture.set_vexpand(True)
        self._picture.set_hexpand(True)
        self._picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.append(self._picture)

        # Bottom bar (filename + controls)
        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        bottom.add_css_class("viewer-bottom")
        bottom.set_margin_start(16)
        bottom.set_margin_end(16)
        bottom.set_margin_bottom(8)
        self.append(bottom)

        self._filename_label = Gtk.Label(label="")
        self._filename_label.add_css_class("viewer-filename")
        self._filename_label.set_halign(Gtk.Align.START)
        self._filename_label.set_hexpand(True)
        bottom.append(self._filename_label)

        self._counter_label = Gtk.Label(label="")
        self._counter_label.add_css_class("viewer-counter")
        bottom.append(self._counter_label)

        # Keyboard controller
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        # Load first image
        self._show_image(self._current_index)

    def _show_image(self, index: int):
        """Display image at given index."""
        if index < 0 or index >= len(self._files):
            return

        self._current_index = index
        file_info = self._files[index]
        path = file_info.get("path", "")
        name = file_info.get("name", os.path.basename(path))

        self._filename_label.set_label(name)
        self._counter_label.set_label(f"{index + 1}/{len(self._files)}")

        if os.path.isfile(path):
            try:
                self._picture.set_filename(path)
            except Exception as e:
                logger.warning("Failed to load image %s: %s", path, e)
                self._picture.set_filename(None)
        else:
            self._picture.set_filename(None)

    def navigate(self, direction: int):
        """Navigate to next (+1) or previous (-1) image."""
        new_index = self._current_index + direction
        if 0 <= new_index < len(self._files):
            self._show_image(new_index)

    def start_slideshow(self):
        """Start automatic slideshow (5s interval)."""
        self._slideshow_active = True
        self._slideshow_id = GLib.timeout_add(5000, self._slideshow_next)

    def stop_slideshow(self):
        """Stop slideshow."""
        self._slideshow_active = False
        if self._slideshow_id:
            GLib.source_remove(self._slideshow_id)
            self._slideshow_id = None

    def _slideshow_next(self):
        """Advance to next image in slideshow."""
        if not self._slideshow_active:
            return False
        if self._current_index < len(self._files) - 1:
            self.navigate(1)
            return True  # Continue
        else:
            self.stop_slideshow()
            return False

    def _on_key(self, controller, keyval, keycode, state):
        """Handle keyboard navigation."""
        from gi.repository import Gdk

        if keyval == Gdk.KEY_Escape:
            if self._slideshow_active:
                self.stop_slideshow()
            elif self._on_close:
                self._on_close()
            return True
        elif keyval == Gdk.KEY_Right:
            self.navigate(1)
            return True
        elif keyval == Gdk.KEY_Left:
            self.navigate(-1)
            return True
        elif keyval == Gdk.KEY_space:
            if self._slideshow_active:
                self.stop_slideshow()
            else:
                self.start_slideshow()
            return True
        return False

    def close(self):
        """Clean up and close viewer."""
        self.stop_slideshow()
        if self._on_close:
            self._on_close()

    @staticmethod
    def get_css() -> str:
        """Return CSS for image viewer."""
        return f"""
            .image-viewer {{
                background: {BG};
            }}
            .viewer-bottom {{
                background: rgba(0, 0, 0, 0.6);
                border-radius: 8px;
                padding: 8px 16px;
            }}
            .viewer-filename {{
                color: {FG};
                font-size: 13px;
            }}
            .viewer-counter {{
                color: {FG_DIM};
                font-size: 12px;
            }}
        """
