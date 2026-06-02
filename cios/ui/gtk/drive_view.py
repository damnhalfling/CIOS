"""Drive View — GTK4 widget for rendering Google Drive file content in the artifact panel.

Displays file metadata (name, type, modified date) and content preview.
Used when the drive handler returns structured file data.

#563 — UI: renderizar docs do Drive no artifact panel (OS)
"""

import logging

logger = logging.getLogger(__name__)

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk, Pango
except ImportError:
    Gtk = None
    Pango = None


MIME_ICONS = {
    "application/vnd.google-apps.document": "📄",
    "application/vnd.google-apps.spreadsheet": "📊",
    "application/vnd.google-apps.presentation": "📽️",
    "application/pdf": "📕",
    "text/plain": "📝",
    "text/csv": "📊",
}


def _get_icon(mime_type: str) -> str:
    """Get emoji icon for a MIME type."""
    for prefix, icon in MIME_ICONS.items():
        if mime_type and mime_type.startswith(prefix):
            return icon
    return "📄"


def _format_size(size_bytes: int | None) -> str:
    """Format file size in human-readable form."""
    if not size_bytes:
        return ""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def create_drive_view(file_data: dict) -> "Gtk.Widget | None":
    """Create a GTK4 widget to display a Drive file.

    Args:
        file_data: {"name", "mimeType", "content", "modifiedTime", "size", "webViewLink"}

    Returns:
        Gtk.Box widget or None if GTK not available.
    """
    if Gtk is None:
        return None

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_margin_start(12)
    box.set_margin_end(12)
    box.set_margin_top(8)
    box.set_margin_bottom(8)

    # Header (icon + name + metadata)
    header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

    mime_type = file_data.get("mimeType", "")
    icon = _get_icon(mime_type)
    icon_label = Gtk.Label(label=icon)
    icon_label.add_css_class("title-1")
    header_box.append(icon_label)

    info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

    name = file_data.get("name", "Arquivo")
    name_label = Gtk.Label(label=name)
    name_label.set_xalign(0)
    name_label.set_ellipsize(Pango.EllipsizeMode.END)
    name_label.add_css_class("title-3")
    info_box.append(name_label)

    # Metadata line
    meta_parts = []
    if mime_type:
        short_type = mime_type.split("/")[-1].replace("vnd.google-apps.", "")
        meta_parts.append(short_type)
    modified = file_data.get("modifiedTime", "")
    if modified:
        meta_parts.append(f"Modificado: {modified[:10]}")
    size = file_data.get("size")
    if size:
        meta_parts.append(_format_size(size))

    if meta_parts:
        meta_label = Gtk.Label(label=" · ".join(meta_parts))
        meta_label.set_xalign(0)
        meta_label.add_css_class("dim-label")
        meta_label.add_css_class("caption")
        info_box.append(meta_label)

    header_box.append(info_box)
    box.append(header_box)

    # Separator
    separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    separator.set_margin_top(4)
    separator.set_margin_bottom(4)
    box.append(separator)

    # Content (scrollable)
    content = file_data.get("content", "")
    if content:
        content_label = Gtk.Label(label=content)
        content_label.set_xalign(0)
        content_label.set_wrap(True)
        content_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        content_label.set_selectable(True)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(content_label)
        box.append(scroll)
    else:
        placeholder = Gtk.Label(label="Conteúdo não disponível para preview.")
        placeholder.add_css_class("dim-label")
        placeholder.set_margin_top(16)
        placeholder.set_margin_bottom(16)
        box.append(placeholder)

    return box


def create_drive_list_view(files: list[dict], on_select=None) -> "Gtk.Widget | None":
    """Create a GTK4 widget to display a list of Drive files.

    Args:
        files: List of {"name", "mimeType", "modifiedTime", "size"} dicts
        on_select: Callback when a file is clicked

    Returns:
        Gtk.ListBox widget or None if GTK not available.
    """
    if Gtk is None:
        return None

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.add_css_class("boxed-list")

    for _i, file in enumerate(files[:10]):
        row = Gtk.ListBoxRow()
        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_box.set_margin_start(8)
        row_box.set_margin_end(8)
        row_box.set_margin_top(6)
        row_box.set_margin_bottom(6)

        # Icon
        mime_type = file.get("mimeType", "")
        icon = _get_icon(mime_type)
        icon_label = Gtk.Label(label=icon)
        row_box.append(icon_label)

        # Name + meta
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        info_box.set_hexpand(True)

        name_label = Gtk.Label(label=file.get("name", "?"))
        name_label.set_xalign(0)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        info_box.append(name_label)

        modified = file.get("modifiedTime", "")
        if modified:
            date_label = Gtk.Label(label=modified[:10])
            date_label.set_xalign(0)
            date_label.add_css_class("dim-label")
            date_label.add_css_class("caption")
            info_box.append(date_label)

        row_box.append(info_box)

        # Size
        size = file.get("size")
        if size:
            size_label = Gtk.Label(label=_format_size(size))
            size_label.add_css_class("dim-label")
            size_label.add_css_class("caption")
            row_box.append(size_label)

        row.set_child(row_box)
        listbox.append(row)

    if on_select:

        def _on_row_activated(lb, row):
            idx = row.get_index()
            if 0 <= idx < len(files):
                on_select(files[idx])

        listbox.connect("row-activated", _on_row_activated)

    return listbox
