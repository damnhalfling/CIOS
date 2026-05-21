"""CIOS — Native Desktop Interface.

Intent-first, single-surface design:
- Prompt always at bottom (multiline, Shift+Enter for newlines)
- Results appear above prompt and persist until next command
- Processing spinner (rotating arc + pulsing dot) only when thinking
- System status panel on the right (CPU, memory, disk, network)
- No sidebar, no menus, no page navigation
- Last 3 activities shown below prompt

State ring communicates system status without words.
Everything fades, nothing snaps. Conversation, not dashboard.
"""

import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import font as tkfont

from cios.core.bridge import CIOSBridge
from cios.ui.gallery_component import GalleryComponent
from cios.ui.theme import (
    ACCENT,
    ACCENT_DK,
    ACCENT_LT,
    BG,
    BG_CARD,
    BG_HOVER,
    BG_INPUT,
    BG_PANEL,
    BG_PRESS,
    BORDER,
    CYAN,
    ERROR,
    FG,
    FG_DIM,
    FG_SEC,
    RIGHT_W,
    RING_ERROR,
    RING_IDLE,
    RING_SUCCESS,
    SP_BLOCK,
    SP_COMPACT,
    SP_DEFAULT,
    SP_MICRO,
    SP_PAGE,
    SP_SECTION,
    SP_TIGHT,
    SUCCESS,
    T_DOTS,
    T_FAST,
    T_NORMAL,
    T_RING,
    T_SLOW,
    T_STEP,
    WARNING,
    hex2rgb,
    lerp,
    rgb2hex,
)
from cios.ui.theme import (
    GREETING as _GREET,
)
from cios.ui.theme import (
    USER as _USER,
)

# ═══════════════════════════════════════════════════════════════════════════
#  COLOR UTILITIES (delegated to theme.py)
# ═══════════════════════════════════════════════════════════════════════════

_hex2rgb = hex2rgb
_rgb2hex = rgb2hex
_lerp = lerp


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

    def color(
        self,
        widgets: list[tk.Widget],
        prop: str,
        target: str,
        duration: int = T_NORMAL,
        steps: int = 8,
    ) -> None:
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

    def fade_in(self, widget: tk.Widget, target_fg: str = FG, duration: int = T_SLOW) -> None:
        """Simulate fade-in by transitioning fg from BG to target."""
        try:
            widget.configure(fg=BG)
        except Exception:
            return
        self.color([widget], "fg", target_fg, duration)

    def bar(self, bar_frame: tk.Frame, target: float, duration: int = T_SLOW) -> None:
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


def _hoverable(
    anim: Animator,
    frame: tk.Frame,
    normal: str = BG_CARD,
    hover: str = BG_HOVER,
    on_click: Callable | None = None,
) -> None:
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

