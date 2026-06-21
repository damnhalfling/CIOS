"""CIOS GTK4 Onboarding — First-run setup wizard (Wayland-native).

Guides the user through initial configuration:
1. Welcome + language selection
2. Wi-Fi connection (if not connected)
3. Keyboard layout
4. LLM provider setup
5. Quick tour + completion

Runs automatically on first launch (no ~/.cios/.onboarding_done).
"""

import logging
import subprocess

from cios.core import config
from cios.core.config import CIOS_HOME, ensure_dirs

logger = logging.getLogger(__name__)

_ONBOARDING_DONE_FLAG = CIOS_HOME / ".onboarding_done"


def needs_onboarding() -> bool:
    """Check if onboarding should run."""
    return not _ONBOARDING_DONE_FLAG.exists()


def mark_onboarding_done() -> None:
    """Mark onboarding as completed."""
    ensure_dirs()
    _ONBOARDING_DONE_FLAG.touch()


def _check_wifi_connected() -> bool:
    """Check if there's an active network connection."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "STATE", "general"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "connected" in result.stdout.lower()
    except Exception:
        return True  # Assume connected if nmcli not available


def _get_available_networks() -> list[str]:
    """Get list of available Wi-Fi networks."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "SSID", "device", "wifi", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        networks = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return list(dict.fromkeys(networks))[:10]
    except Exception:
        return []


def _connect_wifi(ssid: str, password: str) -> bool:
    """Attempt to connect to a Wi-Fi network."""
    try:
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
        if password:
            cmd += ["password", password]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def _get_keyboard_layouts() -> list[tuple[str, str]]:
    """Get common keyboard layouts."""
    return [
        ("Português (Brasil)", "br"),
        ("English (US)", "us"),
        ("Español", "es"),
        ("Français", "fr"),
        ("Deutsch", "de"),
        ("Italiano", "it"),
        ("Português (Portugal)", "pt"),
    ]


def _set_keyboard_layout(layout: str) -> None:
    """Set the keyboard layout."""
    try:
        subprocess.run(["setxkbmap", layout], capture_output=True, timeout=5)
        config.set("keyboard_layout", layout)
    except Exception:
        pass


