"""CIOS Lock Screen — Apple-style clock with password unlock.

Shows as an overlay inside the main window (not a separate window).
- Large centered clock (HH:MM)
- Date below
- Password field appears on click/keypress
- Unlocks on correct password
"""

import os
import subprocess
import time

from gi.repository import GLib, Gtk


def show_lock_screen(parent_window):
    """Show the lock screen as an overlay inside the main window."""
    # Find the root overlay
    app = parent_window.get_application()
    if hasattr(app, "_root_overlay"):
        overlay = app._root_overlay
    else:
        # Fallback: try to get from window child
        overlay = parent_window.get_child()
        if not isinstance(overlay, Gtk.Overlay):
            return

    lock = LockScreenOverlay(overlay)
    overlay.add_overlay(lock)
    lock.grab_focus()


class LockScreenOverlay(Gtk.Box):
    """Lock screen as overlay widget inside the main window."""

    def __init__(self, root_overlay):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._root_overlay = root_overlay
        self._unlocked = False

        # Fill entire screen
        self.set_valign(Gtk.Align.FILL)
        self.set_halign(Gtk.Align.FILL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self.add_css_class("lock-bg")

        # Center content
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        center.set_halign(Gtk.Align.CENTER)
        center.set_valign(Gtk.Align.CENTER)
        center.set_vexpand(True)
        self.append(center)

        # Clock (large)
        self._clock = Gtk.Label(label="00:00")
        self._clock.add_css_class("lock-clock")
        center.append(self._clock)

        # Date
        self._date = Gtk.Label(label="")
        self._date.add_css_class("lock-date")
        center.append(self._date)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_size_request(-1, 40)
        center.append(spacer)

        # Password area (hidden initially)
        self._pass_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._pass_box.set_halign(Gtk.Align.CENTER)
        self._pass_box.set_visible(False)
        center.append(self._pass_box)

        # Username
        username = os.environ.get("USER", "user")
        user_label = Gtk.Label(label=username)
        user_label.add_css_class("lock-user")
        self._pass_box.append(user_label)

        # Password entry
        self._password = Gtk.PasswordEntry()
        self._password.props.placeholder_text = "Senha"
        self._password.set_show_peek_icon(True)
        self._password.add_css_class("lock-password")
        self._password.set_size_request(250, -1)
        self._password.connect("activate", self._on_unlock)
        self._pass_box.append(self._password)

        # Error label
        self._error = Gtk.Label(label="")
        self._error.add_css_class("lock-error")
        self._error.set_visible(False)
        self._pass_box.append(self._error)

        # Hint
        self._hint = Gtk.Label(label="Pressione qualquer tecla para desbloquear")
        self._hint.add_css_class("lock-hint")
        center.append(self._hint)

        # Key press to reveal password field
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        # Click to reveal password field
        click_ctrl = Gtk.GestureClick()
        click_ctrl.connect("released", self._on_click)
        self.add_controller(click_ctrl)

        # Update clock
        self._update_clock()
        GLib.timeout_add(1000, self._update_clock)

        # Make focusable
        self.set_focusable(True)
        self.set_can_focus(True)

    def _on_key(self, ctrl, keyval, keycode, state):
        """Any key press reveals the password field."""
        if not self._pass_box.get_visible():
            self._pass_box.set_visible(True)
            self._hint.set_visible(False)
            self._password.grab_focus()
            return True
        return False

    def _on_click(self, gesture, n_press, x, y):
        """Click reveals the password field."""
        if not self._pass_box.get_visible():
            self._pass_box.set_visible(True)
            self._hint.set_visible(False)
            self._password.grab_focus()

    def _on_unlock(self, entry):
        """Attempt to unlock with entered password."""
        password = entry.get_text()
        if not password:
            return

        username = os.environ.get("USER", "user")

        try:
            result = subprocess.run(
                ["su", "-c", "true", username],
                input=password + "\n",
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                self._unlock()
            else:
                self._show_error("Senha incorreta")
                entry.set_text("")
        except (subprocess.TimeoutExpired, OSError):
            self._show_error("Erro de autenticação")
            entry.set_text("")

    def _show_error(self, msg):
        """Show error message."""
        self._error.set_label(msg)
        self._error.set_visible(True)
        GLib.timeout_add(3000, lambda: self._error.set_visible(False) or False)

    def _unlock(self):
        """Remove lock screen overlay and restore focus to prompt."""
        self._unlocked = True
        self._root_overlay.remove_overlay(self)
        # Restore focus to the main input
        app = self._root_overlay.get_root()
        if app and hasattr(app, "get_application"):
            cios_app = app.get_application()
            if hasattr(cios_app, "_input"):
                cios_app._input.grab_focus()

    def _update_clock(self):
        """Update the clock display."""
        if self._unlocked:
            return False

        now = time.localtime()
        self._clock.set_label(time.strftime("%H:%M", now))

        months_pt = [
            "",
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ]
        days_pt = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        day_name = days_pt[now.tm_wday]
        month_name = months_pt[now.tm_mon]
        self._date.set_label(f"{day_name}, {now.tm_mday} de {month_name}")

        return True
