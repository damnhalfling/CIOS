"""CIOS GTK4 Gallery Component — Thumbnail grid for media files.

Renders a responsive grid of image/video thumbnails using Gtk.FlowBox.
Thumbnails are loaded asynchronously in a background thread.
"""

import logging
import os
import threading

from gi.repository import GdkPixbuf, GLib, Gtk

from cios.ui.theme import BG_CARD, BG_HOVER, FG_DIM, FG_SEC

logger = logging.getLogger(__name__)

THUMB_SIZE = 140


class GalleryComponent(Gtk.Box):
    """Scrollable thumbnail grid widget."""

    def __init__(self, gallery_data: dict, on_image_click=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("gallery")
        self._gallery_data = gallery_data
        self._on_image_click = on_image_click
        self._files = gallery_data.get("files", [])
        self._source_path = gallery_data.get("source_path", "")

        # Header
        header = Gtk.Label(label=f"📁 {self._source_path} ({len(self._files)} arquivos)")
        header.add_css_class("gallery-header")
        header.set_halign(Gtk.Align.START)
        self.append(header)

        # Scrollable flow box
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        self._flowbox = Gtk.FlowBox()
        self._flowbox.set_valign(Gtk.Align.START)
        self._flowbox.set_max_children_per_line(6)
        self._flowbox.set_min_children_per_line(2)
        self._flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flowbox.set_homogeneous(True)
        self._flowbox.set_column_spacing(8)
        self._flowbox.set_row_spacing(8)
        scroll.set_child(self._flowbox)

        # Add placeholder cells, then load thumbnails async
        for i, file_info in enumerate(self._files):
            cell = self._create_cell(i, file_info)
            self._flowbox.append(cell)

        # Load thumbnails in background
        threading.Thread(target=self._load_thumbnails, daemon=True).start()

    def _create_cell(self, index: int, file_info: dict) -> Gtk.Box:
        """Create a thumbnail cell with placeholder."""
        cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        cell.add_css_class("gallery-cell")
        cell.set_size_request(THUMB_SIZE + 16, THUMB_SIZE + 32)

        # Thumbnail image (placeholder)
        image = Gtk.Image()
        image.set_pixel_size(THUMB_SIZE)
        image.set_from_icon_name("image-x-generic")
        image.add_css_class("gallery-thumb")
        cell.append(image)

        # Filename label
        name = file_info.get("name", os.path.basename(file_info.get("path", "")))
        label = Gtk.Label(label=name)
        label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        label.set_max_width_chars(15)
        label.add_css_class("gallery-filename")
        cell.append(label)

        # Click handler
        click = Gtk.GestureClick()
        click.connect("released", lambda g, n, x, y, idx=index: self._on_click(idx))
        cell.add_controller(click)

        # Store image widget ref for async update
        cell._thumb_image = image
        cell._file_index = index

        return cell

    def _on_click(self, index: int):
        """Handle thumbnail click."""
        if self._on_image_click:
            self._on_image_click(self._files, index)

    def _load_thumbnails(self):
        """Load thumbnails in background thread."""
        for i, file_info in enumerate(self._files):
            path = file_info.get("path", "")
            if not os.path.isfile(path):
                continue

            try:
                # Load and scale with GdkPixbuf
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, THUMB_SIZE, THUMB_SIZE, True)
                GLib.idle_add(self._set_thumbnail, i, pixbuf)
            except Exception as e:
                logger.debug("Failed to load thumbnail for %s: %s", path, e)

    def _set_thumbnail(self, index: int, pixbuf):
        """Set thumbnail on the main thread."""
        # Find the cell by index
        child = self._flowbox.get_child_at_index(index)
        if child:
            cell = child.get_child()
            if hasattr(cell, "_thumb_image"):
                cell._thumb_image.set_from_pixbuf(pixbuf)
        return False  # Don't repeat

    @staticmethod
    def get_css() -> str:
        """Return CSS for gallery styling."""
        return f"""
            .gallery {{
                margin: 8px 0;
            }}
            .gallery-header {{
                color: {FG_SEC};
                font-size: 13px;
                font-weight: bold;
            }}
            .gallery-cell {{
                background: {BG_CARD};
                border-radius: 8px;
                padding: 8px;
            }}
            .gallery-cell:hover {{
                background: {BG_HOVER};
            }}
            .gallery-thumb {{
                border-radius: 4px;
            }}
            .gallery-filename {{
                color: {FG_DIM};
                font-size: 10px;
            }}
        """
