"""Email View — GTK4 widget for rendering email content in the artifact panel.

Displays email metadata (from, subject, date) and body in a scrollable view.
Used when the email handler returns structured email data.

#562 — UI: renderizar emails no artifact panel (OS)
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


def create_email_view(email_data: dict) -> "Gtk.Widget | None":
    """Create a GTK4 widget to display an email.

    Args:
        email_data: {"subject", "from", "to", "date", "body", "labels"}

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

    # Subject
    subject = email_data.get("subject", "(sem assunto)")
    subject_label = Gtk.Label(label=subject)
    subject_label.set_xalign(0)
    subject_label.set_wrap(True)
    subject_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    subject_label.add_css_class("title-3")
    box.append(subject_label)

    # Metadata (from, date)
    meta_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

    from_text = email_data.get("from", "")
    if from_text:
        from_label = Gtk.Label(label=f"De: {from_text}")
        from_label.set_xalign(0)
        from_label.add_css_class("dim-label")
        meta_box.append(from_label)

    to_text = email_data.get("to", "")
    if to_text:
        to_label = Gtk.Label(label=f"Para: {to_text}")
        to_label.set_xalign(0)
        to_label.add_css_class("dim-label")
        meta_box.append(to_label)

    date_text = email_data.get("date", "")
    if date_text:
        date_label = Gtk.Label(label=f"Data: {date_text}")
        date_label.set_xalign(0)
        date_label.add_css_class("dim-label")
        meta_box.append(date_label)

    box.append(meta_box)

    # Separator
    separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    separator.set_margin_top(4)
    separator.set_margin_bottom(4)
    box.append(separator)

    # Body (scrollable)
    body_text = email_data.get("body", "")
    body_label = Gtk.Label(label=body_text)
    body_label.set_xalign(0)
    body_label.set_wrap(True)
    body_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    body_label.set_selectable(True)

    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    scroll.set_child(body_label)
    box.append(scroll)

    # Labels (if any)
    labels = email_data.get("labels", [])
    if labels:
        labels_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        labels_box.set_margin_top(4)
        for label_text in labels[:5]:
            badge = Gtk.Label(label=label_text)
            badge.add_css_class("badge")
            labels_box.append(badge)
        box.append(labels_box)

    return box


def create_email_list_view(emails: list[dict], on_select=None) -> "Gtk.Widget | None":
    """Create a GTK4 widget to display a list of emails.

    Args:
        emails: List of {"subject", "from", "date"} dicts
        on_select: Callback when an email is clicked

    Returns:
        Gtk.ListBox widget or None if GTK not available.
    """
    if Gtk is None:
        return None

    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
    listbox.add_css_class("boxed-list")

    for _i, email in enumerate(emails[:10]):
        row = Gtk.ListBoxRow()
        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row_box.set_margin_start(8)
        row_box.set_margin_end(8)
        row_box.set_margin_top(6)
        row_box.set_margin_bottom(6)

        subject = Gtk.Label(label=email.get("subject", "(sem assunto)"))
        subject.set_xalign(0)
        subject.set_ellipsize(Pango.EllipsizeMode.END)
        row_box.append(subject)

        from_label = Gtk.Label(label=email.get("from", ""))
        from_label.set_xalign(0)
        from_label.set_ellipsize(Pango.EllipsizeMode.END)
        from_label.add_css_class("dim-label")
        from_label.add_css_class("caption")
        row_box.append(from_label)

        row.set_child(row_box)
        listbox.append(row)

    if on_select:

        def _on_row_activated(lb, row):
            idx = row.get_index()
            if 0 <= idx < len(emails):
                on_select(emails[idx])

        listbox.connect("row-activated", _on_row_activated)

    return listbox