QUICK_CHIPS = [
    ("📁 Organizar", "organize my downloads"),
    ("📊 Diagnóstico", "my computer is slow"),
    ("🚀 Projeto", "start my backend"),
    ("🔌 Processos", "kill process on port 3000"),
    ("📋 Logs", "show logs"),
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
        self._window = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")

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
#  STATE RING — Visual heartbeat of the system
# ═══════════════════════════════════════════════════════════════════════════


class StateRing:
    """Animated ring that communicates system state without words.

    States:
    - idle: gentle pulse (breathe) in accent color
    - processing: rotating gradient animation
    - success: brief green flash then back to idle
    - error: brief red flash then back to idle
    """

    def __init__(self, parent: tk.Frame, size: int = 48) -> None:
        self._parent = parent
        self._size = size
        self._canvas = tk.Canvas(parent, width=size, height=size, bg=BG, highlightthickness=0, bd=0)
        self._state = "idle"
        self._phase = 0.0
        self._anim_id: str | None = None
        self._ring_id = None
        self._symbol_id = None
        self._draw()

    @property
    def widget(self) -> tk.Canvas:
        return self._canvas

    def _draw(self) -> None:
        """Draw the ring and center symbol."""
        s = self._size
        pad = 4
        # Ring (drawn as oval outline)
        self._ring_id = self._canvas.create_oval(
            pad, pad, s - pad, s - pad, outline=RING_IDLE, width=3
        )
        # Center symbol
        self._symbol_id = self._canvas.create_text(
            s // 2, s // 2, text="✦", fill=ACCENT_LT, font=("Helvetica", s // 3)
        )

    def start(self, root: tk.Tk) -> None:
        """Start the idle breathing animation."""
        self._root = root
        self._animate_idle()

    def set_state(self, state: str) -> None:
        """Change ring state: idle, processing, success, error."""
        prev = self._state
        self._state = state
        self._phase = 0.0

        if state == "processing":
            self._canvas.itemconfig(self._symbol_id, text="⟳")
            self._animate_processing()
        elif state == "success":
            self._canvas.itemconfig(self._ring_id, outline=RING_SUCCESS)
            self._canvas.itemconfig(self._symbol_id, text="✓", fill=RING_SUCCESS)
            # Return to idle after flash
            self._root.after(1200, lambda: self._reset_to_idle())
        elif state == "error":
            self._canvas.itemconfig(self._ring_id, outline=RING_ERROR)
            self._canvas.itemconfig(self._symbol_id, text="✗", fill=RING_ERROR)
            self._root.after(1200, lambda: self._reset_to_idle())
        elif state == "idle":
            self._reset_to_idle()

    def _reset_to_idle(self) -> None:
        self._state = "idle"
        self._phase = 0.0
        self._canvas.itemconfig(self._symbol_id, text="✦", fill=ACCENT_LT)
        self._canvas.itemconfig(self._ring_id, outline=RING_IDLE)
        self._animate_idle()

    def _animate_idle(self) -> None:
        """Gentle breathing pulse on the ring opacity."""
        if self._state != "idle":
            return
        if not self._canvas.winfo_exists():
            return
        import math

        self._phase += 0.05
        # Oscillate between dim and bright
        t = (math.sin(self._phase) + 1) / 2  # 0..1
        color = _lerp(ACCENT_DK, ACCENT_LT, t)
        self._canvas.itemconfig(self._ring_id, outline=color)
        sym_color = _lerp(FG_DIM, ACCENT_LT, t * 0.6)
        self._canvas.itemconfig(self._symbol_id, fill=sym_color)
        self._anim_id = self._root.after(T_RING, self._animate_idle)

    def _animate_processing(self) -> None:
        """Rotating color shift while processing."""
        if self._state != "processing":
            return
        if not self._canvas.winfo_exists():
            return
        import math

        self._phase += 0.12
        t = (math.sin(self._phase) + 1) / 2
        color = _lerp(ACCENT_DK, ACCENT_LT, t)
        self._canvas.itemconfig(self._ring_id, outline=color, width=4)
        # Rotate symbol color
        sym_t = (math.sin(self._phase * 1.5) + 1) / 2
        sym_color = _lerp(FG_DIM, ACCENT, sym_t)
        self._canvas.itemconfig(self._symbol_id, fill=sym_color)
        self._anim_id = self._root.after(T_RING, self._animate_processing)


# ═══════════════════════════════════════════════════════════════════════════
#  THREAD PANEL — Scrollable thread history (replaces recents)
# ═══════════════════════════════════════════════════════════════════════════


class ThreadPanel:
    """Scrollable thread history panel — replaces the recents section.

    Displays recent completed threads with summary, timestamp, and outcome
    status icon. Supports expand/collapse to show full conversation turns.
    Visually distinguishes active threads from completed ones.
    """

    # Status icons for thread outcome
    _OUTCOME_ICONS = {
        "success": "✓",
        "error": "⚠",
        "incomplete": "○",
        "": "○",
    }
    _OUTCOME_COLORS = {
        "success": SUCCESS,
        "error": ERROR,
        "incomplete": FG_DIM,
        "": FG_DIM,
    }

    # Background for active thread distinction
    _ACTIVE_BG = BG_HOVER
    _COMPLETED_BG = BG_CARD

    def __init__(self, parent: tk.Frame, bridge, fonts: dict) -> None:
        """Initialize the ThreadPanel.

        Args:
            parent: Parent Tkinter frame to attach to.
            bridge: CIOSBridge instance (used to access _thread_manager).
            fonts: Font dictionary from CIOSApp._f.
        """
        self._parent = parent
        self._bridge = bridge
        self._fonts = fonts
        self._threads: list = []
        self._expanded: set = set()  # Set of expanded thread IDs
        self._entry_frames: dict = {}  # thread_id → frame widget

        # Build the scrollable container
        self._frame = tk.Frame(parent, bg=BG)
        self._scroll = ScrollFrame(self._frame, bg=BG)
        self._scroll.pack(fill="both", expand=True)

    @property
    def widget(self) -> tk.Frame:
        """Return the root frame for packing/gridding into the parent."""
        return self._frame

    def load(self) -> None:
        """Load recent threads from the store and render them."""
        try:
            self._threads = self._bridge._thread_manager.get_recent_threads(10)
        except Exception:
            self._threads = []
        self._render()

    def refresh(self) -> None:
        """Re-render after a new thread completes."""
        self.load()

    def _render(self) -> None:
        """Clear and re-render all thread entries."""
        # Clear existing entries
        for w in self._scroll.inner.winfo_children():
            w.destroy()
        self._entry_frames.clear()

        if not self._threads:
            tk.Label(
                self._scroll.inner,
                text="Nenhuma conversa ainda",
                font=self._fonts["small"],
                fg=FG_DIM,
                bg=BG,
            ).pack(anchor="w", pady=SP_TIGHT)
            return

        # Check if there's an active thread to distinguish visually
        active_thread_id = None
        try:
            tm = self._bridge._thread_manager
            if tm._active_thread is not None:
                active_thread_id = tm._active_thread.id
        except Exception:
            pass

        for thread in self._threads:
            is_active = thread.id == active_thread_id
            entry_frame = self._render_entry(thread, is_active)
            entry_frame.pack(fill="x", pady=(0, SP_MICRO))
            self._entry_frames[thread.id] = entry_frame

    def _render_entry(self, thread, is_active: bool = False) -> tk.Frame:
        """Render a single thread entry with summary, timestamp, and status icon.

        Args:
            thread: Thread dataclass instance.
            is_active: Whether this is the currently active thread.

        Returns:
            The frame widget for this entry.
        """
        bg = self._ACTIVE_BG if is_active else self._COMPLETED_BG
        entry = tk.Frame(self._scroll.inner, bg=bg, padx=SP_COMPACT, pady=SP_TIGHT)

        # Active thread indicator (left border effect via nested frame)
        if is_active:
            indicator = tk.Frame(entry, bg=ACCENT, width=3)
            indicator.pack(side="left", fill="y", padx=(0, SP_TIGHT))

        # Content area
        content = tk.Frame(entry, bg=bg)
        content.pack(side="left", fill="x", expand=True)

        # Top row: summary + status icon
        top_row = tk.Frame(content, bg=bg)
        top_row.pack(fill="x")

        # Status icon
        outcome = getattr(thread, "outcome", "") or ""
        icon = self._OUTCOME_ICONS.get(outcome, "○")
        icon_color = self._OUTCOME_COLORS.get(outcome, FG_DIM)
        tk.Label(
            top_row,
            text=icon,
            font=self._fonts["small"],
            fg=icon_color,
            bg=bg,
        ).pack(side="left", padx=(0, SP_TIGHT))

        # Summary text
        summary = getattr(thread, "summary", "") or "Nova conversa"
        tk.Label(
            top_row,
            text=summary,
            font=self._fonts["list_t"],
            fg=FG if is_active else FG_SEC,
            bg=bg,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Timestamp
        timestamp_str = self._format_timestamp(thread.created_at)
        tk.Label(
            top_row,
            text=timestamp_str,
            font=self._fonts["small"],
            fg=FG_DIM,
            bg=bg,
        ).pack(side="right")

        # Expanded content (conversation turns) — shown if thread is expanded
        if thread.id in self._expanded:
            self._render_turns(content, thread, bg)

        # Bind click to toggle expand
        for widget in [entry, content, top_row] + list(top_row.winfo_children()):
            widget.bind("<Button-1>", lambda _, tid=thread.id: self._toggle_expand(tid))
            widget.configure(cursor="hand2")

        return entry

    def _render_turns(self, parent: tk.Frame, thread, bg: str) -> None:
        """Render the conversation turns for an expanded thread entry."""
        turns = getattr(thread, "turns", []) or []
        if not turns:
            tk.Label(
                parent,
                text="  Sem detalhes",
                font=self._fonts["small"],
                fg=FG_DIM,
                bg=bg,
                anchor="w",
            ).pack(fill="x", pady=(SP_TIGHT, 0))
            return

        # Separator
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(SP_TIGHT, SP_MICRO))

        for turn in turns:
            turn_frame = tk.Frame(parent, bg=bg, padx=SP_TIGHT)
            turn_frame.pack(fill="x", pady=1)

            # User input
            user_text = getattr(turn, "user_input", "") or ""
            if user_text:
                tk.Label(
                    turn_frame,
                    text=f"→ {user_text}",
                    font=self._fonts["small"],
                    fg=FG_SEC,
                    bg=bg,
                    anchor="w",
                    wraplength=250,
                    justify="left",
                ).pack(fill="x")

            # Result summary
            result = getattr(turn, "result_summary", "") or ""
            if result:
                tk.Label(
                    turn_frame,
                    text=f"  {result}",
                    font=self._fonts["small"],
                    fg=FG_DIM,
                    bg=bg,
                    anchor="w",
                    wraplength=250,
                    justify="left",
                ).pack(fill="x")

    def _toggle_expand(self, thread_id: str) -> None:
        """Expand or collapse a thread entry to show/hide conversation turns."""
        if thread_id in self._expanded:
            self._expanded.discard(thread_id)
        else:
            self._expanded.add(thread_id)
        # Re-render to reflect the change
        self._render()

    def _format_timestamp(self, ts: float) -> str:
        """Format a Unix timestamp into a human-readable relative or absolute string."""
        import time as _time

        now = _time.time()
        diff = now - ts

        if diff < 60:
            return "agora"
        elif diff < 3600:
            mins = int(diff // 60)
            return f"{mins}min"
        elif diff < 86400:
            hours = int(diff // 3600)
            return f"{hours}h"
        else:
            # Show date for older threads
            local = _time.localtime(ts)
            return _time.strftime("%d/%m %H:%M", local)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════


class CIOSApp:
    """Main application — intent-first, single surface."""

    def __init__(self) -> None:
        import time as _time

        _t0 = _time.monotonic()

        # Boot progress → splash screen
        from cios.ui.splash import update_splash_progress

        update_splash_progress("Inicializando…", 0, 14)

        self._bridge = CIOSBridge(on_progress=update_splash_progress)
        self._busy = False
        self._pending: str | None = None
        self._step_widgets: list[tk.Label] = []
        self._dot_id: str | None = None
        self._metrics: dict = {}
        self._secondary_panels: list = []
        self._active_gallery: GalleryComponent | None = None
        # Voice
        update_splash_progress("Carregando voz…", 10, 14)
        from cios.infra.voice import VoiceManager

        self._voice = VoiceManager()

        self._splash_progress = update_splash_progress
        update_splash_progress("Montando interface…", 11, 14)
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
        self.root = tk.Tk(className="CIOS")
        self.root.title("CIOS")
        self.root.configure(bg=BG)

        # CRITICAL: Hide window while building to prevent raw/unfinished flash
        self.root.withdraw()

        # Position below topbar on primary monitor only
        from cios.infra.monitors import get_primary_monitor

        _primary = get_primary_monitor()
        if _primary:
            screen_w = _primary.width
            screen_h = _primary.height
            _primary_x = _primary.x
            _primary_y = _primary.y
        else:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            _primary_x = 0
            _primary_y = 0
        _TOPBAR_H = 28
        self.root.geometry(
            f"{screen_w}x{screen_h - _TOPBAR_H}" f"+{_primary_x}+{_primary_y + _TOPBAR_H}"
        )
        self.root.overrideredirect(False)
        self.root.bind(
            "<F11>",
            lambda _: self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen")),
        )
        self.root.bind("<Escape>", lambda _: self.root.attributes("-fullscreen", False))
        self.root.bind("<Control-q>", lambda _: self._quit())

        self._anim = Animator(self.root)

        # ── Fonts ──
        self._f = {
            "brand": tkfont.Font(family="Helvetica", size=14, weight="bold"),
            "brand_s": tkfont.Font(family="Helvetica", size=8),
            "greet": tkfont.Font(family="Helvetica", size=24, weight="bold"),
            "sub": tkfont.Font(family="Helvetica", size=13),
            "input": tkfont.Font(family="Helvetica", size=16),
            "sec": tkfont.Font(family="Helvetica", size=11, weight="bold"),
            "card_i": tkfont.Font(family="Helvetica", size=20),
            "card_t": tkfont.Font(family="Helvetica", size=11, weight="bold"),
            "card_d": tkfont.Font(family="Helvetica", size=9),
            "step": tkfont.Font(family="Helvetica", size=12),
            "res_t": tkfont.Font(family="Helvetica", size=16, weight="bold"),
            "res_b": tkfont.Font(family="Helvetica", size=12, weight="normal"),
            "metric": tkfont.Font(family="Helvetica", size=10),
            "metric_v": tkfont.Font(family="Helvetica", size=10, weight="bold"),
            "small": tkfont.Font(family="Helvetica", size=9),
            "list_t": tkfont.Font(family="Helvetica", size=11, weight="bold"),
            "list_s": tkfont.Font(family="Helvetica", size=9),
            "btn": tkfont.Font(family="Helvetica", size=10, weight="bold"),
        }

        # ── 2-column grid: center (flex) + right (status) ──
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=0, minsize=RIGHT_W)
        self.root.rowconfigure(0, weight=1)

        self._build_center()
        self._splash_progress("Building center panel", 12, 14)
        self._build_right_panel()
        self._splash_progress("Building right panel", 13, 14)

        self._entry.focus_set()
        self._poll_status()
        self._init_secondary_screens()

        self._splash_progress("Finalizando…", 14, 14)

        # All widgets built — show window
        self.root.deiconify()
        self.root.update_idletasks()

    # ═══════════════════════════════════════════════════════════════════════
    #  CENTER PANEL (the only interaction surface)
    # ═══════════════════════════════════════════════════════════════════════

    def _build_center(self) -> None:
        self._center = tk.Frame(self.root, bg=BG)
        self._center.grid(row=0, column=0, sticky="nsew")

        self._build_page_home()

    # ── HOME (the only view) ────────────────────────────────────────────

    def _build_page_home(self) -> None:
        p = tk.Frame(self._center, bg=BG)
        p.pack(fill="both", expand=True)

        # ═══ TOP AREA: feed + results (grows upward) ═══
        self._feed_area = tk.Frame(p, bg=BG, padx=SP_PAGE, pady=SP_BLOCK)
        self._feed_area.pack(fill="both", expand=True)

        # Greeting (shown when no results yet)
        self._greeting_frame = tk.Frame(self._feed_area, bg=BG)
        self._greeting_frame.pack(fill="both", expand=True)

        # Center greeting vertically
        tk.Frame(self._greeting_frame, bg=BG).pack(fill="both", expand=True)
        self._greeting_center = tk.Frame(self._greeting_frame, bg=BG)
        self._greeting_center.pack()
        self._greeting_lbl = tk.Label(
            self._greeting_center, text=f"{_GREET}, {_USER}.", font=self._f["greet"], fg=FG, bg=BG
        )
        self._greeting_lbl.pack()
        self._subtitle_lbl = tk.Label(
            self._greeting_center, text="O que vamos fazer?", font=self._f["sub"], fg=FG_DIM, bg=BG
        )
        self._subtitle_lbl.pack(pady=(SP_MICRO, 0))

        # Quick chips
        self._chips_frame = tk.Frame(self._greeting_center, bg=BG)
        self._chips_frame.pack(pady=(SP_SECTION, 0))
        self._build_quick_chips()
        tk.Frame(self._greeting_frame, bg=BG).pack(fill="both", expand=True)

        # Processing spinner (hidden, shown during execution)
        self._spinner_frame = tk.Frame(self._feed_area, bg=BG)
        self._spinner_canvas = tk.Canvas(
            self._spinner_frame, width=36, height=36, bg=BG, highlightthickness=0, bd=0
        )
        self._spinner_canvas.pack(pady=(SP_DEFAULT, SP_COMPACT))
        self._spinner_arc = self._spinner_canvas.create_arc(
            4, 4, 32, 32, start=0, extent=270, outline=ACCENT, width=3, style="arc"
        )
        self._spinner_dot = self._spinner_canvas.create_oval(
            14, 14, 22, 22, fill=ACCENT_LT, outline=""
        )
        self._spinner_phase = 0.0
        self._spinner_anim_id: str | None = None

        # Feed (execution steps)
        self._feed = tk.Frame(self._feed_area, bg=BG)

        # Confirm dialog
        self._confirm_frame = tk.Frame(
            self._feed_area, bg=BG_CARD, padx=SP_SECTION, pady=SP_DEFAULT
        )
        self._confirm_msg = tk.Label(
            self._confirm_frame,
            font=self._f["step"],
            fg=FG,
            bg=BG_CARD,
            wraplength=600,
            justify="left",
            anchor="w",
        )
        self._confirm_msg.pack(fill="x", pady=(0, SP_COMPACT))

        btn_row = tk.Frame(self._confirm_frame, bg=BG_CARD)
        btn_row.pack(anchor="w")
        self._confirm_btn = tk.Button(
            btn_row,
            text="Confirmar",
            font=self._f["btn"],
            bg=ACCENT,
            fg="#fff",
            activebackground=ACCENT_LT,
            activeforeground="#fff",
            relief="flat",
            padx=18,
            pady=5,
            command=self._on_confirm,
        )
        self._confirm_btn.pack(side="left", padx=(0, 10))
        self._confirm_btn.bind("<Return>", lambda e: self._on_confirm())
        tk.Button(
            btn_row,
            text="Cancelar",
            font=self._f["btn"],
            bg=BG_INPUT,
            fg=FG_DIM,
            activebackground=BG_HOVER,
            activeforeground=FG,
            relief="flat",
            padx=18,
            pady=5,
            command=self._on_cancel,
        ).pack(side="left")

        # Result (persists until next command)
        self._result_frame = tk.Frame(self._feed_area, bg=BG)
        self._res_title = tk.Label(
            self._result_frame, font=self._f["res_t"], bg=BG, anchor="w", justify="left"
        )
        self._res_body = tk.Label(
            self._result_frame,
            font=self._f["res_b"],
            bg=BG,
            fg=FG_SEC,
            wraplength=600,
            justify="left",
            anchor="w",
        )

        # Activity (recent actions)
        self._activity_outer = tk.Frame(self._feed_area, bg=BG)
        self._activity_frame = tk.Frame(self._activity_outer, bg=BG)
        self._activity_frame.pack(fill="x")

        # ═══ BOTTOM: prompt (always at bottom) ═══
        self._prompt_area = tk.Frame(p, bg=BG_PANEL, padx=SP_PAGE, pady=SP_DEFAULT)
        self._prompt_area.pack(fill="x", side="bottom")

        self._prompt_glow = tk.Frame(self._prompt_area, bg=BORDER, padx=2, pady=2)
        self._prompt_glow.pack(fill="x")

        prompt_inner = tk.Frame(self._prompt_glow, bg=BG_INPUT)
        prompt_inner.pack(fill="x")

        tk.Label(prompt_inner, text="✦", font=self._f["input"], fg=FG_DIM, bg=BG_INPUT).pack(
            side="left", padx=(SP_DEFAULT, 10), anchor="n", pady=SP_COMPACT
        )

        self._entry = tk.Text(
            prompt_inner,
            font=self._f["input"],
            bg=BG_INPUT,
            fg=FG,
            insertbackground=ACCENT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            height=3,
            wrap="word",
        )
        self._entry.pack(side="left", fill="both", expand=True, pady=SP_COMPACT, padx=(0, SP_TIGHT))
        self._entry.bind("<Return>", self._on_enter_key)

        # Focus glow
        self._entry.bind(
            "<FocusIn>", lambda _: self._anim.color([self._prompt_glow], "bg", ACCENT, T_NORMAL)
        )
        self._entry.bind(
            "<FocusOut>", lambda _: self._anim.color([self._prompt_glow], "bg", BORDER, T_NORMAL)
        )

        # Buttons (stacked on right side)
        btn_frame = tk.Frame(prompt_inner, bg=BG_INPUT)
        btn_frame.pack(side="right", padx=(0, SP_COMPACT), pady=SP_COMPACT, anchor="s")

        send_outer = tk.Frame(btn_frame, bg=ACCENT, padx=1, pady=1)
        send_outer.pack(pady=(0, SP_TIGHT))
        self._send_btn_outer = send_outer
        send_btn = tk.Label(
            send_outer,
            text=" Enviar ",
            font=self._f["btn"],
            fg="#fff",
            bg=ACCENT,
            pady=3,
            padx=SP_TIGHT,
            cursor="hand2",
        )
        send_btn.pack()
        self._send_btn = send_btn

        for w in [send_outer, send_btn]:
            w.bind(
                "<Enter>",
                lambda _: self._anim.color([send_outer, send_btn], "bg", ACCENT_LT, T_FAST),
            )
            w.bind(
                "<Leave>", lambda _: self._anim.color([send_outer, send_btn], "bg", ACCENT, T_FAST)
            )
            w.bind("<Button-1>", self._on_enter)
            w.configure(cursor="hand2")

        # Cancel button (hidden by default)
        cancel_outer = tk.Frame(btn_frame, bg=ERROR, padx=1, pady=1)
        self._cancel_btn_outer = cancel_outer
        cancel_btn = tk.Label(
            cancel_outer,
            text=" ✕ ",
            font=self._f["btn"],
            fg="#fff",
            bg=ERROR,
            pady=3,
            padx=SP_TIGHT,
            cursor="hand2",
        )
        cancel_btn.pack()
        self._cancel_btn = cancel_btn

        for w in [cancel_outer, cancel_btn]:
            w.bind(
                "<Enter>",
                lambda _: self._anim.color([cancel_outer, cancel_btn], "bg", "#dc2626", T_FAST),
            )
            w.bind(
                "<Leave>",
                lambda _: self._anim.color([cancel_outer, cancel_btn], "bg", ERROR, T_FAST),
            )
            w.bind("<Button-1>", lambda _: self._on_cancel_intent())
            w.configure(cursor="hand2")

        self._cancelled = False

        # Mic button
        self._mic_outer = tk.Frame(btn_frame, bg=BG_CARD, padx=1, pady=1)
        self._mic_outer.pack(pady=(SP_TIGHT, 0))
        self._mic_btn = tk.Label(
            self._mic_outer,
            text=" 🎤 ",
            font=self._f["btn"],
            fg=FG_SEC,
            bg=BG_CARD,
            pady=3,
            cursor="hand2",
        )
        self._mic_btn.pack()

        for w in [self._mic_outer, self._mic_btn]:
            w.bind(
                "<Enter>",
                lambda _: self._anim.color(
                    [self._mic_outer, self._mic_btn], "bg", BG_HOVER, T_FAST
                ),
            )
            w.bind(
                "<Leave>",
                lambda _: self._anim.color([self._mic_outer, self._mic_btn], "bg", BG_CARD, T_FAST),
            )
            w.bind("<Button-1>", lambda _: self._on_mic())
            w.configure(cursor="hand2")

        # Placeholder
        self._ph = True
        self._entry.insert("1.0", "Diga o que precisa…")
        self._entry.configure(fg=FG_DIM)
        self._entry.bind("<FocusIn>", self._ph_clear, add="+")
        self._entry.bind("<FocusOut>", self._ph_restore, add="+")

        # ═══ BELOW PROMPT: ThreadPanel (replaces recents) + indicators ═══
        self._thread_panel_area = tk.Frame(p, bg=BG, padx=SP_PAGE)
        self._thread_panel_area.pack(fill="x", side="bottom")

        # Pending question indicator (hidden by default)
        self._pending_indicator = tk.Label(
            self._thread_panel_area,
            text="⏳ Aguardando resposta...",
            font=self._f["small"],
            fg=ACCENT_LT,
            bg=BG,
            anchor="w",
        )

        # Timeout warning indicator (hidden by default)
        self._timeout_warning = tk.Label(
            self._thread_panel_area,
            text="⚠ Tempo quase esgotado",
            font=self._f["small"],
            fg=WARNING,
            bg=BG,
            anchor="w",
        )

        # Thread panel header
        thread_header = tk.Frame(self._thread_panel_area, bg=BG)
        thread_header.pack(fill="x", pady=(SP_TIGHT, SP_MICRO))
        tk.Label(thread_header, text="🕐 Conversas", font=self._f["small"], fg=FG_DIM, bg=BG).pack(
            side="left"
        )
        self._show_all_btn = tk.Label(
            thread_header,
            text="ver tudo",
            font=self._f["small"],
            fg=ACCENT_LT,
            bg=BG,
            cursor="hand2",
        )
        self._show_all_btn.pack(side="right")
        self._show_all_btn.bind("<Button-1>", lambda _: self._show_full_history())
        self._show_all_btn.bind("<Enter>", lambda _: self._show_all_btn.configure(fg=ACCENT))
        self._show_all_btn.bind("<Leave>", lambda _: self._show_all_btn.configure(fg=ACCENT_LT))

        # ThreadPanel instance (replaces _recents_frame)
        self._thread_panel = ThreadPanel(self._thread_panel_area, self._bridge, self._f)
        self._thread_panel.widget.pack(fill="x")
        self._thread_panel.load()

        # Start polling for pending question state
        self._poll_pending_state()

    def _build_quick_chips(self) -> None:
        """Build quick actions as subtle inline chips (not big cards)."""
        chips = [
            ("📁 Organizar", "organize my downloads"),
            ("📊 Diagnóstico", "my computer is slow"),
            ("🚀 Projeto", "start my backend"),
            ("🔌 Processos", "kill process on port 3000"),
            ("📋 Logs", "show logs"),
        ]
        for text, cmd in chips:
            chip = tk.Label(
                self._chips_frame,
                text=f" {text} ",
                font=self._f["small"],
                fg=FG_SEC,
                bg=BG_CARD,
                padx=SP_COMPACT,
                pady=SP_TIGHT,
                cursor="hand2",
            )
            chip.pack(side="left", padx=3)

            def mk_enter(w):
                return lambda _: self._anim.color([w], "bg", BG_HOVER, T_FAST)

            def mk_leave(w):
                return lambda _: self._anim.color([w], "bg", BG_CARD, T_FAST)

            def mk_click(c):
                return lambda _: self._on_card(c)

            chip.bind("<Enter>", mk_enter(chip))
            chip.bind("<Leave>", mk_leave(chip))
            chip.bind("<Button-1>", mk_click(cmd))

    def _transition_to_active(self) -> None:
        """Hide greeting, show feed area above prompt."""
        self._greeting_frame.pack_forget()
        # Show spinner + feed
        self._spinner_frame.pack(fill="x")
        self._feed.pack(fill="x")

    def _transition_to_idle(self) -> None:
        """Show greeting again (only if no result is showing)."""
        if not self._res_title.winfo_manager():
            self._spinner_frame.pack_forget()
            self._feed.pack_forget()
            self._greeting_frame.pack(fill="both", expand=True)
        # Refresh thread panel
        self._thread_panel.refresh()

    # ═══════════════════════════════════════════════════════════════════════
    #  RIGHT PANEL (system status + history + intelligence)
    # ═══════════════════════════════════════════════════════════════════════

    def _build_right_panel(self) -> None:
        rp = tk.Frame(self.root, bg=BG_PANEL, width=RIGHT_W)
        rp.grid(row=0, column=1, sticky="nsew")
        rp.grid_propagate(False)
        self._right_panel = rp

        # ── Top: Condensed System Status (icons + percentages only) ──
        status_frame = tk.Frame(rp, bg=BG_PANEL)
        status_frame.pack(side="top", fill="x", padx=SP_COMPACT, pady=(SP_DEFAULT, SP_TIGHT))

        # Status in a compact 2x2 grid
        status_grid = tk.Frame(status_frame, bg=BG_PANEL)
        status_grid.pack(fill="x")
        status_grid.columnconfigure(0, weight=1)
        status_grid.columnconfigure(1, weight=1)

        metrics_config = [
            ("cpu", "⚡", ACCENT),
            ("mem", "◈", CYAN),
            ("disk", "◉", SUCCESS),
            ("net", "⇅", WARNING),
        ]

        for i, (key, icon, color) in enumerate(metrics_config):
            row, col = divmod(i, 2)
            cell = tk.Frame(status_grid, bg=BG_PANEL, padx=SP_TIGHT, pady=SP_TIGHT)
            cell.grid(row=row, column=col, sticky="ew", padx=2, pady=2)

            # Icon + value in one line
            tk.Label(
                cell, text=icon, font=self._f["metric"], fg=color, bg=BG_PANEL
            ).pack(side="left")
            val = tk.Label(
                cell, text="--", font=self._f["metric_v"], fg=FG, bg=BG_PANEL
            )
            val.pack(side="left", padx=(SP_TIGHT, 0))

            # Thin glow bar underneath
            bar_bg = tk.Frame(cell, bg=BORDER, height=2)
            bar_bg.pack(fill="x", side="bottom", pady=(SP_MICRO, 0))
            bar_fill = tk.Frame(bar_bg, bg=color, height=2)
            bar_fill.place(x=0, y=0, relheight=1.0, relwidth=0.005)

            self._metrics[key] = {"val": val, "fill": bar_fill, "color": color}

        # ── Middle: Thread History (scrollable) ──
        history_frame = tk.Frame(rp, bg=BG_PANEL)
        history_frame.pack(side="top", fill="both", expand=True, padx=SP_COMPACT, pady=(SP_COMPACT, 0))

        # History header
        hist_header = tk.Frame(history_frame, bg=BG_PANEL)
        hist_header.pack(fill="x", pady=(0, SP_TIGHT))
        tk.Label(
            hist_header, text="Conversas", font=self._f["small"], fg=FG_DIM, bg=BG_PANEL
        ).pack(side="left")

        # Thread list (scrollable)
        self._sidebar_thread_panel = ThreadPanel(history_frame, self._bridge, self._f)
        self._sidebar_thread_panel.widget.pack(fill="both", expand=True)
        self._sidebar_thread_panel.load()

        # ── Bottom: Intelligence Section (always at bottom) ──
        self._build_intelligence_section(rp)

    def _build_intelligence_section(self, parent) -> None:
        """Build the Intelligence login/status section at the bottom of sidebar."""
        import tkinter as tk

        self._intel_frame = tk.Frame(parent, bg=BG_PANEL)
        self._intel_frame.pack(side="bottom", fill="x", padx=SP_COMPACT, pady=(0, SP_DEFAULT))

        self._refresh_intelligence_ui()

    def _refresh_intelligence_ui(self) -> None:
        """Refresh the Intelligence section based on login state."""
        import tkinter as tk

        from cios.core.intelligence import intelligence

        # Clear existing widgets
        for w in self._intel_frame.winfo_children():
            w.destroy()

        frame = self._intel_frame

        if not intelligence.is_logged_in:
            # ── Not logged in: compact login button ──
            card = tk.Frame(frame, bg=BG_CARD, padx=SP_DEFAULT, pady=SP_COMPACT)
            card.pack(fill="x")

            tk.Label(
                card,
                text="⚡ Intelligence",
                font=self._f["sec"],
                fg=ACCENT_LT,
                bg=BG_CARD,
                anchor="w",
            ).pack(fill="x")

            tk.Label(
                card,
                text="IA avançada · 5/dia grátis",
                font=self._f["small"],
                fg=FG_DIM,
                bg=BG_CARD,
                anchor="w",
            ).pack(fill="x", pady=(SP_MICRO, 0))

            btn = tk.Frame(card, bg=ACCENT, padx=SP_DEFAULT, pady=SP_TIGHT)
            btn.pack(fill="x", pady=(SP_COMPACT, 0))
            tk.Label(
                btn,
                text="Entrar",
                font=self._f["btn"],
                fg="#fff",
                bg=ACCENT,
                cursor="hand2",
            ).pack()
            btn.bind("<Button-1>", lambda _: self._on_intel_login())
            for child in btn.winfo_children():
                child.bind("<Button-1>", lambda _: self._on_intel_login())

        else:
            # ── Logged in: profile + usage ──
            user = intelligence.user
            usage = intelligence.usage

            card = tk.Frame(frame, bg=BG_CARD, padx=SP_DEFAULT, pady=SP_DEFAULT)
            card.pack(fill="x")

            # User info row
            info_row = tk.Frame(card, bg=BG_CARD)
            info_row.pack(fill="x")

            # Profile picture (placeholder circle if no image loaded)
            tk.Label(info_row, text="👤", font=("Helvetica", 16), fg=FG_SEC, bg=BG_CARD).pack(
                side="left", padx=(0, SP_TIGHT)
            )

            name_frame = tk.Frame(info_row, bg=BG_CARD)
            name_frame.pack(side="left", fill="x")
            tk.Label(
                name_frame,
                text=user.name or user.email.split("@")[0],
                font=self._f["metric_v"],
                fg=FG,
                bg=BG_CARD,
                anchor="w",
            ).pack(fill="x")

            plan_text = f"Plano: {usage.plan.capitalize()}"
            plan_color = ACCENT_LT if usage.plan != "free" else FG_SEC
            tk.Label(
                name_frame,
                text=plan_text,
                font=self._f["small"],
                fg=plan_color,
                bg=BG_CARD,
                anchor="w",
            ).pack(fill="x")

            # Usage bar
            used = usage.used_today
            limit = usage.limit_today
            pct = min(used / max(limit, 1), 1.0)

            usage_frame = tk.Frame(card, bg=BG_CARD)
            usage_frame.pack(fill="x", pady=(SP_TIGHT, 0))

            if used >= limit:
                # Limit reached
                tk.Label(
                    usage_frame,
                    text="⚠️ Limite diário atingido",
                    font=self._f["small"],
                    fg=WARNING,
                    bg=BG_CARD,
                    anchor="w",
                ).pack(fill="x")
                tk.Label(
                    usage_frame,
                    text="Renova amanhã às 00:00",
                    font=self._f["small"],
                    fg=FG_DIM,
                    bg=BG_CARD,
                    anchor="w",
                ).pack(fill="x")
            else:
                tk.Label(
                    usage_frame,
                    text=f"Hoje: {used}/{limit} consultas",
                    font=self._f["small"],
                    fg=FG_SEC,
                    bg=BG_CARD,
                    anchor="w",
                ).pack(fill="x")

                # Progress bar
                bar_bg = tk.Frame(usage_frame, bg=BORDER, height=5)
                bar_bg.pack(fill="x", pady=(SP_MICRO, 0))
                bar_color = SUCCESS if pct < 0.8 else WARNING
                bar_fill = tk.Frame(bar_bg, bg=bar_color, height=5)
                bar_fill.place(x=0, y=0, relheight=1.0, relwidth=max(pct, 0.02))

            # Upgrade button (only for free plan)
            if usage.plan == "free":
                upgrade_btn = tk.Frame(card, bg=ACCENT_DK, padx=SP_COMPACT, pady=SP_TIGHT)
                upgrade_btn.pack(fill="x", pady=(SP_TIGHT, 0))
                tk.Label(
                    upgrade_btn,
                    text="⚡ Upgrade → Starter",
                    font=self._f["small"],
                    fg="#fff",
                    bg=ACCENT_DK,
                    cursor="hand2",
                ).pack()
                upgrade_btn.bind("<Button-1>", lambda _: self._on_intel_upgrade())
                for child in upgrade_btn.winfo_children():
                    child.bind("<Button-1>", lambda _: self._on_intel_upgrade())

    def _on_intel_login(self) -> None:
        """Handle Intelligence login button click."""
        from cios.core.intelligence import start_auth_flow

        def on_complete(success, message):
            # Schedule UI refresh on main thread
            if self.root:
                self.root.after(0, self._refresh_intelligence_ui)

        start_auth_flow(on_complete=on_complete)

    def _on_intel_upgrade(self) -> None:
        """Handle upgrade button click — open browser to pricing page."""
        import webbrowser

        webbrowser.open("https://cios-ia.com/upgrade")

    def _refresh_sidebar_threads(self) -> None:
        """Refresh the sidebar thread history panel."""
        if hasattr(self, "_sidebar_thread_panel"):
            self._sidebar_thread_panel.refresh()

    # ═══════════════════════════════════════════════════════════════════════
    #  DATA LOADERS
    # ═══════════════════════════════════════════════════════════════════════

    def _clear_frame(self, frame: tk.Frame) -> None:
        for w in frame.winfo_children():
            w.destroy()

    def _load_activity(self) -> None:
        """Legacy — redirects to thread panel refresh."""
        self._thread_panel.refresh()

    def _load_recents(self) -> None:
        """Legacy compatibility — delegates to thread panel refresh."""
        self._thread_panel.refresh()

    def _show_full_history(self) -> None:
        """Show full history in the feed area above prompt."""
        data = self._bridge.get_recent_activity()
        self._greeting_frame.pack_forget()
        self._clear_result()
        self._spinner_frame.pack_forget()
        self._feed.pack_forget()

        # Use activity_outer in feed_area
        self._clear_frame(self._activity_frame)
        if not data:
            tk.Label(
                self._activity_frame,
                text="Nenhuma atividade registrada",
                font=self._f["step"],
                fg=FG_DIM,
                bg=BG,
            ).pack(anchor="w", pady=SP_TIGHT)
        else:
            for it in data:
                c = (
                    SUCCESS
                    if it["outcome"] == "success"
                    else WARNING
                    if it["outcome"] == "recovered"
                    else ERROR
                )
                row = tk.Frame(self._activity_frame, bg=BG_CARD, padx=SP_COMPACT, pady=7)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=it["icon"], font=self._f["step"], fg=c, bg=BG_CARD).pack(
                    side="left", padx=(0, 10)
                )
                tk.Label(row, text=it["text"], font=self._f["list_s"], fg=FG_SEC, bg=BG_CARD).pack(
                    side="left", fill="x", expand=True
                )
                tk.Label(row, text=it["time"], font=self._f["small"], fg=FG_DIM, bg=BG_CARD).pack(
                    side="right"
                )
        self._activity_outer.pack(fill="both", expand=True)

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

    def _poll_pending_state(self) -> None:
        """Poll for pending question state and update visual indicators."""
        try:
            self._update_pending_indicators()
        except Exception:
            pass
        self.root.after(2000, self._poll_pending_state)

    def _update_pending_indicators(self) -> None:
        """Show/hide pending question and timeout warning indicators."""
        has_pending = False
        time_remaining = None

        try:
            tm = self._bridge._thread_manager
            if (
                tm._active_thread is not None
                and tm._active_thread.pending_question is not None
                and tm._pending_question_mono is not None
            ):
                has_pending = True
                import time as _time

                elapsed = _time.monotonic() - tm._pending_question_mono
                from cios.core.thread_manager import PENDING_QUESTION_TIMEOUT

                time_remaining = PENDING_QUESTION_TIMEOUT - elapsed
        except Exception:
            pass

        # Show/hide pending indicator
        if has_pending:
            if not self._pending_indicator.winfo_manager():
                self._pending_indicator.pack(
                    fill="x", pady=(SP_TIGHT, 0), before=self._thread_panel.widget
                )
        else:
            if self._pending_indicator.winfo_manager():
                self._pending_indicator.pack_forget()

        # Show/hide timeout warning (when <30s remaining)
        if has_pending and time_remaining is not None and time_remaining < 30:
            remaining_int = max(0, int(time_remaining))
            self._timeout_warning.configure(text=f"⚠ Tempo quase esgotado ({remaining_int}s)")
            if not self._timeout_warning.winfo_manager():
                self._timeout_warning.pack(
                    fill="x", pady=(SP_TIGHT, 0), before=self._thread_panel.widget
                )
        else:
            if self._timeout_warning.winfo_manager():
                self._timeout_warning.pack_forget()

    def _update_metrics(self, d: dict) -> None:
        m = self._metrics
        # CPU
        m["cpu"]["val"].configure(text=f"{d['cpu_percent']}%")
        self._anim.bar(m["cpu"]["fill"], d["cpu_percent"] / 100)
        # Memory
        m["mem"]["val"].configure(text=f"{d['mem_used_gb']}/{d['mem_total_gb']} GB")
        self._anim.bar(m["mem"]["fill"], d["mem_percent"] / 100)
        # Disk
        m["disk"]["val"].configure(text=f"{d['disk_free_gb']} GB livre")
        self._anim.bar(m["disk"]["fill"], d["disk_percent"] / 100)
        # Network
        m["net"]["val"].configure(text=f"↑{d['net_sent_mb']} ↓{d['net_recv_mb']} MB")
        self._anim.bar(m["net"]["fill"], 0.3)

    # ═══════════════════════════════════════════════════════════════════════
    #  INPUT / EXECUTION
    # ═══════════════════════════════════════════════════════════════════════

    def _ph_clear(self, _) -> None:
        if self._ph:
            self._entry.delete("1.0", "end")
            self._entry.configure(fg=FG)
            self._ph = False

    def _ph_restore(self, _) -> None:
        if not self._entry.get("1.0", "end").strip():
            self._entry.insert("1.0", "Diga o que precisa…")
            self._entry.configure(fg=FG_DIM)
            self._ph = True

    def _toggle_expand(self) -> None:
        """Toggle between single-line Entry and multiline Text widget."""
        if self._expanded:
            # Collapse: get text from Text, switch back to Entry
            text = self._text_entry.get("1.0", "end").strip()
            self._text_entry.pack_forget()
            self._entry.pack(side="left", fill="x", expand=True, pady=SP_DEFAULT)
            self._entry.delete(0, "end")
            if text and text != "Diga o que precisa…":
                self._entry.insert(0, text)
                self._entry.configure(fg=FG)
            self._expanded = False
            self._expand_btn.configure(text=" ⤢ ")
            self._entry.focus_set()
        else:
            # Expand: get text from Entry, switch to Text
            text = self._entry.get().strip()
            if self._ph:
                text = ""
            self._entry.pack_forget()
            # Create Text widget if not exists
            if not hasattr(self, "_text_entry"):
                self._text_entry = tk.Text(
                    self._prompt_inner,
                    font=self._f["input"],
                    bg=BG_INPUT,
                    fg=FG,
                    insertbackground=ACCENT,
                    relief="flat",
                    bd=0,
                    highlightthickness=0,
                    height=4,
                    wrap="word",
                )
                self._text_entry.bind("<Control-Return>", self._on_enter)
            self._text_entry.pack(
                side="left", fill="both", expand=True, pady=SP_COMPACT, padx=(0, SP_TIGHT)
            )
            self._text_entry.delete("1.0", "end")
            if text:
                self._text_entry.insert("1.0", text)
            self._expanded = True
            self._expand_btn.configure(text=" ⤡ ")
            self._ph = False
            self._text_entry.focus_set()

    def _on_enter_key(self, event=None) -> None:
        """Handle Return key in Text widget — submit on Enter, newline on Shift+Enter."""
        # Check if Shift is held
        if event and (event.state & 0x1):  # Shift mask
            return  # let default behavior insert newline
        # Otherwise submit and prevent newline
        self._on_enter()
        return "break"

    def _on_enter(self, _=None) -> None:
        if self._busy:
            return
        text = self._entry.get("1.0", "end").strip()
        if not text or self._ph:
            return
        self._submit(text)

    def _on_mic(self) -> None:
        """Start voice input — record, transcribe, execute."""
        if self._busy or not self._voice.stt_available:
            return
        if self._voice.is_listening:
            return

        # Signal topbar that mic is active
        from cios.ui.topbar import signal_topbar_idle, signal_topbar_mic

        signal_topbar_mic()

        # Visual feedback: mic button glows
        self._anim.color([self._mic_outer, self._mic_btn], "bg", ACCENT, T_FAST)
        self._mic_btn.configure(text=" 🔴 ", fg="#fff")

        # Clear and show listening state
        if self._ph:
            self._ph_clear(None)
        self._entry.delete("1.0", "end")
        self._entry.insert("1.0", "Escutando...")
        self._entry.configure(fg=ACCENT_LT)

        def on_result(text: str | None):
            # Signal topbar that mic is done
            signal_topbar_idle()

            # Reset mic button
            self.root.after(
                0,
                lambda: (
                    self._anim.color([self._mic_outer, self._mic_btn], "bg", BG_CARD, T_FAST),
                    self._mic_btn.configure(text=" 🎤 ", fg=FG_SEC),
                ),
            )

            if text:
                self.root.after(0, lambda: self._entry.delete("1.0", "end"))
                self.root.after(0, lambda: self._entry.insert("1.0", text))
                self.root.after(0, lambda: self._entry.configure(fg=FG))
                self.root.after(100, lambda: self._submit(text))
            else:
                self.root.after(0, lambda: self._entry.delete("1.0", "end"))
                self.root.after(0, lambda: self._ph_restore(None))

        self._voice.listen_async(on_result, duration=5.0)

    def _on_card(self, cmd: str) -> None:
        if self._busy:
            return
        if self._ph:
            self._ph_clear(None)
        self._entry.delete("1.0", "end")
        self._entry.insert("1.0", cmd)
        self._entry.configure(fg=FG)
        self._submit(cmd)

    def _submit(self, text: str) -> None:
        self._busy = True
        self._cancelled = False
        self._entry.configure(state="disabled")
        # Swap send → cancel button
        self._send_btn_outer.pack_forget()
        self._cancel_btn_outer.pack(pady=(0, SP_TIGHT))
        # Clear previous result
        self._clear_result()
        self._confirm_frame.pack_forget()
        # Transition to active layout
        self._transition_to_active()
        self._clear_feed()
        # Start spinner animation
        self._start_spinner()
        self._add_step("Entendendo…", thinking=True)
        threading.Thread(target=self._run, args=(text,), daemon=True).start()

    def _run(self, text: str) -> None:
        data = self._bridge.execute_command(text)
        if data.get("confirm"):
            self.root.after(0, lambda: self._show_confirm(data["confirm"], text))
            return
        if data.get("password_prompt"):
            self.root.after(0, lambda: self._show_password_dialog(data["result"], text))
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
            target=lambda: self._display(self._bridge.execute_command(cmd, confirmed=True)),
            daemon=True,
        ).start()

    def _on_cancel(self) -> None:
        self._pending = None
        self._confirm_frame.pack_forget()
        self._show_result("Cancelado", "Nenhuma alteração feita", "success")
        self._finish()

    # ── Password dialog ──

    def _show_password_dialog(self, msg: str, cmd: str) -> None:
        """Show a modal with masked password field + confirm/cancel buttons."""
        self._pending = cmd
        self._clear_feed()
        self._stop_spinner()
        self._busy = False
        self._entry.configure(state="disabled")

        # Build password frame
        self._pwd_frame = tk.Frame(self._feed_area, bg=BG_CARD, padx=SP_SECTION, pady=SP_DEFAULT)
        self._pwd_frame.pack(fill="x", pady=(SP_DEFAULT, 0))

        tk.Label(
            self._pwd_frame,
            text=msg,
            font=self._f["step"],
            fg=FG,
            bg=BG_CARD,
            wraplength=600,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(0, SP_COMPACT))

        # Masked entry
        pwd_row = tk.Frame(self._pwd_frame, bg=BG_CARD)
        pwd_row.pack(fill="x", pady=(0, SP_COMPACT))

        self._pwd_entry = tk.Entry(
            pwd_row,
            font=self._f["input"],
            bg=BG_INPUT,
            fg=FG,
            insertbackground=ACCENT,
            relief="flat",
            show="●",
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BORDER,
        )
        self._pwd_entry.pack(fill="x", ipady=6)
        self._pwd_entry.bind("<Return>", lambda e: self._on_pwd_confirm())
        self._pwd_entry.bind("<Escape>", lambda e: self._on_pwd_cancel())

        # Buttons
        btn_row = tk.Frame(self._pwd_frame, bg=BG_CARD)
        btn_row.pack(anchor="w", pady=(SP_COMPACT, 0))

        confirm_btn = tk.Button(
            btn_row,
            text="Confirmar",
            font=self._f["btn"],
            bg=ACCENT,
            fg="#fff",
            activebackground=ACCENT_LT,
            activeforeground="#fff",
            relief="flat",
            padx=18,
            pady=5,
            command=self._on_pwd_confirm,
        )
        confirm_btn.pack(side="left", padx=(0, 10))

        tk.Button(
            btn_row,
            text="Cancelar",
            font=self._f["btn"],
            bg=BG_INPUT,
            fg=FG_DIM,
            activebackground=BG_HOVER,
            activeforeground=FG,
            relief="flat",
            padx=18,
            pady=5,
            command=self._on_pwd_cancel,
        ).pack(side="left")

        # Focus the password field
        self._pwd_entry.focus_set()

    def _on_pwd_confirm(self) -> None:
        """Submit the password and execute the command."""
        password = self._pwd_entry.get()
        self._pwd_frame.pack_forget()
        if not password or not self._pending:
            self._on_pwd_cancel()
            return
        cmd = self._pending
        self._pending = None
        self._busy = True
        self._cancelled = False
        self._entry.configure(state="disabled")
        self._send_btn_outer.pack_forget()
        self._cancel_btn_outer.pack(side="right", padx=(SP_TIGHT, SP_COMPACT), pady=10)
        self._clear_feed()
        self._clear_result()
        self._start_spinner()
        self._add_step("Executando…", thinking=True)
        # Send password as the answer to the pending question
        threading.Thread(
            target=lambda: self._display(self._bridge.execute_command(password)), daemon=True
        ).start()

    def _on_pwd_cancel(self) -> None:
        """Cancel the password prompt."""
        self._pending = None
        if hasattr(self, "_pwd_frame"):
            self._pwd_frame.pack_forget()
        # Clear the pending question in bridge
        try:
            self._bridge._thread_manager.clear_pending_question()
        except Exception:
            pass
        self._show_result("Cancelado", "Nenhuma alteração feita", "success")
        self._finish()

    def _on_cancel_intent(self) -> None:
        """Cancel a running intent execution."""
        self._cancelled = True
        # Signal the bridge to abort (interrupts LLM waits)
        self._bridge.cancel()
        if self._dot_id:
            self.root.after_cancel(self._dot_id)
            self._dot_id = None
        self._clear_feed()
        self._stop_spinner()
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

        # Stop spinner on result
        self.root.after(delay, self._stop_spinner)
        self.root.after(delay, self._dim_steps)

        # Check for Gallery_Signal — render gallery instead of text result
        gallery_data = data.get("gallery")
        if gallery_data:
            self.root.after(delay + 80, lambda: self._show_gallery(gallery_data))
        elif self._is_artifact_content(result_text):
            # Multi-section artifact — show in split panel
            self.root.after(delay + 80, lambda: self._show_artifact(result_text))
        else:
            titles = {
                "success": "Concluído",
                "recovered": "Corrigido",
                "error": "Problema",
            }
            self.root.after(
                delay + 80,
                lambda: self._show_result(titles.get(status, "Concluído"), result_text, status),
            )

        self.root.after(delay + 150, self._finish)

        # Voice output (async, never blocks)
        if result_text:
            self.root.after(delay + 200, lambda: self._voice.speak(result_text, voice_mode))

        # Refresh Intelligence sidebar (usage counter may have changed)
        self.root.after(delay + 300, self._refresh_intelligence_ui)
        # Refresh sidebar thread history
        self.root.after(delay + 350, self._refresh_sidebar_threads)

    # ── Spinner (only visible when processing) ─────────────────────────

    def _start_spinner(self) -> None:
        """Show and animate the processing spinner."""
        self._spinner_phase = 0.0
        self._animate_spinner()

    def _stop_spinner(self) -> None:
        """Hide the spinner."""
        if self._spinner_anim_id:
            self.root.after_cancel(self._spinner_anim_id)
            self._spinner_anim_id = None

    def _animate_spinner(self) -> None:
        """Rotate the arc and pulse the center dot."""
        if not self._spinner_canvas.winfo_exists():
            return
        import math

        self._spinner_phase += 8  # degrees per frame
        # Rotate the arc
        self._spinner_canvas.itemconfig(self._spinner_arc, start=self._spinner_phase % 360)
        # Pulse the dot brightness
        t = (math.sin(self._spinner_phase * 0.05) + 1) / 2
        dot_color = _lerp(ACCENT_DK, ACCENT_LT, t)
        self._spinner_canvas.itemconfig(self._spinner_dot, fill=dot_color)
        self._spinner_anim_id = self.root.after(T_RING, self._animate_spinner)

    # ── Feed ─────────────────────────────────────────────────────────────

    def _clear_feed(self) -> None:
        if self._dot_id:
            self.root.after_cancel(self._dot_id)
            self._dot_id = None
        for w in self._step_widgets:
            w.destroy()
        self._step_widgets.clear()

    def _add_step(self, text: str, thinking: bool = False) -> None:
        lbl = tk.Label(self._feed, text=f"  {text}", font=self._f["step"], fg=BG, bg=BG, anchor="w")
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
        self._dot_id = self.root.after(T_DOTS, lambda: self._animate_dots(lbl, base, n + 1))

    def _dim_steps(self) -> None:
        for lbl in self._step_widgets:
            if lbl.winfo_exists():
                self._anim.color([lbl], "fg", FG_DIM, T_NORMAL)

    # ── Result ───────────────────────────────────────────────────────────

    def _clear_result(self) -> None:
        self._res_title.pack_forget()
        self._res_body.pack_forget()
        self._result_frame.pack_forget()
        self._destroy_active_gallery()

    def _show_result(self, title: str, body: str, status: str) -> None:
        colors = {"success": SUCCESS, "recovered": WARNING, "error": ERROR}
        icons = {"success": "✓", "recovered": "✓", "error": "✗"}
        color = colors.get(status, SUCCESS)
        icon = icons.get(status, "✓")

        self._result_frame.pack(fill="x", pady=(SP_DEFAULT, 0))
        self._res_title.configure(text=f"{icon}  {title}", fg=color)
        self._res_title.pack(fill="x", pady=(0, SP_TIGHT))

        if body:
            # Line spacing 1.5 via padding between lines
            self._res_body.configure(text=body, fg=FG_SEC)
            self._res_body.pack(fill="x")

    def _show_gallery(self, gallery_data: dict) -> None:
        """Render a GalleryComponent in the feed_area for a Gallery_Signal."""
        # Clear existing result/gallery (this also calls _destroy_active_gallery)
        self._clear_result()
        # Instantiate GalleryComponent in the feed_area frame
        self._active_gallery = GalleryComponent(
            parent=self._feed_area,
            gallery_data=gallery_data,
            root=self.root,
            fonts=self._f,
        )

    def _destroy_active_gallery(self) -> None:
        """Destroy the active gallery component if one exists."""
        if self._active_gallery is not None:
            self._active_gallery.destroy()
            self._active_gallery = None

    def _is_artifact_content(self, text: str) -> bool:
        """Detect if response is multi-section artifact content."""
        if not text or len(text) < 300:
            return False
        # Check for section separators or platform headers
        has_separators = "=== " in text
        has_platform_headers = ("LinkedIn" in text and "Twitter" in text) or (
            "linkedin" in text.lower() and "twitter" in text.lower()
        )
        return has_separators or has_platform_headers

    def _show_artifact(self, content: str) -> None:
        """Show artifact content in the center feed area (never replaces sidebar)."""
        from cios.ui.artifact_panel import ArtifactPanel

        # Show artifact inline in the feed area
        self._result_frame.pack(fill="both", expand=True, pady=(SP_DEFAULT, 0))

        self._artifact_panel = ArtifactPanel(
            parent=self._result_frame,
            fonts=self._f,
            on_close=self._close_artifact,
        )
        self._artifact_panel.show(content)

    def _close_artifact(self) -> None:
        """Close artifact panel in the feed area."""
        if hasattr(self, "_artifact_panel") and self._artifact_panel:
            self._artifact_panel.hide()
            self._artifact_panel = None
        self._clear_result()

    def _show_confirm(self, msg: str, cmd: str) -> None:
        self._pending = cmd
        self._confirm_msg.configure(text=msg)
        self._confirm_frame.pack(fill="x", pady=(SP_DEFAULT, 0))
        if self._dot_id:
            self.root.after_cancel(self._dot_id)
            self._dot_id = None
        self._clear_feed()
        self._busy = False
        self._entry.configure(state="disabled")
        # Focus the confirm button so Enter triggers confirmation, not re-submit
        self._confirm_btn.focus_set()

    def _finish(self) -> None:
        self._busy = False
        self._cancelled = False
        self._entry.configure(state="normal")
        self._entry.delete("1.0", "end")
        self._entry.focus_set()
        # Swap cancel → send button
        self._cancel_btn_outer.pack_forget()
        self._send_btn_outer.pack(pady=(0, SP_TIGHT))
        self._ph = False
        # Stop spinner, keep result visible
        self._stop_spinner()
        self._spinner_frame.pack_forget()
        # Refresh thread panel below prompt
        self._thread_panel.refresh()

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
        """Detect secondary monitors and spawn interaction panels."""
        import logging as _log

        _logger = _log.getLogger(__name__)
        try:
            from cios.infra.monitors import get_secondary_monitors
            from cios.ui.gui_secondary import SecondaryPanel

            secondaries = get_secondary_monitors()
            if secondaries:
                _logger.info("Found %d secondary monitor(s)", len(secondaries))
            for monitor in secondaries:
                try:
                    panel = SecondaryPanel(self.root, monitor, bridge=self._bridge)
                    self._secondary_panels.append(panel)
                    _logger.info(
                        "Secondary panel on %s (%dx%d+%d+%d)",
                        monitor.name,
                        monitor.width,
                        monitor.height,
                        monitor.x,
                        monitor.y,
                    )
                except Exception as e:
                    _logger.warning("Failed to create panel on %s: %s", monitor.name, e)
        except Exception as e:
            _logger.warning("Secondary screen init failed: %s", e)

    def run(self) -> None:
        # Auto-start topbar as a daemon thread (always visible in session)
        from cios.ui.topbar import start_topbar_thread

        self._topbar_thread = start_topbar_thread()

        # Signal splash screen to close (we're rendered and ready)
        self.root.after(100, self._signal_ready)
        self.root.mainloop()

    def _signal_ready(self) -> None:
        """Tell the splash screen we're ready — it can close now."""
        try:
            from cios.ui.splash import signal_splash_done

            signal_splash_done()
        except Exception:
            pass


def run_gui() -> None:
    CIOSApp().run()
