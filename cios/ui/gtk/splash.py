"""CIOS GTK4 Splash — Wayland-native loading screen.

Displays a minimal, branded loading screen:
- Appears instantly (before heavy imports)
- Shows real boot progress stages
- Matches the main GUI color scheme
- Closes when main GUI signals ready

Uses the same file-based protocol as the Tkinter version:
- Progress: ~/.cios/.splash_progress ("stage|current|total")
- Done: ~/.cios/.splash_done (file exists = close)
"""

import math
import os
import signal
import sys

_READY_FILE = os.path.expanduser("~/.cios/.splash_done")
_PROGRESS_FILE = os.path.expanduser("~/.cios/.splash_progress")


def show_splash() -> None:
    """Show GTK4 splash screen. Blocks until signaled or timeout."""
    # Clean up stale files
    for f in (_READY_FILE, _PROGRESS_FILE):
        try:
            os.unlink(f)
        except OSError:
            pass

    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import GLib, Gtk
    except (ImportError, ValueError):
        # GTK4 not available, wait for signal
        _wait_for_signal()
        return

    from cios.ui.theme import ACCENT_LT, BG, FG_DIM

    app = Gtk.Application(application_id="com.cios.splash")

    # State
    state = {"phase": 0.0, "progress": 0.0, "stage": "Iniciando…", "total": 10}

    def on_activate(app):
        win = Gtk.ApplicationWindow(application=app)
        win.set_title("CIOS")
        win.set_decorated(False)
        win.set_default_size(4096, 4096)

        # Main container
        overlay = Gtk.Overlay()
        win.set_child(overlay)

        # Background
        bg_area = Gtk.DrawingArea()
        bg_area.set_draw_func(_draw_background, None)
        overlay.set_child(bg_area)

        # Center content box
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        center_box.set_halign(Gtk.Align.CENTER)
        center_box.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(center_box)

        # State ring (Cairo drawing)
        ring_area = Gtk.DrawingArea()
        ring_area.set_content_width(72)
        ring_area.set_content_height(72)
        ring_area.set_draw_func(_draw_ring, state)
        ring_area.set_halign(Gtk.Align.CENTER)
        center_box.append(ring_area)

        # Stage label
        stage_label = Gtk.Label(label=state["stage"])
        stage_label.add_css_class("splash-stage")
        stage_label.set_halign(Gtk.Align.CENTER)
        center_box.append(stage_label)

        # Progress bar
        progress_bar = Gtk.ProgressBar()
        progress_bar.set_fraction(0.0)
        progress_bar.add_css_class("splash-progress")
        progress_bar.set_size_request(300, -1)
        progress_bar.set_halign(Gtk.Align.CENTER)
        center_box.append(progress_bar)

        # Apply CSS
        css = Gtk.CssProvider()
        css.load_from_string(f"""
            window {{
                background-color: {BG};
            }}
            .splash-stage {{
                color: {FG_DIM};
                font-size: 13px;
            }}
            .splash-progress {{
                min-height: 3px;
                border-radius: 2px;
            }}
            .splash-progress trough {{
                background-color: #1f2937;
                min-height: 3px;
            }}
            .splash-progress progress {{
                background-color: {ACCENT_LT};
                min-height: 3px;
                border-radius: 2px;
            }}
        """)
        Gtk.StyleContext.add_provider_for_display(
            win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Animation timer (ring rotation)
        def animate_ring():
            state["phase"] += 0.08
            ring_area.queue_draw()
            return True  # keep running

        GLib.timeout_add(60, animate_ring)

        # Poll progress file
        def poll_progress():
            # Check done
            if os.path.exists(_READY_FILE):
                app.quit()
                return False

            # Read progress
            try:
                with open(_PROGRESS_FILE) as f:
                    parts = f.read().strip().split("|")
                    if len(parts) >= 3:
                        state["stage"] = parts[0]
                        current = int(parts[1])
                        total = int(parts[2])
                        state["progress"] = current / max(total, 1)
                        state["total"] = total
                        stage_label.set_label(state["stage"])
                        progress_bar.set_fraction(state["progress"])
            except (OSError, ValueError):
                pass

            return True  # keep polling

        GLib.timeout_add(80, poll_progress)

        # Timeout (10s max)
        GLib.timeout_add(10000, lambda: app.quit() or False)

        win.present()

    def _draw_background(area, cr, width, height, data):
        """Draw solid dark background."""
        cr.set_source_rgb(*_hex_to_rgb(BG))
        cr.paint()

    def _draw_ring(area, cr, width, height, data):
        """Draw animated state ring."""
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 6
        phase = state["phase"]

        # Ring background
        cr.set_line_width(3)
        cr.set_source_rgba(*_hex_to_rgb(ACCENT_LT), 0.3)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        # Animated arc
        start = phase
        end = phase + math.pi * 1.2
        cr.set_source_rgba(*_hex_to_rgb(ACCENT_LT), 1.0)
        cr.arc(cx, cy, radius, start, end)
        cr.stroke()

        # Center symbol
        cr.set_source_rgba(*_hex_to_rgb(ACCENT_LT), 0.8)
        cr.select_font_face("sans-serif", 0, 0)
        cr.set_font_size(20)
        extents = cr.text_extents("✦")
        cr.move_to(cx - extents.width / 2, cy + extents.height / 2)
        cr.show_text("✦")

    app.connect("activate", on_activate)
    app.run(None)


def update_splash_progress(stage: str, current: int, total: int) -> None:
    """Write progress for splash to read."""
    try:
        os.makedirs(os.path.dirname(_PROGRESS_FILE), exist_ok=True)
        with open(_PROGRESS_FILE, "w") as f:
            f.write(f"{stage}|{current}|{total}")
    except OSError:
        pass


def signal_splash_done() -> None:
    """Signal splash to close."""
    try:
        os.makedirs(os.path.dirname(_READY_FILE), exist_ok=True)
        with open(_READY_FILE, "w") as f:
            f.write("done")
    except OSError:
        pass


def _hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to (r, g, b) floats 0-1."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def _wait_for_signal():
    """Fallback: wait for SIGTERM or splash_done file."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    import time

    for _ in range(100):  # 10s max
        if os.path.exists(_READY_FILE):
            return
        time.sleep(0.1)


if __name__ == "__main__":
    show_splash()
