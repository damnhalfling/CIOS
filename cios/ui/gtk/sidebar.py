"""CIOS GTK4 Sidebar — System status + history + maestro login.

Visual: TRON-inspired glow cards, geometric icons, subtle borders.
Layout (top to bottom):
- System metrics (glow cards with icon + sigla + value)
- Message history (scrollable)
- Maestro login (glow card at bottom)
"""

import time as _time

from gi.repository import GLib, Gtk

from cios.ui.theme import (
    ACCENT,
    ACCENT_LT,
    BG_CARD,
    BG_HOVER,
    FG,
    FG_DIM,
    FG_SEC,
    SUCCESS,
)


class Sidebar(Gtk.Box):
    """Right sidebar: glow-card metrics + history + maestro login."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_size_request(220, -1)
        self.set_hexpand(False)
        self.add_css_class("sidebar")
        self.set_margin_top(12)
        self.set_margin_end(12)
        self.set_margin_bottom(12)
        self._bridge = None
        self._artifact_panel = None

        # ── System metrics (glow cards in 2x2 grid) ──
        metrics_grid = Gtk.Grid()
        metrics_grid.set_row_spacing(6)
        metrics_grid.set_column_spacing(6)
        metrics_grid.set_margin_start(10)
        metrics_grid.set_margin_end(10)
        metrics_grid.set_margin_top(10)
        metrics_grid.set_margin_bottom(10)
        metrics_grid.set_column_homogeneous(True)
        self.append(metrics_grid)

        self._cpu_metric = self._create_glow_card("◇", "CPU", "0%")
        metrics_grid.attach(self._cpu_metric["frame"], 0, 0, 1, 1)

        self._mem_metric = self._create_glow_card("⬡", "MEM", "0%")
        metrics_grid.attach(self._mem_metric["frame"], 1, 0, 1, 1)

        self._disk_metric = self._create_glow_card("⊡", "DISC", "0%")
        metrics_grid.attach(self._disk_metric["frame"], 0, 1, 1, 1)

        self._ai_metric = self._create_glow_card("◎", "IA", "off")
        metrics_grid.attach(self._ai_metric["frame"], 1, 1, 1, 1)

        # Separator
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep1.add_css_class("sidebar-sep")
        self.append(sep1)

        # ── Message history (scrollable, fills available space) ──
        self._history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._history_box.set_margin_start(8)
        self._history_box.set_margin_end(8)
        self._history_box.set_margin_top(8)

        history_title = Gtk.Label(label="Histórico")
        history_title.add_css_class("sidebar-title")
        history_title.set_halign(Gtk.Align.START)
        history_title.set_margin_bottom(4)
        self._history_box.append(history_title)

        self._history_scroll = Gtk.ScrolledWindow()
        self._history_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._history_scroll.set_vexpand(True)
        self._history_box.append(self._history_scroll)

        self._history_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._history_scroll.set_child(self._history_list)

        self.append(self._history_box)

        # Separator
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep2.add_css_class("sidebar-sep")
        self.append(sep2)

        # ── Maestro login (glow card at bottom) ──
        login_frame = Gtk.Frame()
        login_frame.add_css_class("maestro-card")
        login_frame.set_margin_start(10)
        login_frame.set_margin_end(10)
        login_frame.set_margin_top(8)
        login_frame.set_margin_bottom(10)

        login_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        login_box.set_margin_start(10)
        login_box.set_margin_end(10)
        login_box.set_margin_top(8)
        login_box.set_margin_bottom(8)
        login_frame.set_child(login_box)

        login_icon = Gtk.Label(label="⬡")
        login_icon.add_css_class("maestro-icon")
        login_box.append(login_icon)

        login_label = Gtk.Label(label="Maestro")
        login_label.add_css_class("maestro-label")
        login_label.set_hexpand(True)
        login_label.set_halign(Gtk.Align.START)
        login_box.append(login_label)

        self._maestro_status = Gtk.Label(label="offline")
        self._maestro_status.add_css_class("maestro-status")
        login_box.append(self._maestro_status)

        # Make clickable
        click_ctrl = Gtk.GestureClick()
        click_ctrl.connect("released", self._on_maestro_click)
        login_frame.add_controller(click_ctrl)

        self.append(login_frame)

        # Start polling metrics
        GLib.timeout_add(5000, self._update_metrics)
        self._update_metrics()

        # Check initial login state
        GLib.idle_add(self._check_login_state)

    def set_bridge(self, bridge):
        """Set bridge for history access."""
        self._bridge = bridge
        self.refresh_history()

    def set_artifact_panel(self, panel):
        """Set reference to artifact panel for opening URLs."""
        self._artifact_panel = panel

    def refresh_history(self):
        """Reload thread history."""
        child = self._history_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._history_list.remove(child)
            child = next_child

        if not self._bridge:
            empty = Gtk.Label(label="Nenhuma conversa")
            empty.add_css_class("history-empty")
            self._history_list.append(empty)
            return

        try:
            threads = self._bridge._thread_manager.get_recent_threads(10)
        except Exception:
            threads = []

        if not threads:
            empty = Gtk.Label(label="Nenhuma conversa")
            empty.add_css_class("history-empty")
            self._history_list.append(empty)
            return

        for thread in threads:
            row = self._build_history_row(thread)
            self._history_list.append(row)

    def _build_history_row(self, thread) -> Gtk.Box:
        """Build a compact history entry."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("history-row")

        outcome = getattr(thread, "outcome", "") or ""
        icon = "✓" if outcome == "success" else "○"
        icon_lbl = Gtk.Label(label=icon)
        icon_lbl.add_css_class("history-icon")
        if outcome == "success":
            icon_lbl.add_css_class("history-icon-ok")
        row.append(icon_lbl)

        summary = getattr(thread, "summary", "") or "…"
        summary_lbl = Gtk.Label(label=summary)
        summary_lbl.set_halign(Gtk.Align.START)
        summary_lbl.set_hexpand(True)
        summary_lbl.set_ellipsize(3)
        summary_lbl.add_css_class("history-summary")
        row.append(summary_lbl)

        created = getattr(thread, "created_at", None)
        if created:
            time_str = self._format_time(created)
            time_lbl = Gtk.Label(label=time_str)
            time_lbl.add_css_class("history-time")
            row.append(time_lbl)

        return row

    def _format_time(self, timestamp) -> str:
        """Format timestamp as relative time."""
        try:
            diff = _time.time() - timestamp
            if diff < 60:
                return "agora"
            elif diff < 3600:
                return f"{int(diff / 60)}m"
            elif diff < 86400:
                return f"{int(diff / 3600)}h"
            else:
                return f"{int(diff / 86400)}d"
        except Exception:
            return ""

    def _create_glow_card(self, icon: str, sigla: str, value: str) -> dict:
        """Create a metric card with glow border (TRON style)."""
        frame = Gtk.Frame()
        frame.add_css_class("metric-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(4)
        box.set_margin_end(4)
        frame.set_child(box)

        icon_lbl = Gtk.Label(label=icon)
        icon_lbl.add_css_class("metric-icon")
        box.append(icon_lbl)

        sigla_lbl = Gtk.Label(label=sigla)
        sigla_lbl.add_css_class("metric-sigla")
        box.append(sigla_lbl)

        val_lbl = Gtk.Label(label=value)
        val_lbl.add_css_class("metric-value")
        box.append(val_lbl)

        return {"frame": frame, "box": box, "icon": icon_lbl, "sigla": sigla_lbl, "value": val_lbl}

    def _update_metrics(self):
        """Poll system metrics and apply color states."""
        try:
            with open("/proc/loadavg") as f:
                load = float(f.read().split()[0])
                import os

                cpus = os.cpu_count() or 1
                cpu_pct = min(int(load / cpus * 100), 100)
                self._cpu_metric["value"].set_label(f"{cpu_pct}%")
                self._apply_card_state(self._cpu_metric["frame"], cpu_pct)
        except Exception:
            pass

        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
                total = int(lines[0].split()[1])
                avail = int(lines[2].split()[1])
                mem_pct = int((1 - avail / total) * 100)
                self._mem_metric["value"].set_label(f"{mem_pct}%")
                self._apply_card_state(self._mem_metric["frame"], mem_pct)
        except Exception:
            pass

        try:
            import shutil

            usage = shutil.disk_usage("/")
            disk_pct = int(usage.used / usage.total * 100)
            self._disk_metric["value"].set_label(f"{disk_pct}%")
            self._apply_card_state(self._disk_metric["frame"], disk_pct)
        except Exception:
            pass

        return True

    def _apply_card_state(self, frame: Gtk.Frame, pct: int):
        """Apply color state to metric card based on value.

        - < 50%: normal (cyan/blue)
        - 50-79%: normal
        - >= 80%: warn (red)
        """
        frame.remove_css_class("metric-card-warn")
        frame.remove_css_class("metric-card-focus")

        if pct >= 80:
            frame.add_css_class("metric-card-warn")

    def _check_login_state(self):
        """Check if already logged into Maestro."""
        try:
            from cios.core.intelligence import intelligence

            if intelligence.is_logged_in:
                name = intelligence.user.name if intelligence.user else "online"
                self._maestro_status.set_label(name or "online")
        except Exception:
            pass

    def _on_maestro_click(self, gesture, n_press, x, y):
        """Start Maestro OAuth login flow inline (no external browser)."""
        import threading

        from gi.repository import GLib

        self._maestro_status.set_label("conectando…")

        def _do_login():
            from cios.core.intelligence import intelligence

            if intelligence.is_logged_in:
                # Already logged in — open maestro in artifact panel
                name = intelligence.user.name if intelligence.user else "online"
                GLib.idle_add(self._maestro_status.set_label, name or "online")
                if self._artifact_panel:
                    GLib.idle_add(
                        self._artifact_panel.show_url,
                        "https://maestro.cios-ai.com",
                        "Maestro",
                    )
            else:
                # Start OAuth flow INLINE (in artifact panel, not external browser)
                self._start_inline_auth()

        threading.Thread(target=_do_login, daemon=True).start()

    def _start_inline_auth(self):
        """Start OAuth flow using the artifact panel WebView instead of external browser."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from gi.repository import GLib

        from cios.core.intelligence import API_BASE, intelligence

        auth_url = (
            f"{API_BASE}/v1/auth/google?state=cios&redirect_uri=http://localhost:7778/callback"
        )

        # Start local callback server
        def _run_callback_server():
            class CallbackHandler(BaseHTTPRequestHandler):
                def do_GET(self_handler):
                    from urllib.parse import parse_qs, urlparse

                    parsed = urlparse(self_handler.path)
                    if parsed.path == "/callback":
                        params = parse_qs(parsed.query)
                        token = params.get("token", [""])[0]
                        user_json = params.get("user", [""])[0]

                        if token and user_json:
                            try:
                                user_data = json.loads(user_json)
                                intelligence.save_auth(token, user_data)
                                name = user_data.get("name", "online")
                                GLib.idle_add(self._maestro_status.set_label, name)
                                # Close auth view, open maestro
                                if self._artifact_panel:
                                    GLib.idle_add(
                                        self._artifact_panel.show_url,
                                        "https://maestro.cios-ai.com",
                                        "Maestro",
                                    )

                                self_handler.send_response(200)
                                self_handler.send_header("Content-Type", "text/html")
                                self_handler.end_headers()
                                self_handler.wfile.write(
                                    b"<html><body style='background:#00050d;color:#00e5ff;"
                                    b"font-family:sans-serif;text-align:center;padding:60px'>"
                                    b"<h2>Login realizado</h2>"
                                    b"<p>Pode fechar esta aba.</p></body></html>"
                                )
                            except Exception:
                                GLib.idle_add(self._maestro_status.set_label, "erro")
                                self_handler.send_response(400)
                                self_handler.end_headers()
                        else:
                            GLib.idle_add(self._maestro_status.set_label, "erro")
                            self_handler.send_response(400)
                            self_handler.end_headers()
                    else:
                        self_handler.send_response(404)
                        self_handler.end_headers()

                def log_message(self_handler, format, *args):
                    pass

            try:
                server = HTTPServer(("localhost", 7778), CallbackHandler)
                server.timeout = 120
                server.handle_request()
                server.server_close()
            except Exception:
                GLib.idle_add(self._maestro_status.set_label, "erro")

        threading.Thread(target=_run_callback_server, daemon=True).start()

        # Open auth URL in artifact panel (inline WebKit, no external browser)
        import time

        time.sleep(0.3)
        if self._artifact_panel:
            GLib.idle_add(self._artifact_panel.show_url, auth_url, "Login Maestro")

    @staticmethod
    def get_css() -> str:
        """Return CSS for sidebar — borderless floating glow cards."""
        return f"""
            .sidebar {{
                background-color: transparent;
            }}
            .sidebar-title {{
                color: {FG_DIM};
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            .sidebar-sep {{
                min-height: 0;
                margin: 0;
                background: transparent;
            }}
            .metric-card {{
                background-color: {BG_CARD};
                border: 1px solid rgba(0,229,255,0.12);
                border-radius: 8px;
                box-shadow: 0 0 8px rgba(0,229,255,0.04), inset 0 1px 0 rgba(0,229,255,0.06);
                transition: all 200ms ease;
            }}
            .metric-card:hover {{
                border-color: rgba(0,229,255,0.3);
                box-shadow: 0 0 14px rgba(0,229,255,0.1);
            }}
            .metric-card-warn {{
                border-color: rgba(255,23,68,0.3);
                box-shadow: 0 0 10px rgba(255,23,68,0.08);
            }}
            .metric-card-warn .metric-icon {{
                color: #ff1744;
            }}
            .metric-card-warn .metric-value {{
                color: #ff1744;
            }}
            .metric-card-focus {{
                border-color: rgba(0,230,118,0.3);
                box-shadow: 0 0 10px rgba(0,230,118,0.08);
            }}
            .metric-card-focus .metric-icon {{
                color: #00e676;
            }}
            .metric-card-focus .metric-value {{
                color: #00e676;
            }}
            .metric-icon {{
                color: {ACCENT_LT};
                font-size: 18px;
            }}
            .metric-sigla {{
                color: {FG_DIM};
                font-size: 8px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }}
            .metric-value {{
                color: {FG_SEC};
                font-size: 11px;
                font-weight: bold;
            }}
            .history-empty {{
                color: {FG_DIM};
                font-size: 11px;
                font-style: italic;
                padding: 8px 0;
            }}
            .history-row {{
                padding: 5px 8px;
                border-radius: 6px;
            }}
            .history-row:hover {{
                background-color: {BG_HOVER};
            }}
            .history-icon {{
                color: {FG_DIM};
                font-size: 11px;
            }}
            .history-icon-ok {{
                color: {SUCCESS};
            }}
            .history-summary {{
                color: {FG_SEC};
                font-size: 11px;
            }}
            .history-time {{
                color: {FG_DIM};
                font-size: 10px;
            }}
            .maestro-card {{
                background-color: {BG_CARD};
                border: 1px solid rgba(0,229,255,0.15);
                border-radius: 8px;
                box-shadow: 0 0 10px rgba(0,229,255,0.05);
                transition: all 200ms ease;
            }}
            .maestro-card:hover {{
                border-color: rgba(0,229,255,0.4);
                box-shadow: 0 0 18px rgba(0,229,255,0.12);
            }}
            .maestro-icon {{
                color: {ACCENT};
                font-size: 18px;
            }}
            .maestro-label {{
                color: {FG};
                font-size: 12px;
                font-weight: bold;
            }}
            .maestro-status {{
                color: {FG_DIM};
                font-size: 10px;
            }}
        """
