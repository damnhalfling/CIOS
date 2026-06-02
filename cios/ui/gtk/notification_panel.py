"""Notification Panel — GTK4 widget for displaying notifications.

Shows notification history with dismiss/action buttons.
Subscribes to the notification bus and updates in real-time.

#501 — Notification center (histórico, dismiss, actions)
"""

import logging

logger = logging.getLogger(__name__)

try:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk, Pango
except ImportError:
    Gtk = None
    GLib = None
    Pango = None


class NotificationPanel:
    """GTK4 notification panel — shows history, supports dismiss and actions.

    Usage:
        panel = NotificationPanel()
        panel.show()  # Opens the panel
        panel.hide()  # Closes it
        panel.get_widget()  # Returns the GTK widget to embed
    """

    def __init__(self):
        if Gtk is None:
            self._widget = None
            return

        from cios.infra.notifications import bus

        self._bus = bus
        self._widget = self._build_widget()
        self._rows: dict[str, Gtk.ListBoxRow] = {}

        # Subscribe to live notifications
        bus.subscribe(self._on_notification)

        # Load existing history
        self._load_history()

    def get_widget(self) -> "Gtk.Widget | None":
        """Get the GTK widget for embedding in the UI."""
        return self._widget

    def show(self) -> None:
        """Show the notification panel."""
        if self._widget:
            self._widget.set_visible(True)

    def hide(self) -> None:
        """Hide the notification panel."""
        if self._widget:
            self._widget.set_visible(False)

    def toggle(self) -> None:
        """Toggle panel visibility."""
        if self._widget:
            self._widget.set_visible(not self._widget.get_visible())

    def _build_widget(self) -> "Gtk.Box":
        """Build the notification panel widget."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_size_request(320, -1)
        box.add_css_class("notification-panel")

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_top(8)
        header.set_margin_bottom(8)

        title = Gtk.Label(label="Notificações")
        title.set_xalign(0)
        title.set_hexpand(True)
        title.add_css_class("title-4")
        header.append(title)

        # Unread badge
        self._badge = Gtk.Label(label="0")
        self._badge.add_css_class("badge")
        self._badge.set_visible(False)
        header.append(self._badge)

        # Clear all button
        clear_btn = Gtk.Button(label="Limpar")
        clear_btn.add_css_class("flat")
        clear_btn.add_css_class("caption")
        clear_btn.connect("clicked", self._on_clear_all)
        header.append(clear_btn)

        box.append(header)

        # Separator
        box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Notification list (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.add_css_class("boxed-list")
        self._listbox.set_placeholder(self._build_empty_state())

        scroll.set_child(self._listbox)
        box.append(scroll)

        return box

    def _build_empty_state(self) -> "Gtk.Widget":
        """Build empty state placeholder."""
        label = Gtk.Label(label="Nenhuma notificação")
        label.add_css_class("dim-label")
        label.set_margin_top(32)
        label.set_margin_bottom(32)
        return label

    def _build_notification_row(self, notif) -> "Gtk.ListBoxRow":
        """Build a single notification row."""
        row = Gtk.ListBoxRow()
        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row_box.set_margin_start(12)
        row_box.set_margin_end(12)
        row_box.set_margin_top(8)
        row_box.set_margin_bottom(8)

        # Top line: icon + title + dismiss
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        icon = Gtk.Label(label=notif.icon or "ℹ️")
        top.append(icon)

        title = Gtk.Label(label=notif.title)
        title.set_xalign(0)
        title.set_hexpand(True)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.add_css_class("heading")
        top.append(title)

        dismiss_btn = Gtk.Button()
        dismiss_btn.set_icon_name("window-close-symbolic")
        dismiss_btn.add_css_class("flat")
        dismiss_btn.add_css_class("circular")
        dismiss_btn.connect("clicked", lambda b: self._dismiss(notif.id))
        top.append(dismiss_btn)

        row_box.append(top)

        # Body (if present)
        if notif.body:
            body = Gtk.Label(label=notif.body)
            body.set_xalign(0)
            body.set_wrap(True)
            body.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            body.add_css_class("dim-label")
            body.add_css_class("caption")
            row_box.append(body)

        # Progress bar (if progress type)
        if notif.progress is not None:
            progress = Gtk.ProgressBar()
            progress.set_fraction(notif.progress)
            progress.set_margin_top(4)
            row_box.append(progress)

        # Action buttons (if present)
        if notif.actions:
            actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            actions_box.set_margin_top(4)
            for action in notif.actions:
                btn = Gtk.Button(label=action.label)
                btn.add_css_class("pill")
                btn.add_css_class("suggested-action" if action == notif.actions[0] else "flat")
                btn.connect("clicked", lambda b, a=action: self._on_action(a))
                actions_box.append(btn)
            row_box.append(actions_box)

        row.set_child(row_box)
        return row

    def _on_notification(self, notif) -> None:
        """Handle new notification from bus (called from any thread)."""
        if GLib:
            GLib.idle_add(self._add_notification_row, notif)

    def _add_notification_row(self, notif) -> None:
        """Add notification row to the list (must be called on main thread)."""
        if notif.id in self._rows:
            return  # Already displayed

        row = self._build_notification_row(notif)
        self._listbox.prepend(row)
        self._rows[notif.id] = row
        self._update_badge()

    def _dismiss(self, notif_id: str) -> None:
        """Dismiss a notification."""
        self._bus.dismiss(notif_id)
        row = self._rows.pop(notif_id, None)
        if row:
            self._listbox.remove(row)
        self._update_badge()

    def _on_action(self, action) -> None:
        """Handle action button click."""
        logger.info("Notification action: %s (params=%s)", action.callback_id, action.params)
        # Actions are handled by the bridge/planner via callback_id
        # For now, just dismiss the notification
        # TODO: route action.callback_id to appropriate handler

    def _on_clear_all(self, btn) -> None:
        """Clear all notifications."""
        self._bus.clear_all()
        while True:
            row = self._listbox.get_row_at_index(0)
            if row is None:
                break
            self._listbox.remove(row)
        self._rows.clear()
        self._update_badge()

    def _update_badge(self) -> None:
        """Update the unread count badge."""
        count = self._bus.get_unread_count()
        if count > 0:
            self._badge.set_label(str(count))
            self._badge.set_visible(True)
        else:
            self._badge.set_visible(False)

    def _load_history(self) -> None:
        """Load existing notification history."""
        for notif in self._bus.get_history(limit=20):
            self._add_notification_row(notif)
