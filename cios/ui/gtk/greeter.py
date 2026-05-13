"""CIOS Greeter — GTK4 Wayland-native login screen.

Visual design:
- Dark background (#0b0f14) with red gradient corners
  (top-right and bottom-left)
- CIOS logo centered above login fields
- Username + password fields
- Login button with accent color

Communicates with greetd via its IPC protocol (JSON over Unix socket).
Launched by greetd as the greeter session.
"""

import json
import os
import socket
import struct
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

# ═══════════════════════════════════════════════════════════════
#  greetd IPC protocol
# ═══════════════════════════════════════════════════════════════

GREETD_SOCK = os.environ.get("GREETD_SOCK", "")


def _greetd_send(msg: dict) -> dict:
    """Send a message to greetd and receive response."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(GREETD_SOCK)

    payload = json.dumps(msg).encode()
    # greetd protocol: 4-byte length prefix (little-endian) + JSON
    s.sendall(struct.pack("<I", len(payload)) + payload)

    # Read response
    length_data = s.recv(4)
    if len(length_data) < 4:
        s.close()
        return {"type": "error", "error_type": "io", "description": "no response"}
    length = struct.unpack("<I", length_data)[0]
    response_data = s.recv(length)
    s.close()

    return json.loads(response_data)


def _greetd_create_session(username: str) -> dict:
    """Create a greetd session for the given username."""
    return _greetd_send({"type": "create_session", "username": username})


def _greetd_post_auth(password: str) -> dict:
    """Post authentication response (password)."""
    return _greetd_send({"type": "post_auth_message_response", "response": password})


def _greetd_start_session(cmd: list) -> dict:
    """Start the authenticated session with the given command."""
    return _greetd_send({"type": "start_session", "cmd": cmd})


def _greetd_cancel_session() -> dict:
    """Cancel the current session."""
    return _greetd_send({"type": "cancel_session"})


# ═══════════════════════════════════════════════════════════════
#  GTK4 Greeter Application
# ═══════════════════════════════════════════════════════════════

BG = "#0b0f14"
RED_ACCENT = "#dc2626"
RED_GLOW = "#991b1b"
FG = "#e5e7eb"
FG_DIM = "#6b7280"
ACCENT = "#7c3aed"
ACCENT_LT = "#a78bfa"
BG_INPUT = "#161b24"
BORDER = "#1f2937"


class CIOSGreeter(Gtk.Application):
    """CIOS login greeter."""

    def __init__(self):
        super().__init__(application_id="com.cios.greeter")
        self._username_entry = None
        self._password_entry = None
        self._error_label = None
        self._login_btn = None

    def do_activate(self):
        win = Gtk.ApplicationWindow(application=self)
        win.set_title("CIOS")
        win.set_decorated(False)
        win.set_default_size(4096, 4096)

        # Apply CSS
        self._apply_css(win)

        # Dismiss compositor splash overlay
        self._send_compositor_ready()

        # Main overlay (for gradient corners)
        overlay = Gtk.Overlay()
        win.set_child(overlay)

        # Background with gradient corners (Cairo)
        bg_area = Gtk.DrawingArea()
        bg_area.set_draw_func(self._draw_background, None)
        overlay.set_child(bg_area)

        # Center login box
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        center_box.set_halign(Gtk.Align.CENTER)
        center_box.set_valign(Gtk.Align.CENTER)
        center_box.set_size_request(360, -1)
        overlay.add_overlay(center_box)

        # Logo (PNG if available, fallback to text)
        logo_path = "/usr/share/pixmaps/cios-logo.png"
        if os.path.isfile(logo_path):
            logo = Gtk.Image.new_from_file(logo_path)
            logo.set_pixel_size(120)
            logo.set_halign(Gtk.Align.CENTER)
            center_box.append(logo)
        else:
            logo = Gtk.Label(label="CIOS")
            logo.add_css_class("logo")
            center_box.append(logo)

        subtitle = Gtk.Label(label="Intent-first computing")
        subtitle.add_css_class("subtitle")
        center_box.append(subtitle)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_size_request(-1, 32)
        center_box.append(spacer)

        # Username field
        self._username_entry = Gtk.Entry()
        self._username_entry.set_placeholder_text("Usuário")
        self._username_entry.add_css_class("login-input")
        self._username_entry.connect("activate", self._on_username_activate)
        center_box.append(self._username_entry)

        # Password field
        self._password_entry = Gtk.Entry()
        self._password_entry.set_placeholder_text("Senha")
        self._password_entry.set_visibility(False)
        self._password_entry.add_css_class("login-input")
        self._password_entry.connect("activate", self._on_login)
        center_box.append(self._password_entry)

        # Error label (hidden by default)
        self._error_label = Gtk.Label(label="")
        self._error_label.add_css_class("error-msg")
        self._error_label.set_visible(False)
        center_box.append(self._error_label)

        # Login button
        self._login_btn = Gtk.Button(label="Entrar")
        self._login_btn.add_css_class("login-btn")
        self._login_btn.connect("clicked", self._on_login)
        center_box.append(self._login_btn)

        # Focus username
        self._username_entry.grab_focus()

        win.present()

    def _on_username_activate(self, entry):
        """Tab to password when Enter pressed on username."""
        self._password_entry.grab_focus()

    def _on_login(self, *args):
        """Attempt login via greetd."""
        username = self._username_entry.get_text().strip()
        password = self._password_entry.get_text()

        if not username:
            self._show_error("Digite o usuário")
            return

        self._login_btn.set_sensitive(False)
        self._error_label.set_visible(False)

        # Authenticate via greetd
        try:
            # Step 1: Create session
            resp = _greetd_create_session(username)

            if resp.get("type") == "error":
                self._show_error(resp.get("description", "Erro de autenticação"))
                self._login_btn.set_sensitive(True)
                return

            # Step 2: Send password (if auth_message received)
            if resp.get("type") == "auth_message":
                resp = _greetd_post_auth(password)

                if resp.get("type") == "error":
                    self._show_error("Usuário ou senha incorretos")
                    self._password_entry.set_text("")
                    self._password_entry.grab_focus()
                    self._login_btn.set_sensitive(True)
                    return

            # Step 3: Start session
            if resp.get("type") == "success":
                resp = _greetd_start_session(["/usr/local/bin/cios-session"])
                if resp.get("type") == "success":
                    # Session started, greeter should exit
                    self.quit()
                    return
                else:
                    self._show_error("Falha ao iniciar sessão")
                    self._login_btn.set_sensitive(True)

        except Exception as e:
            self._show_error(f"Erro: {e}")
            self._login_btn.set_sensitive(True)

    def _show_error(self, msg: str):
        """Show error message."""
        self._error_label.set_label(msg)
        self._error_label.set_visible(True)

    def _send_compositor_ready(self):
        """Send 'ready' to compositor to dismiss splash overlay."""
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        sock_path = os.path.join(runtime_dir, "cios-shell.sock")
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(sock_path)
            msg = json.dumps({"v": 1, "id": "ready-1", "command": "ready"}) + "\n"
            s.sendall(msg.encode())
            s.settimeout(2.0)
            try:
                s.recv(1024)
            except (TimeoutError, OSError):
                pass
            s.close()
        except Exception:
            pass

    def _draw_background(self, area, cr, width, height, data):
        """Draw background with red gradient corners."""
        # Solid dark background
        cr.set_source_rgb(*_hex_to_rgb(BG))
        cr.paint()

        # Top-right red gradient (radial)
        pattern = _create_radial_gradient(
            width,
            0,  # center at top-right corner
            0,
            width * 0.6,  # radius
            RED_ACCENT,
            BG,
        )
        cr.set_source(pattern)
        cr.paint()

        # Bottom-left red gradient (radial)
        pattern = _create_radial_gradient(
            0,
            height,  # center at bottom-left corner
            0,
            height * 0.6,  # radius
            RED_ACCENT,
            BG,
        )
        cr.set_source(pattern)
        cr.paint()

    def _apply_css(self, win):
        """Apply greeter CSS."""
        css = Gtk.CssProvider()
        css.load_from_string(f"""
            window {{
                background-color: {BG};
            }}
            * {{
                -gtk-icon-shadow: none;
                text-shadow: none;
            }}
            .logo {{
                color: {FG};
                font-size: 48px;
                font-weight: bold;
                letter-spacing: 8px;
            }}
            .subtitle {{
                color: {FG_DIM};
                font-size: 13px;
                letter-spacing: 2px;
            }}
            .login-input {{
                background: {BG_INPUT};
                color: {FG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 14px 18px;
                font-size: 15px;
                min-height: 20px;
                box-shadow: none;
            }}
            .login-input:focus {{
                border-color: {ACCENT_LT};
                outline: none;
            }}
            .login-btn {{
                background: {ACCENT};
                color: white;
                border-radius: 8px;
                padding: 14px 32px;
                font-size: 15px;
                font-weight: bold;
                margin-top: 8px;
                border: none;
                box-shadow: none;
                text-shadow: none;
                min-width: 200px;
            }}
            .login-btn:hover {{
                background: {ACCENT_LT};
                color: white;
            }}
            .error-msg {{
                color: {RED_ACCENT};
                font-size: 12px;
            }}
        """)
        Gtk.StyleContext.add_provider_for_display(
            win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def _hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex to (r, g, b) floats 0-1."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _create_radial_gradient(cx, cy, inner_r, outer_r, color_inner, color_outer):
    """Create a Cairo radial gradient pattern."""
    import cairo

    pattern = cairo.RadialGradient(cx, cy, inner_r, cx, cy, outer_r)
    r, g, b = _hex_to_rgb(color_inner)
    pattern.add_color_stop_rgba(0, r, g, b, 0.15)
    r, g, b = _hex_to_rgb(color_outer)
    pattern.add_color_stop_rgba(1, r, g, b, 0.0)
    return pattern


def run_greeter():
    """Entry point for the CIOS greeter."""
    if not GREETD_SOCK:
        print("ERROR: GREETD_SOCK not set. Must be launched by greetd.", file=sys.stderr)
        sys.exit(1)

    app = CIOSGreeter()
    app.run(None)


if __name__ == "__main__":
    run_greeter()
