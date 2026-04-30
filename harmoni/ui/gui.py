"""Harmoni OS — Native Desktop Interface.

Production-quality 3-column layout with smooth animations,
micro-interactions, and system-level visual polish.

Every color change is animated. Every element fades in.
Every interaction has feedback. Nothing snaps.
"""

import os
import platform
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional, Callable

from harmoni.core.bridge import HarmoniBridge

# ═══════════════════════════════════════════════════════════════════════════
#  DESIGN TOKENS
# ═══════════════════════════════════════════════════════════════════════════

# Backgrounds (darkest → lightest)
BG         = "#0b0f14"
BG_PANEL   = "#0f1319"
BG_CARD    = "#111827"
BG_INPUT   = "#161b24"
BG_HOVER   = "#1e2738"
BG_PRESS   = "#252e3f"

# Borders
BORDER     = "#1f2937"
BORDER_LT  = "#2d3748"

# Foreground
FG         = "#e5e7eb"
FG_SEC     = "#9ca3af"
FG_DIM     = "#6b7280"

# Accent
ACCENT     = "#7c3aed"
ACCENT_LT  = "#a78bfa"
ACCENT_DK  = "#6d28d9"

# Semantic
SUCCESS    = "#22c55e"
SUCCESS_BG = "#0a1a0f"
WARNING    = "#eab308"
ERROR      = "#ef4444"
CYAN       = "#06b6d4"

# Spacing scale (px)
SP_MICRO   = 4
SP_TIGHT   = 8
SP_COMPACT = 12
SP_DEFAULT = 16
SP_SECTION = 24
SP_BLOCK   = 32
SP_PAGE    = 40

# Timing (ms)
T_FAST     = 100
T_NORMAL   = 180
T_SLOW     = 300
T_STEP     = 400
T_DOTS     = 500

# Layout
SIDEBAR_W  = 240
RIGHT_W    = 280

# User context
_USER  = os.environ.get("USER", "user").capitalize()
_HOUR  = time.localtime().tm_hour
_GREET = "Bom dia" if _HOUR < 12 else ("Boa tarde" if _HOUR < 18 else "Boa noite")


# ═══════════════════════════════════════════════════════════════════════════
#  COLOR UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def _hex2rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb2hex(r: int, g: int, b: int) -> str:
    return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"


def _lerp(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex2rgb(c1)
    r2, g2, b2 = _hex2rgb(c2)
    return _rgb2hex(int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t))