def run_onboarding() -> bool:
    """Run the onboarding wizard. Returns True if completed."""
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import GLib, Gtk
    except (ImportError, ValueError):
        logger.warning("GTK4 not available, skipping onboarding")
        mark_onboarding_done()
        return True

    from cios.ui.theme import ACCENT, ACCENT_LT, BG, BG_CARD, BORDER, FG, FG_DIM, FG_SEC

    app = Gtk.Application(application_id="com.cios.onboarding")
    completed = [False]

    def on_activate(app):
        win = Gtk.ApplicationWindow(application=app)
        win.set_title("CIOS — Setup")
        win.set_default_size(600, 450)
        win.set_resizable(False)

        _send_compositor_ready()

        css = Gtk.CssProvider()
        css.load_from_string(f"""
            window {{ background-color: {BG}; }}
            .welcome-title {{ color: {FG}; font-size: 24px; font-weight: bold; }}
            .welcome-sub {{ color: {FG_SEC}; font-size: 14px; }}
            .step-title {{ color: {FG}; font-size: 18px; font-weight: bold; }}
            .step-desc {{ color: {FG_SEC}; font-size: 13px; }}
            .accent-btn {{
                background-color: {ACCENT}; color: white; border-radius: 8px;
                padding: 12px 32px; font-size: 14px; font-weight: bold;
            }}
            .accent-btn:hover {{ background-color: {ACCENT_LT}; }}
            .skip-btn {{
                background: transparent; color: {FG_DIM}; border: none;
                font-size: 12px; padding: 8px 16px;
            }}
            .card {{ background-color: {BG_CARD}; border-radius: 8px; padding: 16px; }}
            .dim {{ color: {FG_DIM}; }}
            .wifi-entry {{
                background: {BG_CARD}; color: {FG}; border: 1px solid {BORDER};
                border-radius: 6px; padding: 8px 12px; font-size: 13px;
            }}
            .wifi-entry:focus {{ border-color: {ACCENT_LT}; }}
            .step-dot {{ color: {FG_DIM}; font-size: 11px; }}
            .step-dot-active {{ color: {ACCENT_LT}; font-size: 11px; font-weight: bold; }}
        """)
        Gtk.StyleContext.add_provider_for_display(
            win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        stack.set_transition_duration(300)
        win.set_child(stack)

        stack.add_named(_build_welcome(stack), "welcome")
        stack.add_named(_build_wifi(stack, GLib), "wifi")
        stack.add_named(_build_keyboard(stack), "keyboard")
        stack.add_named(_build_provider(stack), "provider")
        stack.add_named(_build_tour(stack, app, completed), "tour")

        stack.set_visible_child_name("welcome")
        win.present()

    def _step_dots(current: int, total: int = 5) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_halign(Gtk.Align.CENTER)
        box.set_margin_bottom(16)
        for i in range(total):
            dot = Gtk.Label(label="●" if i == current else "○")
            dot.add_css_class("step-dot-active" if i == current else "step-dot")
            box.append(dot)
        return box

    def _build_welcome(stack):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(40)
        box.set_margin_end(40)

        box.append(_step_dots(0))

        title = Gtk.Label(label="Bem-vindo ao CIOS")
        title.add_css_class("welcome-title")
        box.append(title)

        sub = Gtk.Label(label="Seu computador agora entende intenção.")
        sub.add_css_class("welcome-sub")
        box.append(sub)

        desc = Gtk.Label(
            label="Fale o que quer fazer. O sistema executa.\n"
            "Sem menus, sem apps, sem fricção.\n\n"
            "Vamos configurar algumas coisas rapidamente."
        )
        desc.add_css_class("dim")
        desc.set_justify(2)
        box.append(desc)

        btn = Gtk.Button(label="Começar →")
        btn.add_css_class("accent-btn")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect(
            "clicked",
            lambda _: stack.set_visible_child_name(
                "keyboard" if _check_wifi_connected() else "wifi"
            ),
        )
        box.append(btn)

        return box

    def _build_wifi(stack, GLib):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(40)
        box.set_margin_end(40)

        box.append(_step_dots(1))

        title = Gtk.Label(label="Conexão Wi-Fi")
        title.add_css_class("step-title")
        box.append(title)

        desc = Gtk.Label(label="Conecte-se à internet para baixar atualizações e IA.")
        desc.add_css_class("step-desc")
        box.append(desc)

        networks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        networks_box.add_css_class("card")
        status_label = Gtk.Label(label="Buscando redes…")
        status_label.add_css_class("dim")
        networks_box.append(status_label)
        box.append(networks_box)

        pw_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pw_box.set_visible(False)
        pw_entry = Gtk.Entry()
        pw_entry.set_visibility(False)
        pw_entry.set_placeholder_text("Senha do Wi-Fi")
        pw_entry.add_css_class("wifi-entry")
        pw_box.append(pw_entry)
        box.append(pw_box)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)

        skip_btn = Gtk.Button(label="Pular")
        skip_btn.add_css_class("skip-btn")
        skip_btn.connect("clicked", lambda _: stack.set_visible_child_name("keyboard"))
        btn_box.append(skip_btn)

        connect_btn = Gtk.Button(label="Conectar")
        connect_btn.add_css_class("accent-btn")
        connect_btn.set_sensitive(False)
        btn_box.append(connect_btn)
        box.append(btn_box)

        selected_ssid = [None]

        def populate():
            networks = _get_available_networks()
            while networks_box.get_first_child():
                networks_box.remove(networks_box.get_first_child())
            if not networks:
                lbl = Gtk.Label(label="Nenhuma rede encontrada")
                lbl.add_css_class("dim")
                networks_box.append(lbl)
                return False

            group = None
            for ssid in networks:
                radio = Gtk.CheckButton(label=ssid)
                if group:
                    radio.set_group(group)
                else:
                    group = radio

                def on_sel(r, s=ssid):
                    if r.get_active():
                        selected_ssid[0] = s
                        pw_box.set_visible(True)
                        connect_btn.set_sensitive(True)

                radio.connect("toggled", on_sel)
                networks_box.append(radio)
            return False

        def on_connect(_):
            import threading

            ssid = selected_ssid[0]
            pw = pw_entry.get_text()
            if not ssid:
                return
            connect_btn.set_label("Conectando…")
            connect_btn.set_sensitive(False)

            def do():
                ok = _connect_wifi(ssid, pw)
                GLib.idle_add(
                    lambda: (
                        stack.set_visible_child_name("keyboard")
                        if ok
                        else (
                            connect_btn.set_label("Falhou — Tentar"),
                            connect_btn.set_sensitive(True),
                        )
                    )
                )

            threading.Thread(target=do, daemon=True).start()

        connect_btn.connect("clicked", on_connect)
        GLib.timeout_add(500, populate)

        return box

    def _build_keyboard(stack):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(40)
        box.set_margin_end(40)

        box.append(_step_dots(2))

        title = Gtk.Label(label="Teclado")
        title.add_css_class("step-title")
        box.append(title)

        desc = Gtk.Label(label="Selecione o layout do seu teclado.")
        desc.add_css_class("step-desc")
        box.append(desc)

        layouts_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        layouts_box.add_css_class("card")

        layouts = _get_keyboard_layouts()
        group = None
        selected = ["br"]

        for label_text, code in layouts:
            radio = Gtk.CheckButton(label=label_text)
            if group:
                radio.set_group(group)
            else:
                group = radio
                radio.set_active(True)
            radio.connect(
                "toggled", lambda r, c=code: selected.__setitem__(0, c) if r.get_active() else None
            )
            layouts_box.append(radio)

        box.append(layouts_box)

        btn = Gtk.Button(label="Continuar →")
        btn.add_css_class("accent-btn")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect(
            "clicked",
            lambda _: (
                _set_keyboard_layout(selected[0]),
                stack.set_visible_child_name("provider"),
            ),
        )
        box.append(btn)

        return box

    def _build_provider(stack):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(40)
        box.set_margin_end(40)

        box.append(_step_dots(3))

        title = Gtk.Label(label="Inteligência")
        title.add_css_class("step-title")
        box.append(title)

        desc = Gtk.Label(
            label="O CIOS usa IA para entender suas intenções.\nEscolha como quer usar:"
        )
        desc.add_css_class("step-desc")
        desc.set_justify(2)
        box.append(desc)

        options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        options_box.add_css_class("card")

        providers = [
            ("🧠 Ollama (local, privado, requer 8GB RAM)", "ollama"),
            ("☁️ API CIOS (cloud, rápido)", "cios"),
            ("⚡ Sem IA (só comandos diretos)", "none"),
        ]

        group = None
        selected = ["ollama"]

        for label_text, value in providers:
            radio = Gtk.CheckButton(label=label_text)
            if group:
                radio.set_group(group)
            else:
                group = radio
                radio.set_active(True)
            radio.connect(
                "toggled", lambda r, v=value: selected.__setitem__(0, v) if r.get_active() else None
            )
            options_box.append(radio)

        box.append(options_box)

        hint = Gtk.Label(label="💡 Para IA local: sudo cios-setup-ai (após o setup)")
        hint.add_css_class("dim")
        hint.set_halign(Gtk.Align.START)
        box.append(hint)

        btn = Gtk.Button(label="Continuar →")
        btn.add_css_class("accent-btn")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect(
            "clicked",
            lambda _: (
                config.set("llm_provider", selected[0]),
                stack.set_visible_child_name("tour"),
            ),
        )
        box.append(btn)

        return box

    def _build_tour(stack, app, completed):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(40)
        box.set_margin_end(40)

        box.append(_step_dots(4))

        title = Gtk.Label(label="Tudo pronto!")
        title.add_css_class("welcome-title")
        box.append(title)

        desc = Gtk.Label(label="Exemplos do que você pode dizer:")
        desc.add_css_class("step-desc")
        box.append(desc)

        examples = [
            '💡 "quero trabalhar no projeto X"',
            '📁 "organiza meus downloads"',
            '🔌 "conecta no wifi"',
            '📊 "meu computador está lento"',
            '🔊 "aumenta o volume"',
            '📦 "instala o chrome"',
            '🔄 "atualizar o sistema"',
        ]

        examples_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        examples_box.add_css_class("card")
        for ex in examples:
            lbl = Gtk.Label(label=ex)
            lbl.set_halign(Gtk.Align.START)
            lbl.add_css_class("step-desc")
            examples_box.append(lbl)
        box.append(examples_box)

        shortcuts = Gtk.Label(label="⌨️ Ctrl+Space — overlay rápido\n⌨️ Super+Q — logout")
        shortcuts.add_css_class("dim")
        shortcuts.set_halign(Gtk.Align.START)
        box.append(shortcuts)

        btn = Gtk.Button(label="Iniciar CIOS")
        btn.add_css_class("accent-btn")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect(
            "clicked",
            lambda _: (
                mark_onboarding_done(),
                completed.__setitem__(0, True),
                app.quit(),
            ),
        )
        box.append(btn)

        return box

    app.connect("activate", on_activate)
    app.run(None)

    return completed[0]


def _send_compositor_ready():
    """Send 'ready' to compositor via IPC to dismiss splash overlay."""
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
        s.settimeout(2.0)
        try:
            s.recv(1024)
        except (TimeoutError, OSError):
            pass
        s.close()
    except Exception:
        pass
