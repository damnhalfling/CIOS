"""CIOS GTK4 Onboarding — First-run setup wizard (Wayland-native).

Guides the user through initial configuration:
1. Welcome + language selection
2. LLM provider setup
3. Wi-Fi connection check
4. Quick tour
5. Completion

Runs automatically on first launch (no ~/.cios/.onboarding_done).
"""

import logging

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


def run_onboarding() -> bool:
    """Run the onboarding wizard. Returns True if completed."""
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk
    except (ImportError, ValueError):
        # Fallback: skip onboarding, mark as done
        logger.warning("GTK4 not available, skipping onboarding")
        mark_onboarding_done()
        return True

    from cios.ui.theme import ACCENT, ACCENT_LT, BG, BG_CARD, FG, FG_DIM, FG_SEC

    app = Gtk.Application(application_id="com.cios.onboarding")
    completed = [False]

    def on_activate(app):
        win = Gtk.ApplicationWindow(application=app)
        win.set_title("CIOS — Setup")
        win.set_default_size(600, 450)
        win.set_resizable(False)

        # Dismiss compositor splash overlay so this window is visible
        _send_compositor_ready()

        # CSS
        css = Gtk.CssProvider()
        css.load_from_string(f"""
            window {{
                background-color: {BG};
            }}
            .welcome-title {{
                color: {FG};
                font-size: 24px;
                font-weight: bold;
            }}
            .welcome-sub {{
                color: {FG_SEC};
                font-size: 14px;
            }}
            .step-title {{
                color: {FG};
                font-size: 18px;
                font-weight: bold;
            }}
            .step-desc {{
                color: {FG_SEC};
                font-size: 13px;
            }}
            .accent-btn {{
                background-color: {ACCENT};
                color: white;
                border-radius: 8px;
                padding: 12px 32px;
                font-size: 14px;
                font-weight: bold;
            }}
            .accent-btn:hover {{
                background-color: {ACCENT_LT};
            }}
            .card {{
                background-color: {BG_CARD};
                border-radius: 8px;
                padding: 16px;
            }}
            .dim {{
                color: {FG_DIM};
            }}
        """)
        Gtk.StyleContext.add_provider_for_display(
            win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Stack for wizard steps
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        stack.set_transition_duration(300)
        win.set_child(stack)

        # ── Step 1: Welcome ──
        welcome = _build_welcome(stack, win)
        stack.add_named(welcome, "welcome")

        # ── Step 2: Provider ──
        provider = _build_provider(stack, win)
        stack.add_named(provider, "provider")

        # ── Step 3: Tour ──
        tour = _build_tour(stack, win, app, completed)
        stack.add_named(tour, "tour")

        stack.set_visible_child_name("welcome")
        win.present()

    def _build_welcome(stack, win):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(40)
        box.set_margin_end(40)

        title = Gtk.Label(label="Bem-vindo ao CIOS")
        title.add_css_class("welcome-title")
        box.append(title)

        sub = Gtk.Label(label="Seu computador agora entende intenção.")
        sub.add_css_class("welcome-sub")
        box.append(sub)

        desc = Gtk.Label(
            label="Fale o que quer fazer. O sistema executa.\nSem menus, sem apps, sem fricção."
        )
        desc.add_css_class("dim")
        desc.set_justify(2)  # CENTER
        box.append(desc)

        btn = Gtk.Button(label="Começar")
        btn.add_css_class("accent-btn")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect("clicked", lambda _: stack.set_visible_child_name("provider"))
        box.append(btn)

        return box

    def _build_provider(stack, win):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(40)
        box.set_margin_end(40)

        title = Gtk.Label(label="Inteligência Local")
        title.add_css_class("step-title")
        box.append(title)

        desc = Gtk.Label(
            label="O CIOS usa IA local (Ollama) para entender suas intenções.\n"
            "Após o setup, execute: sudo cios-setup-ai"
        )
        desc.add_css_class("step-desc")
        desc.set_justify(2)
        box.append(desc)

        # Provider options
        options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        options_box.add_css_class("card")

        providers = [
            ("Ollama (local, privado)", "ollama"),
            ("API CIOS (cloud)", "cios"),
            ("Sem IA (só regex)", "none"),
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

        btn = Gtk.Button(label="Continuar")
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

    def _build_tour(stack, win, app, completed):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_start(40)
        box.set_margin_end(40)

        title = Gtk.Label(label="Pronto!")
        title.add_css_class("welcome-title")
        box.append(title)

        examples = [
            '💡 "quero trabalhar no projeto X"',
            '📁 "organiza meus downloads"',
            '🔌 "conecta no wifi"',
            '📊 "meu computador está lento"',
            '🔊 "aumenta o volume"',
        ]

        desc = Gtk.Label(label="Exemplos do que você pode dizer:")
        desc.add_css_class("step-desc")
        box.append(desc)

        examples_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        examples_box.add_css_class("card")
        for ex in examples:
            lbl = Gtk.Label(label=ex)
            lbl.set_halign(Gtk.Align.START)
            lbl.add_css_class("step-desc")
            examples_box.append(lbl)
        box.append(examples_box)

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
        # Wait for compositor to process before closing
        s.settimeout(2.0)
        try:
            s.recv(1024)  # Read response
        except (TimeoutError, OSError):
            pass
        s.close()
    except Exception:
        pass  # Non-fatal: compositor may not be running (e.g., --setup mode)