# ═══════════════════════════════════════════════════════════════════════════
#  ANIMATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class Animator:
    """Smooth animation scheduler using root.after()."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._jobs: dict[int, str] = {}

    def cancel(self, widget: tk.Widget) -> None:
        wid = id(widget)
        if wid in self._jobs:
            try:
                self._root.after_cancel(self._jobs[wid])
            except Exception:
                pass
            del self._jobs[wid]

    def color(self, widgets: list[tk.Widget], prop: str, target: str,
              duration: int = T_NORMAL, steps: int = 8) -> None:
        """Animate bg or fg color across widgets."""
        if not widgets:
            return
        try:
            current = widgets[0].cget("background" if prop == "bg" else "fg")
        except Exception:
            return
        if current == target:
            return
        step_ms = max(1, duration // steps)

        def tick(i: int):
            if i > steps:
                return
            c = _lerp(current, target, i / steps)
            for w in widgets:
                try:
                    if w.winfo_exists():
                        w.configure(**{prop if prop == "fg" else "bg": c})
                except Exception:
                    pass
            if i < steps:
                aid = self._root.after(step_ms, lambda: tick(i + 1))
                self._jobs[id(widgets[0])] = aid

        tick(0)

    def fade_in(self, widget: tk.Widget, target_fg: str = FG,
                duration: int = T_SLOW) -> None:
        """Simulate fade-in by transitioning fg from BG to target."""
        try:
            widget.configure(fg=BG)
        except Exception:
            return
        self.color([widget], "fg", target_fg, duration)

    def bar(self, bar_frame: tk.Frame, target: float,
            duration: int = T_SLOW) -> None:
        """Smoothly animate a progress bar relwidth."""
        try:
            current = float(bar_frame.place_info().get("relwidth", 0))
        except Exception:
            current = 0.0
        steps = 12
        step_ms = max(1, duration // steps)

        def tick(i: int):
            if i > steps or not bar_frame.winfo_exists():
                return
            t = i / steps
            ease = 1 - (1 - t) ** 3  # ease-out cubic
            w = current + (target - current) * ease
            bar_frame.place(relwidth=max(0.005, w))
            if i < steps:
                self._root.after(step_ms, lambda: tick(i + 1))

        tick(0)


# ═══════════════════════════════════════════════════════════════════════════
#  INTERACTIVE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _hoverable(anim: Animator, frame: tk.Frame, normal: str = BG_CARD,
               hover: str = BG_HOVER, on_click: Optional[Callable] = None) -> None:
    """Make frame + children respond to hover with animated transitions."""
    children = list(frame.winfo_children())
    all_w = [frame] + children

    def enter(_):
        anim.color(all_w, "bg", hover, T_FAST)

    def leave(_):
        anim.color(all_w, "bg", normal, T_FAST)

    def click(_):
        if on_click:
            anim.color(all_w, "bg", BG_PRESS, 50)
            frame.after(80, lambda: anim.color(all_w, "bg", hover, 80))
            frame.after(120, on_click)

    for w in all_w:
        w.bind("<Enter>", enter)
        w.bind("<Leave>", leave)
        if on_click:
            w.configure(cursor="hand2")
            w.bind("<Button-1>", click)


# ═══════════════════════════════════════════════════════════════════════════
#  DATA
# ═══════════════════════════════════════════════════════════════════════════

QUICK_ACTIONS = [
    ("📁", "Organizar Arquivos",  "Organizar downloads por tipo",  "organize my downloads"),
    ("📊", "Status do Sistema",   "Verificar saúde do sistema",    "my computer is slow"),
    ("🔌", "Finalizar Processo",  "Encerrar processos por porta",  "kill process on port 3000"),
    ("🌐", "Serviços Ativos",     "Ver portas e serviços",         "status"),
    ("🚀", "Iniciar Projeto",     "Detectar e iniciar servidor",   "start my backend"),
    ("📋", "Ver Logs",            "Analisar erros recentes",       "show logs"),
]

NAV_ITEMS = [
    ("🏠", "Início",        "home"),
    ("📂", "Projetos",      "projects"),
    ("📁", "Arquivos",      "files"),
    ("⚙️",  "Sistema",       "system"),
    ("🔌", "Serviços",      "services"),
    ("📋", "Histórico",     "history"),
    ("🔧", "Configurações", "settings"),
]


# ═══════════════════════════════════════════════════════════════════════════
#  SCROLLABLE FRAME
# ═══════════════════════════════════════════════════════════════════════════

class ScrollFrame(tk.Frame):
    """A scrollable frame that hides the scrollbar and supports mousewheel."""

    def __init__(self, parent, **kw):
        bg = kw.pop("bg", BG)
        super().__init__(parent, bg=bg, **kw)

        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self._canvas, bg=bg)
        self._window = self._canvas.create_window((0, 0), window=self.inner,
                                                   anchor="nw")

        self.inner.bind("<Configure>", self._on_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel
        self._canvas.bind("<Enter>", self._bind_wheel)
        self._canvas.bind("<Leave>", self._unbind_wheel)

    def _on_configure(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._window, width=e.width)

    def _bind_wheel(self, _):
        self._canvas.bind_all("<Button-4>", self._on_wheel)
        self._canvas.bind_all("<Button-5>", self._on_wheel)
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _):
        self._canvas.unbind_all("<Button-4>")
        self._canvas.unbind_all("<Button-5>")
        self._canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, e):
        if e.num == 4 or e.delta > 0:
            self._canvas.yview_scroll(-3, "units")
        elif e.num == 5 or e.delta < 0:
            self._canvas.yview_scroll(3, "units")

    def scroll_to_top(self):
        self._canvas.yview_moveto(0)



# ═══════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════

class HarmoniApp:
    """Main application — 3-column desktop interface."""

    def __init__(self) -> None:
        import time as _time
        _t0 = _time.monotonic()

        # Boot progress → splash screen
        from harmoni.ui.splash import update_splash_progress
        update_splash_progress("Inicializando…", 0, 8)

        self._bridge = HarmoniBridge(on_progress=update_splash_progress)
        self._busy = False
        self._pending: Optional[str] = None
        self._step_widgets: list[tk.Label] = []
        self._dot_id: Optional[str] = None
        self._current_page = "home"
        self._nav_frames: dict[str, tuple[tk.Frame, tk.Label]] = {}
        self._pages: dict[str, tk.Frame] = {}
        self._metrics: dict = {}
        self._secondary_panels: list = []
        # Voice
        update_splash_progress("Carregando voz…", 7, 8)
        from harmoni.infra.voice import VoiceManager
        self._voice = VoiceManager()

        update_splash_progress("Montando interface…", 8, 8)
        self._build()

        _boot_ms = (_time.monotonic() - _t0) * 1000
        import logging
        logging.getLogger(__name__).info(
            "GUI boot: %.0fms total | Bridge: %s",
            _boot_ms,
            " | ".join(f"{k}: {v:.0f}ms" for k, v in self._bridge.boot_times.items()),
        )

    # ═══════════════════════════════════════════════════════════════════════
    #  ROOT WINDOW
    # ═══════════════════════════════════════════════════════════════════════

    def _build(self) -> None:
        self.root = tk.Tk()
        self.root.title("Harmoni OS")
        self.root.configure(bg=BG)

        # CRITICAL: Hide window while building to prevent raw/unfinished flash
        self.root.withdraw()

        # Position below topbar (28px) — don't use fullscreen or zoomed
        # which may ignore the topbar strut on some WMs
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        _TOPBAR_H = 28
        self.root.geometry(f"{screen_w}x{screen_h - _TOPBAR_H}+0+{_TOPBAR_H}")
        self.root.overrideredirect(False)  # keep WM decorations off but allow strut
        self.root.bind("<F11>", lambda _: self.root.attributes(
            "-fullscreen", not self.root.attributes("-fullscreen")))
        self.root.bind("<Escape>", lambda _: self.root.attributes("-fullscreen", False))
        self.root.bind("<Control-q>", lambda _: self._quit())

        self._anim = Animator(self.root)

        # ── Fonts ──
        self._f = {
            "brand":    tkfont.Font(family="Helvetica", size=14, weight="bold"),
            "brand_s":  tkfont.Font(family="Helvetica", size=8),
            "nav":      tkfont.Font(family="Helvetica", size=11),
            "nav_btn":  tkfont.Font(family="Helvetica", size=11, weight="bold"),
            "greet":    tkfont.Font(family="Helvetica", size=24, weight="bold"),
            "sub":      tkfont.Font(family="Helvetica", size=13),
            "input":    tkfont.Font(family="Helvetica", size=16),
            "sec":      tkfont.Font(family="Helvetica", size=11, weight="bold"),
            "card_i":   tkfont.Font(family="Helvetica", size=20),
            "card_t":   tkfont.Font(family="Helvetica", size=11, weight="bold"),
            "card_d":   tkfont.Font(family="Helvetica", size=9),
            "step":     tkfont.Font(family="Helvetica", size=12),
            "res_t":    tkfont.Font(family="Helvetica", size=16, weight="bold"),
            "res_b":    tkfont.Font(family="Helvetica", size=12),
            "metric":   tkfont.Font(family="Helvetica", size=10),
            "metric_v": tkfont.Font(family="Helvetica", size=10, weight="bold"),
            "small":    tkfont.Font(family="Helvetica", size=9),
            "page_h":   tkfont.Font(family="Helvetica", size=20, weight="bold"),
            "page_s":   tkfont.Font(family="Helvetica", size=11),
            "list_t":   tkfont.Font(family="Helvetica", size=11, weight="bold"),
            "list_s":   tkfont.Font(family="Helvetica", size=9),
            "btn":      tkfont.Font(family="Helvetica", size=10, weight="bold"),
        }

        # ── 3-column grid ──
        self.root.columnconfigure(0, weight=0, minsize=SIDEBAR_W)
        self.root.columnconfigure(1, weight=1)
        self.root.columnconfigure(2, weight=0, minsize=RIGHT_W)
        self.root.rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_center()
        self._build_right_panel()

        self._entry.focus_set()
        self._poll_status()
        self._init_secondary_screens()

        # All widgets built — show window (prevents raw/unfinished flash)
        self.root.deiconify()
        self.root.update_idletasks()

    # ═══════════════════════════════════════════════════════════════════════
    #  SIDEBAR (LEFT)
    # ═══════════════════════════════════════════════════════════════════════

    def _build_sidebar(self) -> None:
        sb = tk.Frame(self.root, bg=BG_PANEL, width=SIDEBAR_W)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)

        # ── Brand ──
        brand = tk.Frame(sb, bg=BG_PANEL)
        brand.pack(fill="x", padx=SP_DEFAULT, pady=(SP_SECTION, 0))

        # Logo image (PNG) or fallback letter
        from harmoni.core.config import get_logo_path
        logo_path = get_logo_path()
        self._logo_img = None  # keep reference to prevent GC
        if logo_path:
            try:
                raw = tk.PhotoImage(file=str(logo_path))
                # Scale to ~32x32 (logo is 1024x1024, subsample by 32)
                scale = max(1, raw.width() // 32)
                self._logo_img = raw.subsample(scale, scale)
                logo_lbl = tk.Label(brand, image=self._logo_img, bg=BG_PANEL)
                logo_lbl.pack(side="left", padx=(0, SP_COMPACT))
            except Exception:
                self._logo_img = None

        if not self._logo_img:
            # Fallback: letter in purple square
            logo = tk.Frame(brand, bg=ACCENT, padx=1, pady=1)
            logo.pack(side="left", padx=(0, SP_COMPACT))
            tk.Label(logo, text=" H ", font=self._f["brand"], fg="#fff",
                     bg=ACCENT, padx=SP_MICRO, pady=2).pack()

        brand_text = tk.Frame(brand, bg=BG_PANEL)
        brand_text.pack(side="left")
        tk.Label(brand_text, text="Harmoni OS", font=self._f["brand"],
                 fg=FG, bg=BG_PANEL).pack(anchor="w")
        tk.Label(brand_text, text="AI-first interface", font=self._f["brand_s"],
                 fg=FG_DIM, bg=BG_PANEL).pack(anchor="w")

        # Separator
        tk.Frame(sb, bg=BORDER, height=1).pack(
            fill="x", padx=SP_DEFAULT, pady=(20, SP_DEFAULT))

        # ── User card ──
        uf = tk.Frame(sb, bg=BG_CARD, padx=SP_COMPACT, pady=10)
        uf.pack(fill="x", padx=SP_COMPACT, pady=(0, 10))

        avatar = tk.Label(uf, text=f" {_USER[0]} ", font=self._f["nav_btn"],
                          fg="#fff", bg=ACCENT_LT, padx=2)
        avatar.pack(side="left", padx=(0, 10))

        ui = tk.Frame(uf, bg=BG_CARD)
        ui.pack(side="left")
        tk.Label(ui, text=_USER, font=self._f["nav"],
                 fg=FG, bg=BG_CARD).pack(anchor="w")
        tk.Label(ui, text="Operador", font=self._f["small"],
                 fg=FG_DIM, bg=BG_CARD).pack(anchor="w")

        # ── Nova Intenção button ──
        btn_outer = tk.Frame(sb, bg=ACCENT, padx=1, pady=1)
        btn_outer.pack(fill="x", padx=SP_COMPACT, pady=(6, 18))
        btn_label = tk.Label(btn_outer, text="✦  Nova Intenção",
                             font=self._f["nav_btn"], fg="#fff", bg=ACCENT,
                             pady=9, cursor="hand2")
        btn_label.pack(fill="x")

        for w in [btn_outer, btn_label]:
            w.bind("<Enter>", lambda _: self._anim.color(
                [btn_outer, btn_label], "bg", ACCENT_LT, T_FAST))
            w.bind("<Leave>", lambda _: self._anim.color(
                [btn_outer, btn_label], "bg", ACCENT, T_FAST))
            w.bind("<Button-1>", lambda _: self._nav_to("home"))
            w.configure(cursor="hand2")

        # ── Nav items ──
        for icon, label, page in NAV_ITEMS:
            f, lbl = self._make_nav_item(sb, icon, label, page)
            self._nav_frames[page] = (f, lbl)

        self._set_active_nav("home")

        # ── Footer ──
        from harmoni import __version__
        tk.Label(sb, text=f"Harmoni v{__version__}", font=self._f["small"], fg=FG_DIM,
                 bg=BG_PANEL, justify="left").pack(
            side="bottom", anchor="w", padx=20, pady=20)

    def _make_nav_item(self, parent: tk.Frame, icon: str, label: str,
                       page: str) -> tuple[tk.Frame, tk.Label]:
        f = tk.Frame(parent, bg=BG_PANEL, padx=SP_COMPACT, pady=SP_TIGHT)
        f.pack(fill="x", padx=SP_TIGHT, pady=1)

        icon_lbl = tk.Label(f, text=icon, font=self._f["nav"],
                            bg=BG_PANEL, width=2)
        icon_lbl.pack(side="left", padx=(0, SP_TIGHT))

        text_lbl = tk.Label(f, text=label, font=self._f["nav"],
                            fg=FG_SEC, bg=BG_PANEL)
        text_lbl.pack(side="left")

        all_w = [f, icon_lbl, text_lbl]

        def enter(_):
            self._anim.color(all_w, "bg", BG_HOVER, T_FAST)
            self._anim.color([text_lbl], "fg", FG, T_FAST)

        def leave(_):
            if page != self._current_page:
                self._anim.color(all_w, "bg", BG_PANEL, T_FAST)
                self._anim.color([text_lbl], "fg", FG_SEC, T_FAST)

        def click(_):
            self._nav_to(page)

        for w in all_w:
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            w.bind("<Button-1>", click)
            w.configure(cursor="hand2")

        return f, text_lbl

    def _set_active_nav(self, active: str) -> None:
        for page, (frame, text_lbl) in self._nav_frames.items():
            all_w = [frame] + list(frame.winfo_children())
            if page == active:
                self._anim.color(all_w, "bg", BG_CARD, T_NORMAL)
                self._anim.color([text_lbl], "fg", FG, T_NORMAL)
            else:
                self._anim.color(all_w, "bg", BG_PANEL, T_NORMAL)
                self._anim.color([text_lbl], "fg", FG_SEC, T_NORMAL)

    # ═══════════════════════════════════════════════════════════════════════
    #  CENTER PANEL
    # ═══════════════════════════════════════════════════════════════════════

    def _build_center(self) -> None:
        self._center = tk.Frame(self.root, bg=BG)
        self._center.grid(row=0, column=1, sticky="nsew")

        self._build_page_home()
        self._build_page_projects()
        self._build_page_files()
        self._build_page_system()
        self._build_page_services()
        self._build_page_history()
        self._build_page_settings()
        self._show_page("home")

    def _make_page(self, name: str) -> tk.Frame:
        """Create a scrollable page container."""
        scroll = ScrollFrame(self._center, bg=BG)
        self._pages[name] = scroll
        # Inner content with page padding
        inner = scroll.inner
        inner.configure(padx=SP_PAGE, pady=SP_BLOCK)
        return inner

    def _show_page(self, name: str) -> None:
        for f in self._pages.values():
            f.pack_forget()
        if name in self._pages:
            self._pages[name].pack(fill="both", expand=True)
            self._pages[name].scroll_to_top()

    # ── HOME PAGE ────────────────────────────────────────────────────────

    def _build_page_home(self) -> None:
        p = self._make_page("home")

        # ── Greeting ──
        tk.Label(p, text=f"{_GREET}, {_USER}.", font=self._f["greet"],
                 fg=FG, bg=BG, anchor="w").pack(fill="x")
        tk.Label(p, text="O que vamos construir hoje?", font=self._f["sub"],
                 fg=FG_DIM, bg=BG, anchor="w").pack(
            fill="x", pady=(SP_MICRO, SP_SECTION))

        # ── Prompt ──
        self._prompt_glow = tk.Frame(p, bg=BORDER, padx=2, pady=2)
        self._prompt_glow.pack(fill="x")

        prompt_inner = tk.Frame(self._prompt_glow, bg=BG_INPUT)
        prompt_inner.pack(fill="x")

        tk.Label(prompt_inner, text="✦", font=self._f["input"],
                 fg=FG_DIM, bg=BG_INPUT).pack(
            side="left", padx=(SP_DEFAULT, 10))

        self._entry = tk.Entry(
            prompt_inner, font=self._f["input"], bg=BG_INPUT, fg=FG,
            insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=0)
        self._entry.pack(side="left", fill="x", expand=True, pady=SP_DEFAULT)
        self._entry.bind("<Return>", self._on_enter)

        # Focus glow
        self._entry.bind("<FocusIn>", lambda _: self._anim.color(
            [self._prompt_glow], "bg", ACCENT, T_NORMAL))
        self._entry.bind("<FocusOut>", lambda _: self._anim.color(
            [self._prompt_glow], "bg", BORDER, T_NORMAL))

        # Send button
        send_outer = tk.Frame(prompt_inner, bg=ACCENT, padx=1, pady=1)
        send_outer.pack(side="right", padx=(SP_TIGHT, SP_COMPACT), pady=10)
        self._send_btn_outer = send_outer
        send_btn = tk.Label(send_outer, text=" Enviar ", font=self._f["btn"],
                            fg="#fff", bg=ACCENT, pady=3, padx=SP_TIGHT,
                            cursor="hand2")
        send_btn.pack()
        self._send_btn = send_btn

        for w in [send_outer, send_btn]:
            w.bind("<Enter>", lambda _: self._anim.color(
                [send_outer, send_btn], "bg", ACCENT_LT, T_FAST))
            w.bind("<Leave>", lambda _: self._anim.color(
                [send_outer, send_btn], "bg", ACCENT, T_FAST))
            w.bind("<Button-1>", self._on_enter)
            w.configure(cursor="hand2")

        # Cancel button (hidden by default, shown when busy)
        cancel_outer = tk.Frame(prompt_inner, bg=ERROR, padx=1, pady=1)
        self._cancel_btn_outer = cancel_outer
        cancel_btn = tk.Label(cancel_outer, text=" ✕ Cancelar ", font=self._f["btn"],
                              fg="#fff", bg=ERROR, pady=3, padx=SP_TIGHT,
                              cursor="hand2")
        cancel_btn.pack()
        self._cancel_btn = cancel_btn

        for w in [cancel_outer, cancel_btn]:
            w.bind("<Enter>", lambda _: self._anim.color(
                [cancel_outer, cancel_btn], "bg", "#dc2626", T_FAST))
            w.bind("<Leave>", lambda _: self._anim.color(
                [cancel_outer, cancel_btn], "bg", ERROR, T_FAST))
            w.bind("<Button-1>", lambda _: self._on_cancel_intent())
            w.configure(cursor="hand2")

        # Cancel state
        self._cancelled = False

        # Mic button (voice input)
        self._mic_outer = tk.Frame(prompt_inner, bg=BG_CARD, padx=1, pady=1)
        self._mic_outer.pack(side="right", pady=10)
        self._mic_btn = tk.Label(self._mic_outer, text=" 🎤 ",
                                 font=self._f["btn"], fg=FG_SEC, bg=BG_CARD,
                                 pady=3, cursor="hand2")
        self._mic_btn.pack()

        for w in [self._mic_outer, self._mic_btn]:
            w.bind("<Enter>", lambda _: self._anim.color(
                [self._mic_outer, self._mic_btn], "bg", BG_HOVER, T_FAST))
            w.bind("<Leave>", lambda _: self._anim.color(
                [self._mic_outer, self._mic_btn], "bg", BG_CARD, T_FAST))
            w.bind("<Button-1>", lambda _: self._on_mic())
            w.configure(cursor="hand2")

        # Placeholder
        self._ph = True
        self._entry.insert(0, "O que você deseja que o sistema faça?")
        self._entry.configure(fg=FG_DIM)
        self._entry.bind("<FocusIn>", self._ph_clear, add="+")
        self._entry.bind("<FocusOut>", self._ph_restore, add="+")

        # ── Quick Actions ──
        tk.Label(p, text="⚡ Ações Rápidas", font=self._f["sec"],
                 fg=FG_SEC, bg=BG, anchor="w").pack(
            fill="x", pady=(SP_SECTION, SP_COMPACT))

        self._cards_frame = tk.Frame(p, bg=BG)
        self._cards_frame.pack(fill="x")
        self._build_quick_actions()

        # ── Feed (execution steps) ──
        self._feed = tk.Frame(p, bg=BG)
        self._feed.pack(fill="x", pady=(SP_DEFAULT, 0))

        # ── Confirm dialog ──
        self._confirm_frame = tk.Frame(p, bg=BG_CARD,
                                       padx=SP_SECTION, pady=SP_DEFAULT)
        self._confirm_msg = tk.Label(self._confirm_frame, font=self._f["step"],
                                     fg=FG, bg=BG_CARD, wraplength=480,
                                     justify="center")
        self._confirm_msg.pack(pady=(0, SP_COMPACT))

        btn_row = tk.Frame(self._confirm_frame, bg=BG_CARD)
        btn_row.pack()
        tk.Button(btn_row, text="Confirmar", font=self._f["btn"],
                  bg=ACCENT, fg="#fff", activebackground=ACCENT_LT,
                  activeforeground="#fff", relief="flat",
                  padx=18, pady=5, command=self._on_confirm).pack(
            side="left", padx=(0, 10))
        tk.Button(btn_row, text="Cancelar", font=self._f["btn"],
                  bg=BG_INPUT, fg=FG_DIM, activebackground=BG_HOVER,
                  activeforeground=FG, relief="flat",
                  padx=18, pady=5, command=self._on_cancel).pack(side="left")

        # ── Result ──
        self._result_frame = tk.Frame(p, bg=BG)
        self._result_frame.pack(fill="x", pady=(10, 0))
        self._res_title = tk.Label(self._result_frame, font=self._f["res_t"],
                                   bg=BG)
        self._res_body = tk.Label(self._result_frame, font=self._f["res_b"],
                                  bg=BG, fg=FG_SEC, wraplength=520,
                                  justify="center")

        # ── Activity ──
        tk.Label(p, text="🕐 Atividades Recentes", font=self._f["sec"],
                 fg=FG_SEC, bg=BG, anchor="w").pack(
            fill="x", pady=(SP_SECTION, SP_TIGHT))
        self._activity_frame = tk.Frame(p, bg=BG)
        self._activity_frame.pack(fill="x")
        self._load_activity()

    def _build_quick_actions(self) -> None:
        for i, (icon, title, desc, cmd) in enumerate(QUICK_ACTIONS):
            row, col = divmod(i, 3)

            outer = tk.Frame(self._cards_frame, bg=BORDER, padx=1, pady=1)
            outer.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            card = tk.Frame(outer, bg=BG_CARD, padx=14, pady=14)
            card.pack(fill="both", expand=True)

            lbl_i = tk.Label(card, text=icon, font=self._f["card_i"],
                             bg=BG_CARD)
            lbl_i.pack(anchor="w")
            lbl_t = tk.Label(card, text=title, font=self._f["card_t"],
                             fg=FG, bg=BG_CARD)
            lbl_t.pack(anchor="w", pady=(SP_TIGHT, 0))
            lbl_d = tk.Label(card, text=desc, font=self._f["card_d"],
                             fg=FG_DIM, bg=BG_CARD)
            lbl_d.pack(anchor="w", pady=(3, 0))

            card_widgets = [card, lbl_i, lbl_t, lbl_d]

            def mk_enter(ws, border):
                return lambda _: (
                    self._anim.color(ws, "bg", BG_HOVER, T_FAST),
                    self._anim.color([border], "bg", BORDER_LT, T_FAST))

            def mk_leave(ws, border):
                return lambda _: (
                    self._anim.color(ws, "bg", BG_CARD, T_FAST),
                    self._anim.color([border], "bg", BORDER, T_FAST))

            def mk_click(command):
                return lambda _: self._on_card(command)

            for w in card_widgets + [outer]:
                w.bind("<Enter>", mk_enter(card_widgets, outer))
                w.bind("<Leave>", mk_leave(card_widgets, outer))
                w.bind("<Button-1>", mk_click(cmd))
                w.configure(cursor="hand2")

        for c in range(3):
            self._cards_frame.columnconfigure(c, weight=1)

    # ── OTHER PAGES ──────────────────────────────────────────────────────

    def _page_header(self, parent: tk.Frame, icon: str, title: str,
                     subtitle: str) -> None:
        tk.Label(parent, text=f"{icon} {title}", font=self._f["page_h"],
                 fg=FG, bg=BG, anchor="w").pack(fill="x")
        tk.Label(parent, text=subtitle, font=self._f["page_s"],
                 fg=FG_DIM, bg=BG, anchor="w").pack(
            fill="x", pady=(SP_MICRO, SP_SECTION))

    def _build_page_projects(self) -> None:
        p = self._make_page("projects")
        self._page_header(p, "📂", "Projetos",
                          "Projetos detectados no sistema")
        self._projects_list = tk.Frame(p, bg=BG)
        self._projects_list.pack(fill="x")

    def _build_page_files(self) -> None:
        p = self._make_page("files")
        self._page_header(p, "📁", "Arquivos",
                          "Navegação rápida de diretórios")

        af = tk.Frame(p, bg=BG)
        af.pack(fill="x")
        for i, (icon, label, cmd) in enumerate([
            ("📥", "Organizar Downloads", "organize my downloads"),
            ("🖥️",  "Organizar Desktop",   "organize my desktop"),
            ("📄", "Organizar Documentos", "organize my documents"),
        ]):
            outer = tk.Frame(af, bg=BORDER, padx=1, pady=1)
            outer.grid(row=0, column=i, padx=5, pady=5, sticky="nsew")
            c = tk.Frame(outer, bg=BG_CARD, padx=14, pady=14)
            c.pack(fill="both", expand=True)
            tk.Label(c, text=icon, font=self._f["card_i"],
                     bg=BG_CARD).pack(anchor="w")
            tk.Label(c, text=label, font=self._f["card_t"],
                     fg=FG, bg=BG_CARD).pack(anchor="w", pady=(6, 0))
            _hoverable(self._anim, c,
                       on_click=lambda cm=cmd: (
                           self._on_card(cm), self._nav_to("home")))
        for col in range(3):
            af.columnconfigure(col, weight=1)

        tk.Label(p, text="📂 Diretórios", font=self._f["sec"],
                 fg=FG_SEC, bg=BG, anchor="w").pack(
            fill="x", pady=(SP_SECTION, SP_COMPACT))
        self._files_list = tk.Frame(p, bg=BG)
        self._files_list.pack(fill="x")

    def _build_page_system(self) -> None:
        p = self._make_page("system")
        self._page_header(p, "⚙️", "Sistema",
                          "Informações e saúde do sistema")
        self._system_list = tk.Frame(p, bg=BG)
        self._system_list.pack(fill="x")

        tk.Label(p, text="🔧 Ações do Sistema", font=self._f["sec"],
                 fg=FG_SEC, bg=BG, anchor="w").pack(
            fill="x", pady=(SP_SECTION, SP_COMPACT))

        af = tk.Frame(p, bg=BG)
        af.pack(fill="x")
        for i, (icon, label, cmd) in enumerate([
            ("📊", "Diagnóstico",   "my computer is slow"),
            ("🧹", "Limpar Sistema", "free disk space"),
            ("📋", "Ver Logs",       "show logs"),
        ]):
            outer = tk.Frame(af, bg=BORDER, padx=1, pady=1)
            outer.grid(row=0, column=i, padx=5, pady=5, sticky="nsew")
            c = tk.Frame(outer, bg=BG_CARD, padx=14, pady=14)
            c.pack(fill="both", expand=True)
            tk.Label(c, text=icon, font=self._f["card_i"],
                     bg=BG_CARD).pack(anchor="w")
            tk.Label(c, text=label, font=self._f["card_t"],
                     fg=FG, bg=BG_CARD).pack(anchor="w", pady=(6, 0))
            _hoverable(self._anim, c,
                       on_click=lambda cm=cmd: (
                           self._on_card(cm), self._nav_to("home")))
        for col in range(3):
            af.columnconfigure(col, weight=1)

    def _build_page_services(self) -> None:
        p = self._make_page("services")
        self._page_header(p, "🔌", "Serviços",
                          "Portas e processos ativos")
        self._services_list = tk.Frame(p, bg=BG)
        self._services_list.pack(fill="x")

        rf = tk.Frame(p, bg=ACCENT, padx=1, pady=1)
        rf.pack(anchor="w", pady=(SP_DEFAULT, 0))
        rb = tk.Label(rf, text=" 🔄 Atualizar ", font=self._f["btn"],
                      fg="#fff", bg=ACCENT, pady=6, cursor="hand2")
        rb.pack()
        _hoverable(self._anim, rf, ACCENT, ACCENT_LT,
                   on_click=self._load_services)

    def _build_page_history(self) -> None:
        p = self._make_page("history")
        self._page_header(p, "📋", "Histórico",
                          "Todas as ações executadas")
        self._history_list = tk.Frame(p, bg=BG)
        self._history_list.pack(fill="x")

    def _build_page_settings(self) -> None:
        p = self._make_page("settings")
        self._page_header(p, "🔧", "Configurações",
                          "Provedor de IA e chaves de API")

        from harmoni.core import config

        self._settings_entries: dict[str, tk.Entry] = {}
        self._settings_provider = tk.StringVar(value=config.get("llm_provider"))

        # ── Provider selector ──
        tk.Label(p, text="🤖 Provedor de IA", font=self._f["sec"],
                 fg=FG_SEC, bg=BG, anchor="w").pack(
            fill="x", pady=(0, SP_COMPACT))

        providers = [
            ("ollama",    "Ollama (local, gratuito)"),
            ("openai",    "OpenAI (GPT-4o)"),
            ("anthropic", "Anthropic (Claude)"),
            ("bedrock",   "AWS Bedrock (Claude via AWS)"),
        ]

        prov_frame = tk.Frame(p, bg=BG)
        prov_frame.pack(fill="x", pady=(0, SP_SECTION))

        for i, (value, label) in enumerate(providers):
            rb = tk.Radiobutton(
                prov_frame, text=label, variable=self._settings_provider,
                value=value, font=self._f["metric"], fg=FG_SEC, bg=BG,
                selectcolor=BG_CARD, activebackground=BG,
                activeforeground=FG, highlightthickness=0,
                command=self._on_provider_change)
            rb.grid(row=i // 2, column=i % 2, sticky="w",
                    padx=(0, SP_SECTION), pady=2)

        # ── Config sections ──
        self._settings_sections: dict[str, tk.Frame] = {}

        # Ollama
        self._settings_sections["ollama"] = self._settings_section(p, "Ollama", [
            ("ollama_url",   "URL do servidor",  False),
            ("ollama_model", "Modelo",            False),
        ])

        # OpenAI
        self._settings_sections["openai"] = self._settings_section(p, "OpenAI", [
            ("openai_api_key", "API Key",  True),
            ("openai_model",   "Modelo",   False),
        ])

        # Anthropic
        self._settings_sections["anthropic"] = self._settings_section(p, "Anthropic", [
            ("anthropic_api_key", "API Key",  True),
            ("anthropic_model",   "Modelo",   False),
        ])

        # Bedrock
        self._settings_sections["bedrock"] = self._settings_section(p, "AWS Bedrock", [
            ("aws_access_key_id",     "Access Key ID",     True),
            ("aws_secret_access_key", "Secret Access Key", True),
            ("bedrock_region",        "Região",            False),
            ("bedrock_model_id",      "Model ID",          False),
        ])

        # Show only the active provider section
        self._on_provider_change()

        # ── Buttons ──
        btn_frame = tk.Frame(p, bg=BG)
        btn_frame.pack(fill="x", pady=(SP_SECTION, SP_COMPACT))

        save_outer = tk.Frame(btn_frame, bg=ACCENT, padx=1, pady=1)
        save_outer.pack(side="left", padx=(0, SP_COMPACT))
        save_btn = tk.Label(save_outer, text=" 💾 Salvar ", font=self._f["btn"],
                            fg="#fff", bg=ACCENT, pady=5, padx=SP_COMPACT,
                            cursor="hand2")
        save_btn.pack()
        _hoverable(self._anim, save_outer, ACCENT, ACCENT_LT,
                   on_click=self._save_settings)

        test_outer = tk.Frame(btn_frame, bg=BG_CARD, padx=1, pady=1)
        test_outer.pack(side="left")
        test_btn = tk.Label(test_outer, text=" 🔌 Testar Conexão ",
                            font=self._f["btn"], fg=FG_SEC, bg=BG_CARD,
                            pady=5, padx=SP_COMPACT, cursor="hand2")
        test_btn.pack()
        _hoverable(self._anim, test_outer, BG_CARD, BG_HOVER,
                   on_click=self._test_provider)

        # ── Status feedback ──
        self._settings_status = tk.Label(p, text="", font=self._f["metric"],
                                         fg=FG_DIM, bg=BG, anchor="w")
        self._settings_status.pack(fill="x", pady=(SP_COMPACT, 0))

        # ── General settings ──
        tk.Frame(p, bg=BORDER, height=1).pack(
            fill="x", pady=(SP_SECTION, SP_DEFAULT))

        tk.Label(p, text="⚙️ Geral", font=self._f["sec"],
                 fg=FG_SEC, bg=BG, anchor="w").pack(
            fill="x", pady=(0, SP_COMPACT))

        general = [
            ("Timeout de Comandos", "120s"),
            ("Máximo de Retries",   "1"),
            ("Diretório de Dados",  str(config.HARMONI_HOME)),
            ("Interface",           "Tkinter (nativa)"),
        ]
        for label, value in general:
            row = tk.Frame(p, bg=BG_CARD, padx=SP_DEFAULT, pady=SP_COMPACT)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, font=self._f["metric"],
                     fg=FG_SEC, bg=BG_CARD).pack(side="left")
            tk.Label(row, text=value, font=self._f["metric_v"],
                     fg=FG, bg=BG_CARD).pack(side="right")

    def _settings_section(self, parent: tk.Frame, title: str,
                          fields: list[tuple[str, str, bool]]) -> tk.Frame:
        """Create a settings section with labeled entry fields.

        Args:
            fields: list of (config_key, label, is_secret)
        """
        from harmoni.core import config

        frame = tk.Frame(parent, bg=BG)

        tk.Label(frame, text=title, font=self._f["list_t"],
                 fg=FG, bg=BG, anchor="w").pack(
            fill="x", pady=(0, SP_TIGHT))

        for key, label, is_secret in fields:
            row = tk.Frame(frame, bg=BG_CARD, padx=SP_DEFAULT, pady=10)
            row.pack(fill="x", pady=2)

            tk.Label(row, text=label, font=self._f["metric"],
                     fg=FG_SEC, bg=BG_CARD, width=18,
                     anchor="w").pack(side="left")

            entry = tk.Entry(row, font=self._f["metric"], bg=BG_INPUT,
                             fg=FG, insertbackground=ACCENT, relief="flat",
                             bd=0, highlightthickness=0)
            if is_secret:
                entry.configure(show="•")
            entry.pack(side="left", fill="x", expand=True, padx=(SP_TIGHT, 0))

            # Load current value
            current = config.get(key)
            if current:
                entry.insert(0, str(current))

            self._settings_entries[key] = entry

            # Toggle visibility for secret fields
            if is_secret:
                vis_btn = tk.Label(row, text="👁", font=self._f["small"],
                                   fg=FG_DIM, bg=BG_CARD, cursor="hand2")
                vis_btn.pack(side="right", padx=(SP_TIGHT, 0))

                def make_toggle(e=entry, b=vis_btn):
                    def toggle(_=None):
                        if e.cget("show") == "•":
                            e.configure(show="")
                            b.configure(text="🔒")
                        else:
                            e.configure(show="•")
                            b.configure(text="👁")
                    return toggle

                vis_btn.bind("<Button-1>", make_toggle())

        return frame

    def _on_provider_change(self) -> None:
        """Show/hide settings sections based on selected provider."""
        active = self._settings_provider.get()
        for name, frame in self._settings_sections.items():
            if name == active:
                frame.pack(fill="x", pady=(0, SP_COMPACT))
            else:
                frame.pack_forget()

    def _save_settings(self) -> None:
        """Save all settings to disk."""
        from harmoni.core import config

        config.set("llm_provider", self._settings_provider.get())

        for key, entry in self._settings_entries.items():
            value = entry.get().strip()
            config.set(key, value)

        config.save()
        self._settings_status.configure(
            text="✓ Configurações salvas", fg=SUCCESS)
        self.root.after(3000, lambda: self._settings_status.configure(
            text="", fg=FG_DIM))

    def _test_provider(self) -> None:
        """Test the selected provider connection."""
        from harmoni.core.model_router import check_provider

        provider = self._settings_provider.get()
        self._settings_status.configure(
            text=f"Testando {provider}...", fg=FG_SEC)

        # Save current values first so the test uses them
        self._save_settings()

        def run():
            success, msg = check_provider(provider)
            color = SUCCESS if success else ERROR
            self.root.after(0, lambda: self._settings_status.configure(
                text=f"{'✓' if success else '✗'} {msg}", fg=color))

        import threading
        threading.Thread(target=run, daemon=True).start()


    # ═══════════════════════════════════════════════════════════════════════
    #  RIGHT PANEL
    # ═══════════════════════════════════════════════════════════════════════

    def _build_right_panel(self) -> None:
        rp = tk.Frame(self.root, bg=BG_PANEL, width=RIGHT_W)
        rp.grid(row=0, column=2, sticky="nsew")
        rp.grid_propagate(False)

        # ── System Status ──
        tk.Label(rp, text="📈 Status do Sistema", font=self._f["sec"],
                 fg=FG_SEC, bg=BG_PANEL, anchor="w").pack(
            fill="x", padx=SP_DEFAULT, pady=(SP_SECTION, SP_DEFAULT))

        for key, label, color in [
            ("cpu",  "CPU",     ACCENT),
            ("mem",  "Memória", CYAN),
            ("disk", "Disco",   SUCCESS),
            ("net",  "Rede",    WARNING),
        ]:
            mf = tk.Frame(rp, bg=BG_CARD, padx=14, pady=SP_COMPACT)
            mf.pack(fill="x", padx=SP_COMPACT, pady=3)

            hdr = tk.Frame(mf, bg=BG_CARD)
            hdr.pack(fill="x")
            tk.Label(hdr, text=label, font=self._f["metric"],
                     fg=FG_SEC, bg=BG_CARD).pack(side="left")
            val = tk.Label(hdr, text="--", font=self._f["metric_v"],
                           fg=FG, bg=BG_CARD)
            val.pack(side="right")

            bar_bg = tk.Frame(mf, bg=BORDER, height=5)
            bar_bg.pack(fill="x", pady=(SP_TIGHT, 0))
            bar_fill = tk.Frame(bar_bg, bg=color, height=5)
            bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0.005)

            self._metrics[key] = {
                "val": val, "fill": bar_fill, "color": color}

        # ── Separator ──
        tk.Frame(rp, bg=BORDER, height=1).pack(
            fill="x", padx=SP_DEFAULT, pady=(SP_DEFAULT, SP_COMPACT))

        # ── Environment ──
        env_text = (f"Host: {platform.node()}\n"
                    f"Kernel: {platform.release()}\n"
                    f"Interface: Tkinter")
        tk.Label(rp, text=env_text, font=self._f["small"], fg=FG_DIM,
                 bg=BG_PANEL, justify="left").pack(
            anchor="w", padx=20)

        # ── Security badge ──
        badge = tk.Frame(rp, bg=SUCCESS_BG, padx=SP_COMPACT, pady=9)
        badge.pack(fill="x", padx=SP_COMPACT, pady=(SP_DEFAULT, SP_COMPACT))
        tk.Label(badge, text="🛡️  Tudo sob controle", font=self._f["metric"],
                 fg=SUCCESS, bg=SUCCESS_BG).pack(anchor="w")

        # ── Suggestions ──
        tk.Label(rp, text="💡 Sugestões", font=self._f["sec"],
                 fg=FG_SEC, bg=BG_PANEL, anchor="w").pack(
            fill="x", padx=SP_DEFAULT, pady=(SP_DEFAULT, SP_COMPACT))

        for icon, text, cmd in [
            ("📁", "Organizar downloads",  "organize my downloads"),
            ("🔍", "Verificar performance", "my computer is slow"),
            ("📋", "Revisar logs",          "show logs"),
        ]:
            sf = tk.Frame(rp, bg=BG_CARD, padx=SP_COMPACT, pady=9)
            sf.pack(fill="x", padx=SP_COMPACT, pady=2)
            tk.Label(sf, text=icon, font=self._f["metric"],
                     bg=BG_CARD).pack(side="left", padx=(0, SP_TIGHT))
            tk.Label(sf, text=text, font=self._f["metric"],
                     fg=FG_SEC, bg=BG_CARD).pack(side="left")
            _hoverable(self._anim, sf,
                       on_click=lambda c=cmd: self._on_card(c))

    # ═══════════════════════════════════════════════════════════════════════
    #  NAVIGATION
    # ═══════════════════════════════════════════════════════════════════════

    def _nav_to(self, page: str) -> None:
        if page == self._current_page and page == "home":
            self._entry.focus_set()
            return
        self._current_page = page
        self._set_active_nav(page)
        self._show_page(page)

        loaders = {
            "home":     self._load_activity,
            "projects": self._load_projects,
            "files":    self._load_files,
            "system":   self._load_system,
            "services": self._load_services,
            "history":  self._load_history,
        }
        if page in loaders:
            threading.Thread(target=loaders[page], daemon=True).start()
        if page == "home":
            self._entry.focus_set()

    # ═══════════════════════════════════════════════════════════════════════
    #  DATA LOADERS
    # ═══════════════════════════════════════════════════════════════════════

    def _clear_frame(self, frame: tk.Frame) -> None:
        for w in frame.winfo_children():
            w.destroy()

    def _list_card(self, parent: tk.Frame, icon: str, title: str,
                   sub: str, action_text: str = "",
                   action_cmd: str = "") -> None:
        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="x", pady=2)

        row = tk.Frame(outer, bg=BG_CARD, padx=14, pady=11)
        row.pack(fill="both")

        tk.Label(row, text=icon, font=self._f["card_i"],
                 bg=BG_CARD).pack(side="left", padx=(0, SP_COMPACT))

        body = tk.Frame(row, bg=BG_CARD)
        body.pack(side="left", fill="x", expand=True)
        tk.Label(body, text=title, font=self._f["list_t"],
                 fg=FG, bg=BG_CARD, anchor="w").pack(fill="x")
        if sub:
            tk.Label(body, text=sub, font=self._f["list_s"],
                     fg=FG_DIM, bg=BG_CARD, anchor="w").pack(fill="x")

        if action_text:
            btn_f = tk.Frame(row, bg=ACCENT, padx=1, pady=1)
            btn_f.pack(side="right", padx=(10, 0))
            btn = tk.Label(btn_f, text=f" {action_text} ",
                           font=self._f["btn"], fg="#fff", bg=ACCENT,
                           pady=2, cursor="hand2")
            btn.pack()
            _hoverable(self._anim, btn_f, ACCENT, ACCENT_LT,
                       on_click=lambda c=action_cmd: (
                           self._on_card(c), self._nav_to("home")))

    def _load_projects(self) -> None:
        from harmoni.ui.gui_web import _get_projects
        data = _get_projects()

        def render():
            self._clear_frame(self._projects_list)
            if not data:
                self._list_card(self._projects_list, "📭",
                                "Nenhum projeto detectado",
                                "Navegue até um diretório com package.json "
                                "ou requirements.txt")
                return
            for proj in data:
                icon = "🟢" if proj["type"] == "node" else "🐍"
                self._list_card(self._projects_list, icon,
                                proj["name"], proj["path"],
                                "Iniciar", "start my backend")
        self.root.after(0, render)

    def _load_files(self) -> None:
        from harmoni.ui.gui_web import _get_directories
        data = _get_directories()

        def render():
            self._clear_frame(self._files_list)
            for f in data:
                self._list_card(self._files_list, f["icon"],
                                f["name"], f"{f['count']} itens")
        self.root.after(0, render)

    def _load_system(self) -> None:
        data = self._bridge.get_system_status()

        def render():
            self._clear_frame(self._system_list)
            self._list_card(self._system_list, "💻", "Processador",
                            f"{data['cpu_cores']} cores · "
                            f"{data['cpu_percent']}% em uso")
            self._list_card(self._system_list, "🧠", "Memória",
                            f"{data['mem_used_gb']} / "
                            f"{data['mem_total_gb']} GB "
                            f"({data['mem_percent']}%)")
            self._list_card(self._system_list, "💾", "Disco",
                            f"{data['disk_free_gb']} GB livre de "
                            f"{data['disk_total_gb']} GB")
            self._list_card(self._system_list, "🌐", "Rede",
                            f"↑ {data['net_sent_mb']} MB  "
                            f"↓ {data['net_recv_mb']} MB")
            self._list_card(self._system_list, "🖥️", "Host",
                            f"{data['hostname']} · "
                            f"Kernel {data['kernel']}")
        self.root.after(0, render)

    def _load_services(self) -> None:
        from harmoni.ui.gui_web import _get_services
        data = _get_services()

        def render():
            self._clear_frame(self._services_list)
            if not data:
                self._list_card(self._services_list, "😴",
                                "Nenhum serviço ativo", "")
                return
            for s in data:
                self._list_card(
                    self._services_list, "🔌",
                    f"Porta {s['port']}",
                    f"{s['name']} · PID {s.get('pid', '?')}",
                    "Encerrar",
                    f"kill process on port {s['port']}")
        self.root.after(0, render)

    def _load_history(self) -> None:
        data = self._bridge.get_recent_activity()

        def render():
            self._clear_frame(self._history_list)
            if not data:
                tk.Label(self._history_list,
                         text="Nenhuma atividade registrada",
                         font=self._f["step"], fg=FG_DIM,
                         bg=BG).pack(anchor="w", pady=SP_TIGHT)
                return
            for it in data:
                c = (SUCCESS if it["outcome"] == "success"
                     else WARNING if it["outcome"] == "recovered"
                     else ERROR)
                row = tk.Frame(self._history_list, bg=BG_CARD,
                               padx=SP_COMPACT, pady=9)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=it["icon"], font=self._f["step"],
                         fg=c, bg=BG_CARD).pack(
                    side="left", padx=(0, 10))
                tk.Label(row, text=it["text"], font=self._f["list_s"],
                         fg=FG_SEC, bg=BG_CARD).pack(
                    side="left", fill="x", expand=True)
                tk.Label(row, text=it["time"], font=self._f["small"],
                         fg=FG_DIM, bg=BG_CARD).pack(side="right")
        self.root.after(0, render)

    def _load_activity(self) -> None:
        data = self._bridge.get_recent_activity()

        def render():
            self._clear_frame(self._activity_frame)
            if not data:
                tk.Label(self._activity_frame,
                         text="Nenhuma atividade ainda",
                         font=self._f["small"], fg=FG_DIM,
                         bg=BG).pack(anchor="w")
                return
            for it in data:
                c = (SUCCESS if it["outcome"] == "success"
                     else WARNING if it["outcome"] == "recovered"
                     else ERROR)
                row = tk.Frame(self._activity_frame, bg=BG_CARD,
                               padx=SP_COMPACT, pady=7)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=it["icon"], font=self._f["step"],
                         fg=c, bg=BG_CARD).pack(
                    side="left", padx=(0, 10))
                tk.Label(row, text=it["text"], font=self._f["list_s"],
                         fg=FG_SEC, bg=BG_CARD).pack(
                    side="left", fill="x", expand=True)
                tk.Label(row, text=it["time"], font=self._f["small"],
                         fg=FG_DIM, bg=BG_CARD).pack(side="right")
        self.root.after(0, render)

    # ═══════════════════════════════════════════════════════════════════════
    #  STATUS POLLING
    # ═══════════════════════════════════════════════════════════════════════

    def _poll_status(self) -> None:
        def update():
            try:
                d = self._bridge.get_system_status()
                self.root.after(0, lambda: self._update_metrics(d))
            except Exception:
                pass
        threading.Thread(target=update, daemon=True).start()
        self.root.after(5000, self._poll_status)

    def _update_metrics(self, d: dict) -> None:
        m = self._metrics
        # CPU
        m["cpu"]["val"].configure(text=f"{d['cpu_percent']}%")
        self._anim.bar(m["cpu"]["fill"], d["cpu_percent"] / 100)
        # Memory
        m["mem"]["val"].configure(
            text=f"{d['mem_used_gb']}/{d['mem_total_gb']} GB")
        self._anim.bar(m["mem"]["fill"], d["mem_percent"] / 100)
        # Disk
        m["disk"]["val"].configure(text=f"{d['disk_free_gb']} GB livre")
        self._anim.bar(m["disk"]["fill"], d["disk_percent"] / 100)
        # Network
        m["net"]["val"].configure(
            text=f"↑{d['net_sent_mb']} ↓{d['net_recv_mb']} MB")
        self._anim.bar(m["net"]["fill"], 0.3)

    # ═══════════════════════════════════════════════════════════════════════
    #  INPUT / EXECUTION
    # ═══════════════════════════════════════════════════════════════════════

    def _ph_clear(self, _) -> None:
        if self._ph:
            self._entry.delete(0, "end")
            self._anim.color([self._entry], "fg", FG, T_NORMAL)
            self._ph = False

    def _ph_restore(self, _) -> None:
        if not self._entry.get().strip():
            self._entry.insert(0, "O que você deseja que o sistema faça?")
            self._anim.color([self._entry], "fg", FG_DIM, T_NORMAL)
            self._ph = True

    def _on_enter(self, _=None) -> None:
        if self._busy:
            return
        text = self._entry.get().strip()
        if not text or self._ph:
            return
        if self._current_page != "home":
            self._nav_to("home")
        self._submit(text)

    def _on_mic(self) -> None:
        """Start voice input — record, transcribe, execute."""
        if self._busy or not self._voice.stt_available:
            return
        if self._voice.is_listening:
            return

        # Visual feedback: mic button glows
        self._anim.color([self._mic_outer, self._mic_btn], "bg", ACCENT, T_FAST)
        self._mic_btn.configure(text=" 🔴 ", fg="#fff")

        if self._current_page != "home":
            self._nav_to("home")

        # Clear and show listening state
        if self._ph:
            self._ph_clear(None)
        self._entry.delete(0, "end")
        self._entry.insert(0, "Escutando...")
        self._entry.configure(fg=ACCENT_LT)

        def on_result(text: Optional[str]):
            # Reset mic button
            self.root.after(0, lambda: (
                self._anim.color(
                    [self._mic_outer, self._mic_btn], "bg", BG_CARD, T_FAST),
                self._mic_btn.configure(text=" 🎤 ", fg=FG_SEC),
            ))

            if text:
                self.root.after(0, lambda: self._entry.delete(0, "end"))
                self.root.after(0, lambda: self._entry.insert(0, text))
                self.root.after(0, lambda: self._entry.configure(fg=FG))
                self.root.after(100, lambda: self._submit(text))
            else:
                self.root.after(0, lambda: self._entry.delete(0, "end"))
                self.root.after(0, lambda: self._ph_restore(None))

        self._voice.listen_async(on_result, duration=5.0)

    def _on_card(self, cmd: str) -> None:
        if self._busy:
            return
        if self._current_page != "home":
            self._nav_to("home")
        if self._ph:
            self._ph_clear(None)
        self._entry.delete(0, "end")
        self._entry.insert(0, cmd)
        self._entry.configure(fg=FG)
        self._submit(cmd)

    def _submit(self, text: str) -> None:
        self._busy = True
        self._cancelled = False
        self._entry.configure(state="disabled")
        # Swap send → cancel button
        self._send_btn_outer.pack_forget()
        self._cancel_btn_outer.pack(side="right", padx=(SP_TIGHT, SP_COMPACT), pady=10)
        self._clear_feed()
        self._clear_result()
        self._confirm_frame.pack_forget()
        self._cards_frame.pack_forget()
        self._add_step("Entendendo…", thinking=True)
        threading.Thread(target=self._run, args=(text,), daemon=True).start()

    def _run(self, text: str) -> None:
        data = self._bridge.execute_command(text)
        if data.get("confirm"):
            self.root.after(0, lambda: self._show_confirm(
                data["confirm"], text))
            return
        self._display(data)

    def _on_confirm(self) -> None:
        cmd = self._pending
        self._pending = None
        self._confirm_frame.pack_forget()
        if not cmd:
            return
        self._busy = True
        self._cancelled = False
        self._entry.configure(state="disabled")
        # Swap send → cancel
        self._send_btn_outer.pack_forget()
        self._cancel_btn_outer.pack(side="right", padx=(SP_TIGHT, SP_COMPACT), pady=10)
        self._clear_feed()
        self._clear_result()
        self._add_step("Executando…", thinking=True)
        threading.Thread(
            target=lambda: self._display(
                self._bridge.execute_command(cmd, confirmed=True)),
            daemon=True).start()

    def _on_cancel(self) -> None:
        self._pending = None
        self._confirm_frame.pack_forget()
        self._show_result("Cancelado", "Nenhuma alteração feita", "success")
        self._finish()

    def _on_cancel_intent(self) -> None:
        """Cancel a running intent execution."""
        self._cancelled = True
        if self._dot_id:
            self.root.after_cancel(self._dot_id)
            self._dot_id = None
        self._clear_feed()
        self._show_result("Cancelado", "", "success")
        self._finish()

    def _display(self, data: dict) -> None:
        # If user cancelled while we were executing, discard the result
        if self._cancelled:
            return
        steps = data.get("steps", [])
        result_text = data.get("result", "")
        status = data.get("status", "success")
        voice_mode = data.get("voice_mode", "full")

        self.root.after(0, self._clear_feed)

        for i, s in enumerate(steps):
            self.root.after(i * T_STEP, lambda s=s: self._add_step(s))

        delay = len(steps) * T_STEP + T_SLOW
        titles = {
            "success": "Concluído",
            "recovered": "Corrigido",
            "error": "Problema",
        }

        self.root.after(delay, self._dim_steps)
        self.root.after(delay + 80, lambda: self._show_result(
            titles.get(status, "Concluído"), result_text, status))
        self.root.after(delay + 150, self._finish)

        # Voice output (async, never blocks)
        if result_text:
            self.root.after(delay + 200, lambda: self._voice.speak(
                result_text, voice_mode))

    # ── Feed ─────────────────────────────────────────────────────────────

    def _clear_feed(self) -> None:
        if self._dot_id:
            self.root.after_cancel(self._dot_id)
            self._dot_id = None
        for w in self._step_widgets:
            w.destroy()
        self._step_widgets.clear()

    def _add_step(self, text: str, thinking: bool = False) -> None:
        lbl = tk.Label(self._feed, text=f"  {text}", font=self._f["step"],
                       fg=BG, bg=BG, anchor="w")
        lbl.pack(fill="x", pady=3)
        self._step_widgets.append(lbl)

        target = FG_DIM if thinking else FG_SEC
        self._anim.color([lbl], "fg", target, T_SLOW)

        if thinking:
            self._animate_dots(lbl, text.rstrip("…").rstrip("."))

    def _animate_dots(self, lbl: tk.Label, base: str, n: int = 0) -> None:
        if not lbl.winfo_exists():
            return
        dots = "." * ((n % 3) + 1)
        lbl.configure(text=f"  {base}{dots}")
        self._dot_id = self.root.after(
            T_DOTS, lambda: self._animate_dots(lbl, base, n + 1))

    def _dim_steps(self) -> None:
        for lbl in self._step_widgets:
            if lbl.winfo_exists():
                self._anim.color([lbl], "fg", FG_DIM, T_NORMAL)

    # ── Result ───────────────────────────────────────────────────────────

    def _clear_result(self) -> None:
        self._res_title.pack_forget()
        self._res_body.pack_forget()

    def _show_result(self, title: str, body: str, status: str) -> None:
        colors = {"success": SUCCESS, "recovered": WARNING, "error": ERROR}
        icons = {"success": "✓", "recovered": "✓", "error": "✗"}
        color = colors.get(status, SUCCESS)
        icon = icons.get(status, "✓")

        self._res_title.configure(text=f"{icon}  {title}", fg=BG)
        self._res_title.pack(pady=(0, SP_MICRO))
        self._anim.color([self._res_title], "fg", color, T_SLOW)

        if body:
            self._res_body.configure(text=body, fg=BG)
            self._res_body.pack()
            self._anim.color([self._res_body], "fg", FG_SEC, T_SLOW)

    def _show_confirm(self, msg: str, cmd: str) -> None:
        self._pending = cmd
        self._confirm_msg.configure(text=msg)
        self._confirm_frame.pack(fill="x", pady=(SP_DEFAULT, 0))
        if self._dot_id:
            self.root.after_cancel(self._dot_id)
            self._dot_id = None
        self._clear_feed()
        self._busy = False
        self._entry.configure(state="normal")

    def _finish(self) -> None:
        self._busy = False
        self._cancelled = False
        self._entry.configure(state="normal")
        self._entry.delete(0, "end")
        self._entry.focus_set()
        # Swap cancel → send button
        self._cancel_btn_outer.pack_forget()
        self._send_btn_outer.pack(side="right", padx=(SP_TIGHT, SP_COMPACT), pady=10)
        self._ph = False
        # Re-show cards
        self._cards_frame.pack(fill="x", before=self._feed)
        # Refresh activity
        threading.Thread(target=self._load_activity, daemon=True).start()

    # ═══════════════════════════════════════════════════════════════════════
    #  LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════════

    def _quit(self) -> None:
        for panel in self._secondary_panels:
            panel.close()
        self._voice.close()
        self._bridge.close()
        self.root.destroy()

    def _init_secondary_screens(self) -> None:
        """Detect secondary monitors and spawn context panels."""
        import logging as _log
        _logger = _log.getLogger(__name__)
        try:
            from harmoni.infra.monitors import get_secondary_monitors
            from harmoni.ui.gui_secondary import SecondaryPanel

            secondaries = get_secondary_monitors()
            if secondaries:
                _logger.info("Found %d secondary monitor(s)", len(secondaries))
            for monitor in secondaries:
                try:
                    panel = SecondaryPanel(self.root, monitor)
                    self._secondary_panels.append(panel)
                    _logger.info("Secondary panel on %s (%dx%d+%d+%d)",
                                 monitor.name, monitor.width, monitor.height,
                                 monitor.x, monitor.y)
                except Exception as e:
                    _logger.warning("Failed to create panel on %s: %s",
                                    monitor.name, e)
        except Exception as e:
            _logger.warning("Secondary screen init failed: %s", e)

    def run(self) -> None:
        # Auto-start topbar as a daemon thread (always visible in session)
        from harmoni.ui.topbar import start_topbar_thread
        self._topbar_thread = start_topbar_thread()

        # Signal splash screen to close (we're rendered and ready)
        self.root.after(100, self._signal_ready)
        self.root.mainloop()

    def _signal_ready(self) -> None:
        """Tell the splash screen we're ready — it can close now."""
        try:
            from harmoni.ui.splash import signal_splash_done
            signal_splash_done()
        except Exception:
            pass


def run_gui() -> None:
    HarmoniApp().run()
