"""CIOS Lock Screen — Apple-style clock with password unlock.

Shows:
- Large centered clock (HH:MM)
- Date below
- Password field appears on click/keypress
- Unlocks on correct password (PAM auth)
"""

import os
import subprocess
import time

from gi.repository import Gdk, GLib, Gtk


def show_lock_screen(parent_window):
    """Show the lock screen overlay on top of the main window."""
    lock = LockScreen(parent_window)
    lock.show()


class LockScreen(Gtk.Window):
    """Fullscreen lock screen with clock and password unlock."""

    def __init__(self, parent):
        super().__init__()
        self.set_decorated(False)
        self.set_modal(True)
        self.set_transient_for(parent)
        self.fullscreen()

        self._parent = parent
        self._unlocked = False

        # Main container
        overlay = Gtk.Overlay()
        self.set_child(overlay)

        # Background (dark)
        bg = Gtk.Box()
        bg.add_css_class("lock-bg")
        bg.set_hexpand(True)
        bg.set_vexpand(True)
        overlay.set_child(bg)

        # Center content
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        center.set_halign(Gtk.Align.CENTER)
        center.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(center)

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

        # Password area (hidden initially, shown on interaction)
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
        self._password.set_placeholder_text("Senha")
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

        # Apply CSS
        self._apply_css()

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

        # Verify password via su
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
        """Dismiss lock screen."""
        self._unlocked = True
        self.close()

    def _update_clock(self):
        """Update the clock display."""
        if self._unlocked:
            return False

        now = time.localtime()
        self._clock.set_label(time.strftime("%H:%M", now))

        # Date: "domingo, 24 de maio"
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

    def _apply_css(self):
        """Apply lock screen CSS."""
        css = """
            .lock-bg {
                background-color: #0a0a0f;
            }
            .lock-clock {
                color: #ffffff;
                font-size: 96px;
                font-weight: 200;
                letter-spacing: -2px;
            }
            .lock-date {
                color: rgba(255,255,255,0.7);
                font-size: 18px;
                font-weight: 300;
            }
            .lock-user {
                color: rgba(255,255,255,0.8);
                font-size: 14px;
                font-weight: 500;
            }
            .lock-password {
                background-color: rgba(255,255,255,0.08);
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 8px;
                color: #ffffff;
                font-size: 14px;
                padding: 8px 16px;
                min-height: 36px;
            }
            .lock-password:focus {
                border-color: rgba(0,229,255,0.5);
                box-shadow: 0 0 8px rgba(0,229,255,0.15);
            }
            .lock-error {
                color: #ff4444;
                font-size: 12px;
            }
            .lock-hint {
                color: rgba(255,255,255,0.4);
                font-size: 12px;
                margin-top: 40px;
            }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
