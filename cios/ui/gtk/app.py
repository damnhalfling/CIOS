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
    ERROR,
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
        self._win.set_decorated(False)
        self._win.set_default_size(4096, 4096)

        # Global keyboard shortcuts (fallback when compositor IPC unavailable)
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_global_key)
        self._win.add_controller(key_ctrl)

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
            on_search=self._on_search_triggered,
        )
        self._ipc_listener.start()

        self._win.present()

    def _build_main_ui(self):
        """Build the main CIOS interface with topbar + sidebar + prompt."""
        from cios.ui.gtk.hotkey_overlay import HotkeyOverlay
        from cios.ui.gtk.search_overlay import SearchOverlay
        from cios.ui.gtk.sidebar import Sidebar
        from cios.ui.gtk.topbar import Topbar

        # Root: overlay for floating prompt + hotkey popup
        root_overlay = Gtk.Overlay()

        # Main vertical layout
        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root_overlay.set_child(outer_box)

        # ── Topbar ──
        self._topbar = Topbar()
        outer_box.append(self._topbar)

        # ── Content area (horizontal: artifact + center + sidebar) ──
        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        content_box.set_vexpand(True)
        outer_box.append(content_box)

        # ── Artifact panel (left, hidden by default) ──
        from cios.ui.gtk.artifact_panel import ARTIFACT_PANEL_CSS, ArtifactPanel

        self._artifact_panel = ArtifactPanel()
        content_box.append(self._artifact_panel)

        # Apply artifact CSS
        artifact_css = Gtk.CssProvider()
        artifact_css.load_from_data(ARTIFACT_PANEL_CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            self._win.get_display(), artifact_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Center column
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center_box.set_hexpand(True)
        content_box.append(center_box)

        # Chat feed (replaces old label-based result display)
        from cios.ui.gtk.chat_feed import CHAT_FEED_CSS, ChatFeed

        self._chat_feed = ChatFeed()
        center_box.append(self._chat_feed)

        # Apply chat feed CSS
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CHAT_FEED_CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            self._win.get_display(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Legacy references (kept for backward compat with password dialog etc.)
        self._greeting = self._chat_feed._greeting
        self._feed_box = self._chat_feed._messages_box

        # ── Sidebar (right, always rightmost) ──
        self._sidebar = Sidebar()
        content_box.append(self._sidebar)

        # ── Prompt with status line (bottom of center area, not over sidebar) ──
        prompt_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        prompt_container.set_margin_start(48)
        prompt_container.set_margin_end(16)
        prompt_container.set_margin_bottom(12)
        prompt_container.set_margin_top(8)

        # Status line (hidden by default, shown during processing)
        self._status_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._status_line.set_margin_start(16)
        self._status_line.set_margin_bottom(4)
        self._status_line.add_css_class("status-line")
        self._status_line.set_visible(False)

        self._status_dot = Gtk.Label(label="●")
        self._status_dot.add_css_class("status-dot")
        self._status_line.append(self._status_dot)

        self._status_label = Gtk.Label(label="")
        self._status_label.add_css_class("status-text")
        self._status_line.append(self._status_label)

        # Glowing separator line
        self._status_bar = Gtk.Box()
        self._status_bar.set_hexpand(True)
        self._status_bar.add_css_class("status-glow-bar")
        self._status_line.append(self._status_bar)

        prompt_container.append(self._status_line)

        # Prompt input row
        prompt_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        prompt_box.add_css_class("prompt-area")

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

        prompt_container.append(prompt_box)

        # Prompt goes at bottom of center column (respects sidebar boundary)
        center_box.append(prompt_container)

        # ── Hotkey overlay (floating) ──
        self._hotkey_overlay = HotkeyOverlay(on_submit=self._on_hotkey_submit)
        root_overlay.add_overlay(self._hotkey_overlay)

        # ── Search overlay (Ctrl+K) ──
        self._search_overlay = SearchOverlay()
        root_overlay.add_overlay(self._search_overlay)

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

    def _on_bridge_ready(self):
        """Called when bridge is initialized."""
        self._input.set_sensitive(True)
        self._input.grab_focus()
        self._sidebar.set_bridge(self._bridge)
        self._sidebar.set_artifact_panel(self._artifact_panel)
        self._search_overlay.set_bridge(self._bridge)

        # Start command poller for cross-device commands
        try:
            from cios.core.command_poller import CommandPoller

            self._command_poller = CommandPoller(bridge=self._bridge)
            self._command_poller.start()
        except Exception as e:
            logger.debug("Command poller not started: %s", e)

        # Apply saved monitor config
        try:
            from cios.skills.monitor import apply_saved_config

            apply_saved_config()
        except Exception as e:
            logger.debug("Monitor config not applied: %s", e)

        # Spawn secondary window if multiple outputs detected
        self._spawn_secondary_windows()

    def _on_hotkey_submit(self, text: str):
        """Handle hotkey overlay submission."""
        self._input.set_text(text)
        self._on_submit()

    def _spawn_secondary_windows(self):
        """Detect secondary outputs and create independent windows for them."""
        try:
            from cios.skills.monitor import get_monitors

            monitors = get_monitors()
            if len(monitors) < 2:
                return

            # Find non-primary monitors
            primary = next((m for m in monitors if m.primary), monitors[0])
            secondaries = [m for m in monitors if m.name != primary.name]

            for mon in secondaries:
                from cios.ui.gtk.secondary_window import SecondaryWindow

                sec_win = SecondaryWindow(
                    app=self,
                    bridge=self._bridge,
                    monitor_name=mon.name,
                    width=mon.width,
                    height=mon.height,
                )
                sec_win.present()
                logger.info(
                    "Secondary window created for %s (%dx%d)", mon.name, mon.width, mon.height
                )
        except Exception as e:
            logger.debug("Secondary windows not spawned: %s", e)

    def _on_hotkey_triggered(self):
        """Called when Ctrl+Space is pressed (via compositor IPC)."""
        if self._hotkey_overlay.get_visible():
            self._hotkey_overlay.hide_overlay()
        else:
            self._hotkey_overlay.show_overlay()

    def _on_search_triggered(self):
        """Called when Ctrl+K is pressed (via compositor IPC)."""
        self._search_overlay.toggle()

    def _on_global_key(self, controller, keyval, keycode, state):
        """Handle global keyboard shortcuts (GTK-level fallback)."""
        from gi.repository import Gdk

        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and keyval == ord("k"):
            self._on_search_triggered()
            return True
        return False

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

        # Add user message to chat feed
        self._chat_feed.add_user_message(text)

        # Show status line instead of streaming bubble
        self._set_status("pensando")

        # Execute with streaming in background
        def execute():
            import time as _time

            _time.sleep(0.25)
            GLib.idle_add(self._set_status, "buscando contexto")

            try:
                if self._bridge:

                    def on_step(step: str, current: int, total: int):
                        GLib.idle_add(self._set_status, "executando")

                    GLib.idle_add(self._set_status, "processando")
                    data = self._bridge.execute_streaming(text, confirmed=False, on_step=on_step)
                    result = data.get("result", "Concluído.")
                    status = data.get("status", "success")

                    # Lock screen action
                    if data.get("action") == "lock_screen":
                        GLib.idle_add(self._hide_status)
                        GLib.idle_add(self._do_lock_screen)
                        return

                    # Confirmation needed (destructive action)
                    if data.get("confirm"):
                        confirm_msg = data["confirm"]
                        GLib.idle_add(self._hide_status)
                        GLib.idle_add(
                            self._chat_feed.add_assistant_message,
                            f"{confirm_msg}\n\nDiga 'sim' para confirmar.",
                        )
                        GLib.idle_add(self._finish_execution)
                        return

                    # Password needed
                    if data.get("password_prompt"):
                        GLib.idle_add(self._hide_status)
                        GLib.idle_add(self._finish_streaming_show, result, None)
                        GLib.idle_add(self._show_password_dialog, result)
                        return

                    # Background task
                    if status == "background":
                        task_id = data.get("task_id", "")
                        GLib.idle_add(self._hide_status)
                        GLib.idle_add(self._finish_streaming_background, result, task_id)
                        return

                    # Gallery
                    gallery = data.get("gallery")
                    if gallery:
                        GLib.idle_add(self._hide_status)
                        GLib.idle_add(self._show_gallery, gallery)
                        GLib.idle_add(self._finish_execution)
                        return

                    # Normal result
                    GLib.idle_add(self._hide_status)
                    GLib.idle_add(self._finish_streaming_show, result, status)
                else:
                    GLib.idle_add(self._hide_status)
                    GLib.idle_add(
                        self._finish_streaming_show, "Sistema ainda inicializando…", "error"
                    )
            except Exception as e:
                GLib.idle_add(self._finish_streaming_show, f"Erro: {e}", "error")

        threading.Thread(target=execute, daemon=True).start()

    def _set_status(self, phase: str):
        """Show status line with current processing phase."""
        self._status_label.set_label(phase)
        self._status_line.set_visible(True)
        # Start pulse animation
        if not hasattr(self, "_pulse_timer") or self._pulse_timer is None:
            self._pulse_state = False
            self._pulse_timer = GLib.timeout_add(1500, self._pulse_status_bar)

    def _pulse_status_bar(self):
        """Toggle pulse class for animated glow bar."""
        if not self._status_line.get_visible():
            self._pulse_timer = None
            return False
        self._pulse_state = not self._pulse_state
        if self._pulse_state:
            self._status_bar.add_css_class("pulse")
        else:
            self._status_bar.remove_css_class("pulse")
        return True

    def _hide_status(self):
        """Hide the status line."""
        self._status_line.set_visible(False)
        self._status_label.set_label("")
        self._status_bar.remove_css_class("pulse")
        if hasattr(self, "_pulse_timer") and self._pulse_timer:
            GLib.source_remove(self._pulse_timer)
            self._pulse_timer = None

    def _finish_streaming_show(self, result: str, status: str | None):
        """Show final result in chat."""
        from cios.ui.gtk.artifact_panel import is_artifact

        # Long/structured content → artifact panel
        if status and status != "error" and is_artifact(result):
            summary = result[:80].split("\n")[0] + "…"
            self._chat_feed.add_assistant_message(f"{summary}\n\n📄 Aberto no painel lateral.")
            self._artifact_panel.show_artifact(result)
        else:
            self._chat_feed.add_assistant_message(result)
            # Follow-up suggestion
            follow_up = self._suggest_follow_up(result)
            if follow_up:
                self._chat_feed.add_assistant_message(follow_up)

        self._input.set_sensitive(True)
        self._input.grab_focus()
        self._busy = False
        self._sidebar.refresh_history()

    def _finish_streaming_background(self, message: str, task_id: str):
        """Show background task progress."""
        progress_bubble = self._chat_feed.add_progress_message(message)
        self._input.set_sensitive(True)
        self._input.grab_focus()
        self._busy = False

        if task_id:
            GLib.timeout_add(2000, self._poll_task_chat, task_id, progress_bubble)

    def _suggest_follow_up(self, result: str) -> str | None:
        """Suggest a natural follow-up based on the result context.

        Conversational UX: the system anticipates the next step.
        """
        r = result.lower()

        # App installed → offer to open
        if "instalado" in r or "installed" in r or "pronto, instalado" in r:
            # Extract app name from result
            for app in ("chrome", "firefox", "code", "spotify", "vlc", "brave"):
                if app in r:
                    return f"Quer que eu abra o {app.title()}?"
            return "Quer que eu abra?"

        # Disk analysis → offer to clean
        if ("disco" in r or "armazenamento" in r or "storage" in r) and (
            "cheio" in r or "quase" in r or "%" in r
        ):
            return "Quer que eu libere espaço?"

        # Network connected → confirm
        if "conectado" in r and ("wifi" in r or "wi-fi" in r or "rede" in r):
            return None  # Connection is the end goal

        # Process killed → confirm
        if "parado" in r or "stopped" in r:
            return None  # Action complete

        # Error → offer retry
        if "não consegui" in r or "falhou" in r or "erro" in r:
            return "Quer tentar de novo?"

        # Volume adjusted → no follow-up needed
        if "volume" in r or "silenciado" in r:
            return None

        # Files organized → show result
        if "organizados" in r or "organized" in r:
            return "Quer ver como ficou?"

        # Project started → no follow-up (already complete)
        if "rodando" in r or "running" in r or "pronto" in r:
            return None

        return None

    def _poll_task_chat(self, task_id: str, progress_bubble) -> bool:
        """Poll a background task for completion. Updates chat feed."""
        if not self._bridge:
            return False

        task_data = self._bridge.get_task_result(task_id)
        if task_data is None:
            return False

        status = task_data.get("status", "")

        if status == "running":
            progress = task_data.get("progress", "")
            if progress:
                self._chat_feed.update_progress(progress_bubble, progress)
            return True

        if status in ("completed", "failed"):
            result_data = task_data.get("result", {})
            if isinstance(result_data, dict):
                result_text = result_data.get("result", "Concluído.")
            else:
                result_text = str(result_data) if result_data else "Concluído."

            self._remove_bubble(progress_bubble)
            self._chat_feed.add_assistant_message(result_text)
            self._sidebar.refresh_history()
            return False

        return True

    def _remove_bubble(self, bubble):
        """Remove a bubble from the chat feed."""
        if bubble and bubble.get_parent():
            bubble.get_parent().remove(bubble)

    def _finish_execution(self):
        """Reset UI state after execution (no result to show)."""
        self._input.set_sensitive(True)
        self._input.grab_focus()
        self._busy = False
        self._sidebar.refresh_history()

    def _show_result(self, result: str, status: str):
        """Display execution result in chat feed (legacy compat)."""
        self._chat_feed.add_assistant_message(result)
        self._input.set_sensitive(True)
        self._input.grab_focus()
        self._busy = False
        self._sidebar.refresh_history()

    def _finish_chat_execution(self, progress_bubble, result: str, status: str):
        """Remove progress bubble and display the final result."""
        parent = progress_bubble.get_parent()
        if parent:
            parent.remove(progress_bubble)
        self._show_result(result, status)

    def _show_password_dialog(self, prompt_text: str):
        """Show a password dialog as an overlay inside the main window (not a separate window)."""
        import threading

        # Create overlay container that covers the main content
        overlay_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay_container.add_css_class("sudo-overlay")
        overlay_container.set_valign(Gtk.Align.FILL)
        overlay_container.set_halign(Gtk.Align.FILL)
        overlay_container.set_vexpand(True)
        overlay_container.set_hexpand(True)

        # Center the dialog
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center.set_valign(Gtk.Align.CENTER)
        center.set_halign(Gtk.Align.CENTER)
        center.set_vexpand(True)
        overlay_container.append(center)

        # Dialog card
        dialog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        dialog_box.add_css_class("sudo-dialog")
        dialog_box.set_halign(Gtk.Align.CENTER)
        center.append(dialog_box)

        # Lock icon
        icon = Gtk.Label(label="🔒")
        icon.add_css_class("sudo-icon")
        icon.set_halign(Gtk.Align.CENTER)
        dialog_box.append(icon)

        # Title
        title = Gtk.Label(label="Autenticação necessária")
        title.add_css_class("sudo-title")
        title.set_halign(Gtk.Align.CENTER)
        dialog_box.append(title)

        # Prompt label
        label = Gtk.Label(label=prompt_text)
        label.add_css_class("sudo-label")
        label.set_wrap(True)
        label.set_halign(Gtk.Align.CENTER)
        dialog_box.append(label)

        # Password entry (masked)
        entry = Gtk.Entry()
        entry.set_visibility(False)
        entry.set_placeholder_text("Senha de administrador")
        entry.add_css_class("sudo-entry")
        dialog_box.append(entry)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.CENTER)
        dialog_box.append(btn_box)

        cancel_btn = Gtk.Button(label="Cancelar")
        cancel_btn.add_css_class("sudo-cancel")
        btn_box.append(cancel_btn)

        ok_btn = Gtk.Button(label="Confirmar")
        ok_btn.add_css_class("sudo-btn")
        btn_box.append(ok_btn)

        # Get the root overlay of the main window to add this on top
        root_overlay = self._win.get_child()  # The Gtk.Overlay
        root_overlay.add_overlay(overlay_container)

        def dismiss():
            root_overlay.remove_overlay(overlay_container)

        def on_submit(*args):
            password = entry.get_text()
            dismiss()
            if password:
                progress = self._chat_feed.add_progress_message("Executando…")

                def execute_with_password():
                    try:
                        data = self._bridge.execute_command(password)
                        result = data.get("result", "Concluído.")
                        status = data.get("status", "success")
                    except Exception as e:
                        result = f"Erro: {e}"
                        status = "error"
                    GLib.idle_add(self._finish_chat_execution, progress, result, status)

                threading.Thread(target=execute_with_password, daemon=True).start()
            else:
                self._finish_execution()

        def on_cancel(*args):
            dismiss()
            self._finish_execution()

        ok_btn.connect("clicked", on_submit)
        cancel_btn.connect("clicked", on_cancel)
        entry.connect("activate", on_submit)

        # Focus the entry
        entry.grab_focus()
        self._busy = False  # Allow interaction with dialog

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

    def _do_lock_screen(self):
        """Show the lock screen overlay."""
        from cios.ui.gtk.lock_screen import show_lock_screen

        show_lock_screen(self._win)

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
        from cios.ui.gtk.search_overlay import SearchOverlay
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
                color: {ERROR};
            }}
            .prompt-area {{
                background-color: {BG_CARD};
                border-radius: 12px;
                padding: 12px 16px;
                border: 1px solid rgba(0,229,255,0.12);
                box-shadow: 0 0 8px rgba(0,229,255,0.04);
                transition: all 200ms ease;
            }}
            .prompt-area:focus-within {{
                border-color: rgba(0,230,118,0.4);
                box-shadow: 0 0 14px rgba(0,230,118,0.08);
            }}
            .status-line {{
                padding: 2px 0;
            }}
            .status-dot {{
                color: {ACCENT};
                font-size: 8px;
                opacity: 0.9;
            }}
            .status-text {{
                color: {ACCENT};
                font-size: 11px;
                font-weight: 500;
                opacity: 0.7;
                letter-spacing: 0.5px;
            }}
            .status-glow-bar {{
                min-height: 2px;
                background: linear-gradient(90deg, transparent, {ACCENT}, transparent);
                opacity: 0.5;
                border-radius: 1px;
                transition: all 1.5s ease-in-out;
            }}
            .status-glow-bar.pulse {{
                opacity: 0.15;
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
                border-color: rgba(0,230,118,0.5);
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
            + SearchOverlay.get_css()
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
