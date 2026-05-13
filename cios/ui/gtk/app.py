"""CIOS GTK4 Main Application — Wayland-native desktop interface.

Intent-first, single-surface design:
- Prompt at bottom (multiline input)
- Results appear above and persist
- State ring communicates system status
- No X11 dependency
"""

import logging
import sys
import threading
import traceback

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from cios.core.bridge import CIOSBridge  # noqa: E402
from cios.ui.gtk.splash import signal_splash_done, update_splash_progress  # noqa: E402
from cios.ui.theme import (  # noqa: E402
    ACCENT,
    ACCENT_LT,
    BG,
    BG_CARD,
    BG_INPUT,
    BORDER,
    FG,
    FG_DIM,
    FG_SEC,
)

logger = logging.getLogger(__name__)


class CIOSApplication(Gtk.Application):
    """Main CIOS GTK4 application."""

    def __init__(self):
        super().__init__(application_id="com.cios.desktop")
        self._bridge = None
        self._busy = False
        self._win = None
        self._stack = None

    def do_activate(self):
        from cios.ui.gtk.onboarding import needs_onboarding

        # Keep app alive even if GTK thinks there's no work
        self.hold()

        self._win = Gtk.ApplicationWindow(application=self)
        self._win.set_title("CIOS")
        self._win.fullscreen()

        # Apply CSS
        self._apply_css(self._win)

        # Use a stack to switch between onboarding and main UI
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(300)
        self._win.set_child(self._stack)

        # Build main UI page
        main_page = self._build_main_ui()
        self._stack.add_named(main_page, "main")

        # Check if onboarding needed
        if needs_onboarding():
            onboarding_page = self._build_onboarding()
            self._stack.add_named(onboarding_page, "onboarding")
            self._stack.set_visible_child_name("onboarding")
        else:
            self._stack.set_visible_child_name("main")
            self._start_bridge()

        # Start IPC listener early (dismisses compositor splash on connect)
        from cios.ui.gtk.ipc_listener import IPCListener

        self._ipc_listener = IPCListener(
            on_hotkey=self._on_hotkey_triggered,
            on_logout=self._on_logout_requested,
        )
        self._ipc_listener.start()

        self._win.present()

    def _build_main_ui(self):
        """Build the main CIOS interface with topbar + sidebar + prompt."""
        from cios.ui.gtk.hotkey_overlay import HotkeyOverlay
        from cios.ui.gtk.sidebar import Sidebar
        from cios.ui.gtk.thread_panel import ThreadPanel
        from cios.ui.gtk.topbar import Topbar

        # Root: overlay for hotkey popup
        root_overlay = Gtk.Overlay()

        # Main vertical layout
        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root_overlay.set_child(outer_box)

        # ── Topbar ──
        self._topbar = Topbar()
        outer_box.append(self._topbar)

        # ── Content area (horizontal: center + sidebar) ──
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        content_box.set_vexpand(True)
        outer_box.append(content_box)

        # Center column
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center_box.set_hexpand(True)
        content_box.append(center_box)

        # Feed area (scrollable)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        center_box.append(scroll)

        self._feed_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._feed_box.set_margin_start(48)
        self._feed_box.set_margin_end(48)
        self._feed_box.set_margin_top(32)
        self._feed_box.set_margin_bottom(16)
        scroll.set_child(self._feed_box)

        # Greeting
        greeting = Gtk.Label(label="O que você quer fazer?")
        greeting.add_css_class("greeting")
        greeting.set_halign(Gtk.Align.START)
        self._feed_box.append(greeting)
        self._greeting = greeting

        # Result area
        self._result_label = Gtk.Label(label="")
        self._result_label.set_wrap(True)
        self._result_label.set_halign(Gtk.Align.START)
        self._result_label.add_css_class("result")
        self._result_label.set_visible(False)
        self._feed_box.append(self._result_label)

        # ── Prompt area (bottom) ──
        prompt_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        prompt_box.set_margin_start(48)
        prompt_box.set_margin_end(48)
        prompt_box.set_margin_top(8)
        prompt_box.set_margin_bottom(12)
        prompt_box.add_css_class("prompt-area")
        center_box.append(prompt_box)

        # Input field
        self._input = Gtk.Entry()
        self._input.set_placeholder_text("Fale o que quer fazer…")
        self._input.set_hexpand(True)
        self._input.add_css_class("prompt-input")
        self._input.connect("activate", self._on_submit)
        prompt_box.append(self._input)

        # Send button
        send_btn = Gtk.Button(label="→")
        send_btn.add_css_class("send-btn")
        send_btn.connect("clicked", self._on_submit)
        prompt_box.append(send_btn)

        # ── Thread panel (below prompt) ──
        self._thread_panel = ThreadPanel()
        center_box.append(self._thread_panel)

        # ── Sidebar (right) ──
        self._sidebar = Sidebar(on_suggestion=self._on_suggestion)
        content_box.append(self._sidebar)

        # ── Hotkey overlay (floating) ──
        self._hotkey_overlay = HotkeyOverlay(on_submit=self._on_hotkey_submit)
        root_overlay.add_overlay(self._hotkey_overlay)

        return root_overlay

    def _build_onboarding(self):
        """Build onboarding page within the main app."""
        from cios.ui.gtk.onboarding import mark_onboarding_done

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(40)
        box.set_margin_end(40)

        title = Gtk.Label(label="Bem-vindo ao CIOS")
        title.add_css_class("greeting")
        box.append(title)

        sub = Gtk.Label(
            label="Seu computador agora entende intenção.\nFale o que quer fazer. O sistema executa."
        )
        sub.add_css_class("result")
        sub.set_justify(2)
        box.append(sub)

        examples = Gtk.Label(
            label='💡 "quero trabalhar no projeto X"\n'
            '📁 "organiza meus downloads"\n'
            '🔌 "conecta no wifi"\n'
            '📊 "meu computador está lento"\n'
            '🔊 "aumenta o volume"'
        )
        examples.add_css_class("result")
        examples.set_halign(Gtk.Align.START)
        box.append(examples)

        # AI setup hint
        ai_hint = Gtk.Label(label="💡 Para IA local, execute depois: sudo cios-setup-ai")
        ai_hint.add_css_class("result")
        ai_hint.set_halign(Gtk.Align.START)
        ai_hint.set_margin_top(16)
        box.append(ai_hint)

        btn = Gtk.Button(label="Iniciar CIOS")
        btn.add_css_class("send-btn")
        btn.set_halign(Gtk.Align.CENTER)

        def on_start(_):
            mark_onboarding_done()
            self._stack.set_visible_child_name("main")
            self._start_bridge()

        btn.connect("clicked", on_start)
        box.append(btn)

        return box

    def _start_bridge(self):
        """Initialize bridge in background thread."""

        def init_bridge():
            try:
                self._bridge = CIOSBridge(on_progress=update_splash_progress)
                GLib.idle_add(signal_splash_done)
                GLib.idle_add(self._on_bridge_ready)
            except Exception as e:
                logger.exception("Failed to initialize bridge")
                GLib.idle_add(signal_splash_done)

        threading.Thread(target=init_bridge, daemon=True).start()

        threading.Thread(target=init_bridge, daemon=True).start()

    def _on_bridge_ready(self):
        """Called when bridge is initialized."""
        self._input.set_sensitive(True)
        self._input.grab_focus()
        self._thread_panel.set_bridge(self._bridge)

    def _on_suggestion(self, cmd: str):
        """Handle suggestion chip click."""
        self._input.set_text(cmd)
        self._on_submit()

    def _on_hotkey_submit(self, text: str):
        """Handle hotkey overlay submission."""
        self._input.set_text(text)
        self._on_submit()

    def _on_hotkey_triggered(self):
        """Called when Ctrl+Space is pressed (via compositor IPC)."""
        if self._hotkey_overlay.get_visible():
            self._hotkey_overlay.hide_overlay()
        else:
            self._hotkey_overlay.show_overlay()

    def _on_logout_requested(self):
        """Called when Super+Q is pressed (via compositor IPC)."""
        self.quit()

    def _on_submit(self, *args):
        """Handle command submission."""
        text = self._input.get_text().strip()
        if not text or self._busy:
            return

        self._busy = True
        self._input.set_text("")
        self._input.set_sensitive(False)

        # Hide greeting, show processing
        self._greeting.set_visible(False)
        self._result_label.set_label("⟳ Processando…")
        self._result_label.set_visible(True)
        self._result_label.add_css_class("processing")

        # Execute in background
        def execute():
            try:
                if self._bridge:
                    data = self._bridge.execute_command(text, confirmed=False)
                    result = data.get("result", "Concluído.")
                    status = data.get("status", "success")

                    # Check if result contains gallery data
                    gallery = data.get("gallery")
                    if gallery:
                        GLib.idle_add(self._show_gallery, gallery)
                        GLib.idle_add(self._finish_execution)
                        return
                else:
                    result = "Sistema ainda inicializando…"
                    status = "error"
            except Exception as e:
                result = f"Erro: {e}"
                status = "error"

            GLib.idle_add(self._show_result, result, status)

        threading.Thread(target=execute, daemon=True).start()

    def _finish_execution(self):
        """Reset UI state after execution (no result to show)."""
        self._input.set_sensitive(True)
        self._input.grab_focus()
        self._busy = False
        self._thread_panel.refresh()

    def _show_result(self, result: str, status: str):
        """Display execution result."""
        self._result_label.remove_css_class("processing")
        self._result_label.set_label(result)
        self._result_label.set_visible(True)

        if status == "error":
            self._result_label.add_css_class("error-result")
        else:
            self._result_label.remove_css_class("error-result")

        self._input.set_sensitive(True)
        self._input.grab_focus()
        self._busy = False

        # Refresh thread panel
        self._thread_panel.refresh()

    def _show_gallery(self, gallery_data: dict):
        """Display gallery grid in the feed area."""
        from cios.ui.gtk.gallery import GalleryComponent

        # Remove previous gallery if any
        if hasattr(self, "_active_gallery") and self._active_gallery:
            self._feed_box.remove(self._active_gallery)

        self._active_gallery = GalleryComponent(
            gallery_data=gallery_data,
            on_image_click=self._open_image_viewer,
        )
        self._feed_box.append(self._active_gallery)
        self._greeting.set_visible(False)
        self._result_label.set_visible(False)

    def _open_image_viewer(self, files: list, index: int):
        """Open full-size image viewer."""
        from cios.ui.gtk.image_viewer import ImageViewer

        # Replace main content with viewer
        if hasattr(self, "_active_viewer") and self._active_viewer:
            return  # Already open

        self._active_viewer = ImageViewer(
            files=files,
            start_index=index,
            on_close=self._close_image_viewer,
        )
        self._stack.add_named(self._active_viewer, "viewer")
        self._stack.set_visible_child_name("viewer")

    def _close_image_viewer(self):
        """Close image viewer and return to main."""
        if hasattr(self, "_active_viewer") and self._active_viewer:
            self._stack.remove(self._active_viewer)
            self._active_viewer = None
        self._stack.set_visible_child_name("main")

    def _send_ipc_ready(self):
        """Send 'ready' command to compositor via IPC socket to dismiss splash."""
        import json
        import os
        import socket

        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        sock_path = os.path.join(runtime_dir, "cios-shell.sock")

        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(sock_path)
            msg = json.dumps({"v": 1, "id": "ready-1", "command": "ready"}) + "\n"
            s.sendall(msg.encode())
            # Wait for compositor to process before closing
            s.settimeout(2.0)
            try:
                s.recv(1024)
            except (TimeoutError, OSError):
                pass
            s.close()
            logger.info("Sent 'ready' to compositor")
        except Exception as e:
            logger.warning("Failed to send 'ready' to compositor: %s", e)

    def _apply_css(self, win):
        """Apply application-wide CSS."""
        from cios.ui.gtk.gallery import GalleryComponent as GalleryCSS
        from cios.ui.gtk.hotkey_overlay import HotkeyOverlay
        from cios.ui.gtk.image_viewer import ImageViewer as ViewerCSS
        from cios.ui.gtk.sidebar import Sidebar
        from cios.ui.gtk.thread_panel import ThreadPanel
        from cios.ui.gtk.topbar import Topbar

        css = Gtk.CssProvider()
        css.load_from_string(
            f"""
            window {{
                background-color: {BG};
            }}
            .greeting {{
                color: {FG};
                font-size: 24px;
                font-weight: bold;
                margin-bottom: 16px;
            }}
            .result {{
                color: {FG_SEC};
                font-size: 14px;
                margin-top: 8px;
            }}
            .processing {{
                color: {FG_DIM};
                font-style: italic;
            }}
            .error-result {{
                color: #ef4444;
            }}
            .prompt-area {{
                background-color: {BG_CARD};
                border-radius: 12px;
                padding: 12px 16px;
            }}
            .prompt-input {{
                background: {BG_INPUT};
                color: {FG};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 16px;
                min-height: 20px;
                box-shadow: none;
            }}
            .prompt-input:focus {{
                border-color: {ACCENT_LT};
            }}
            .send-btn {{
                background: {ACCENT};
                color: white;
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 16px;
                font-weight: bold;
                border: none;
                box-shadow: none;
                text-shadow: none;
            }}
            .send-btn:hover {{
                background: {ACCENT_LT};
            }}
            """
            + Topbar.get_css()
            + Sidebar.get_css()
            + ThreadPanel.get_css()
            + HotkeyOverlay.get_css()
            + GalleryCSS.get_css()
            + ViewerCSS.get_css()
        )
        Gtk.StyleContext.add_provider_for_display(
            win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def run_gui():
    """Entry point for the GTK4 GUI."""

    # Install exception hook to log crashes
    def _exception_hook(exc_type, exc_value, exc_tb):
        logger.error(
            "Unhandled exception: %s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _exception_hook

    app = CIOSApplication()
    app.run(None)
