"""Secondary screen — interaction environment.

Full interaction surface on secondary monitors.
Same layout as main GUI (prompt at bottom, feed above) but without
the right sidebar. Shares the bridge with the main window.
"""

import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional

from cios.infra.monitors import Monitor

# Design tokens (same as main GUI)
BG         = "#0b0f14"
BG_PANEL   = "#0f1319"
BG_CARD    = "#111827"
BG_INPUT   = "#111827"
BG_HOVER   = "#1f2937"
BORDER     = "#1f2937"
FG         = "#e5e7eb"
FG_SEC     = "#9ca3af"
FG_DIM     = "#6b7280"
ACCENT     = "#7c3aed"
ACCENT_LT  = "#a78bfa"
SUCCESS    = "#22c55e"
WARNING    = "#eab308"
ERROR      = "#ef4444"

# Spacing
SP_PAGE    = 48
SP_SECTION = 24
SP_DEFAULT = 16
SP_COMPACT = 10
SP_TIGHT   = 6
SP_MICRO   = 4

# Timing
T_STEP     = 180
T_SLOW     = 300
T_FAST     = 120
T_NORMAL   = 200


class SecondaryPanel:
    """Interaction panel for a secondary monitor — no sidebar."""

    def __init__(self, root: tk.Tk, monitor: Monitor, bridge=None) -> None:
        self._root = root
        self._monitor = monitor
        self._bridge = bridge
        self._win: Optional[tk.Toplevel] = None
        self._busy = False
        self._pending: Optional[str] = None
        self._step_widgets: list[tk.Label] = []
        self._ph = True
        self._cancelled = False
        self._build()

    def set_bridge(self, bridge) -> None:
        """Set the bridge after construction (allows deferred init)."""
        self._bridge = bridge

    def _build(self) -> None:
        self._win = tk.Toplevel(self._root)
        self._win.title("CIOS — Extended")
        self._win.configure(bg=BG)

        # Position on secondary monitor (fullscreen, no decoration via openbox rule)
        geo = (f"{self._monitor.width}x{self._monitor.height}"
               f"+{self._monitor.x}+{self._monitor.y}")
        self._win.geometry(geo)
        # Set WM class so openbox applies decor=no rule
        self._win.wm_attributes("-type", "normal")
        # Request no resizing (prevents WM from adding resize handles)
        self._win.resizable(False, False)

        # Fonts
        self._f = {
            "greet":   tkfont.Font(family="Helvetica", size=22, weight="bold"),
            "sub":     tkfont.Font(family="Helvetica", size=13),
            "input":   tkfont.Font(family="Helvetica", size=14),
            "step":    tkfont.Font(family="Helvetica", size=12),
            "res_t":   tkfont.Font(family="Helvetica", size=14, weight="bold"),
            "res_b":   tkfont.Font(family="Helvetica", size=12),
            "btn":     tkfont.Font(family="Helvetica", size=11),
            "small":   tkfont.Font(family="Helvetica", size=9),
        }

        # Main container — single column, no sidebar
        container = tk.Frame(self._win, bg=BG)
        container.pack(fill="both", expand=True)

        # ═══ TOP AREA: feed + results (grows) ═══
        self._feed_area = tk.Frame(container, bg=BG, padx=SP_PAGE, pady=SP_SECTION)
        self._feed_area.pack(fill="both", expand=True)

        # Greeting
        self._greeting_frame = tk.Frame(self._feed_area, bg=BG)
        self._greeting_frame.pack(fill="both", expand=True)

        tk.Frame(self._greeting_frame, bg=BG).pack(fill="both", expand=True)
        center = tk.Frame(self._greeting_frame, bg=BG)
        center.pack()
        tk.Label(center, text="CIOS", font=self._f["greet"],
                 fg=FG, bg=BG).pack()
        tk.Label(center, text="O que vamos fazer?", font=self._f["sub"],
                 fg=FG_DIM, bg=BG).pack(pady=(SP_MICRO, 0))
        tk.Frame(self._greeting_frame, bg=BG).pack(fill="both", expand=True)

        # Spinner (hidden)
        self._spinner_frame = tk.Frame(self._feed_area, bg=BG)
        self._spinner_canvas = tk.Canvas(
            self._spinner_frame, width=36, height=36,
            bg=BG, highlightthickness=0, bd=0)
        self._spinner_canvas.pack(pady=(SP_DEFAULT, SP_COMPACT))
        self._spinner_arc = self._spinner_canvas.create_arc(
            4, 4, 32, 32, start=0, extent=270,
            outline=ACCENT, width=3, style="arc")
        self._spinner_dot = self._spinner_canvas.create_oval(
            14, 14, 22, 22, fill=ACCENT_LT, outline="")
        self._spinner_phase = 0.0
        self._spinner_anim_id: Optional[str] = None

        # Feed (execution steps)
        self._feed = tk.Frame(self._feed_area, bg=BG)

        # Confirm dialog
        self._confirm_frame = tk.Frame(self._feed_area, bg=BG_CARD,
                                       padx=SP_SECTION, pady=SP_DEFAULT)
        self._confirm_msg = tk.Label(self._confirm_frame, font=self._f["step"],
                                     fg=FG, bg=BG_CARD, wraplength=600,
                                     justify="left", anchor="w")
        self._confirm_msg.pack(fill="x", pady=(0, SP_COMPACT))

        btn_row = tk.Frame(self._confirm_frame, bg=BG_CARD)
        btn_row.pack(anchor="w")
        self._confirm_btn = tk.Button(
            btn_row, text="Confirmar", font=self._f["btn"],
            bg=ACCENT, fg="#fff", activebackground=ACCENT_LT,
            activeforeground="#fff", relief="flat",
            padx=18, pady=5, command=self._on_confirm)
        self._confirm_btn.pack(side="left", padx=(0, 10))
        self._confirm_btn.bind("<Return>", lambda e: self._on_confirm())
        tk.Button(btn_row, text="Cancelar", font=self._f["btn"],
                  bg=BG_INPUT, fg=FG_DIM, activebackground=BG_HOVER,
                  activeforeground=FG, relief="flat",
                  padx=18, pady=5, command=self._on_cancel).pack(side="left")

        # Result
        self._result_frame = tk.Frame(self._feed_area, bg=BG)
        self._res_title = tk.Label(self._result_frame, font=self._f["res_t"],
                                   bg=BG, anchor="w", justify="left")
        self._res_body = tk.Label(self._result_frame, font=self._f["res_b"],
                                  bg=BG, fg=FG_SEC, wraplength=600,
                                  justify="left", anchor="w")

        # ═══ BOTTOM: prompt ═══
        self._prompt_area = tk.Frame(container, bg=BG_PANEL, padx=SP_PAGE, pady=SP_DEFAULT)
        self._prompt_area.pack(fill="x", side="bottom")

        self._prompt_glow = tk.Frame(self._prompt_area, bg=BORDER, padx=2, pady=2)
        self._prompt_glow.pack(fill="x")

        prompt_inner = tk.Frame(self._prompt_glow, bg=BG_INPUT)
        prompt_inner.pack(fill="x")

        tk.Label(prompt_inner, text="✦", font=self._f["input"],
                 fg=FG_DIM, bg=BG_INPUT).pack(
            side="left", padx=(SP_DEFAULT, 10), anchor="n", pady=SP_COMPACT)

        self._entry = tk.Text(
            prompt_inner, font=self._f["input"], bg=BG_INPUT, fg=FG,
            insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=0, height=2, wrap="word")
        self._entry.pack(side="left", fill="both", expand=True,
                         pady=SP_COMPACT, padx=(0, SP_TIGHT))
        self._entry.bind("<Return>", self._on_enter_key)

        # Focus glow
        self._entry.bind("<FocusIn>", lambda _: self._prompt_glow.configure(bg=ACCENT))
        self._entry.bind("<FocusOut>", lambda _: self._prompt_glow.configure(bg=BORDER))

        # Send button
        btn_frame = tk.Frame(prompt_inner, bg=BG_INPUT)
        btn_frame.pack(side="right", padx=(0, SP_COMPACT), pady=SP_COMPACT, anchor="s")

        send_outer = tk.Frame(btn_frame, bg=ACCENT, padx=1, pady=1)
        send_outer.pack(pady=(0, SP_TIGHT))
        self._send_btn_outer = send_outer
        send_btn = tk.Label(send_outer, text=" Enviar ", font=self._f["btn"],
                            fg="#fff", bg=ACCENT, pady=3, padx=SP_TIGHT,
                            cursor="hand2")
        send_btn.pack()

        for w in [send_outer, send_btn]:
            w.bind("<Button-1>", self._on_enter)
            w.configure(cursor="hand2")

        # Placeholder
        self._entry.insert("1.0", "Diga o que precisa…")
        self._entry.configure(fg=FG_DIM)
        self._entry.bind("<FocusIn>", self._ph_clear, add="+")
        self._entry.bind("<FocusOut>", self._ph_restore, add="+")

    # ── Input handling ──

    def _on_enter_key(self, event=None) -> str:
        if event and (event.state & 0x1):
            return ""
        self._on_enter()
        return "break"

    def _on_enter(self, _=None) -> None:
        if self._busy:
            return
        text = self._entry.get("1.0", "end").strip()
        if not text or self._ph:
            return
        self._submit(text)

    def _submit(self, text: str) -> None:
        if not self._bridge:
            return
        self._busy = True
        self._cancelled = False
        self._entry.configure(state="disabled")
        self._clear_result()
        self._confirm_frame.pack_forget()
        self._greeting_frame.pack_forget()
        self._clear_feed()
        self._start_spinner()
        self._add_step("Entendendo…", thinking=True)
        threading.Thread(target=self._run, args=(text,), daemon=True).start()

    def _run(self, text: str) -> None:
        data = self._bridge.execute_command(text)
        if data.get("confirm"):
            self._root.after(0, lambda: self._show_confirm(data["confirm"], text))
            return
        self._display(data)

    def _display(self, data: dict) -> None:
        if self._cancelled:
            return
        steps = data.get("steps", [])
        result_text = data.get("result", "")
        status = data.get("status", "success")

        self._root.after(0, self._clear_feed)

        for i, s in enumerate(steps):
            self._root.after(i * T_STEP, lambda s=s: self._add_step(s))

        delay = len(steps) * T_STEP + T_SLOW
        titles = {
            "success": "Concluído",
            "recovered": "Corrigido",
            "error": "Problema",
        }

        self._root.after(delay, self._stop_spinner)
        self._root.after(delay + 80, lambda: self._show_result(
            titles.get(status, "Concluído"), result_text, status))
        self._root.after(delay + 150, self._finish)

    # ── Confirm ──

    def _show_confirm(self, msg: str, cmd: str) -> None:
        self._pending = cmd
        self._confirm_msg.configure(text=msg)
        self._confirm_frame.pack(fill="x", pady=(SP_DEFAULT, 0))
        self._clear_feed()
        self._stop_spinner()
        self._busy = False
        self._entry.configure(state="disabled")
        self._confirm_btn.focus_set()

    def _on_confirm(self) -> None:
        cmd = self._pending
        self._pending = None
        self._confirm_frame.pack_forget()
        if not cmd or not self._bridge:
            return
        self._busy = True
        self._entry.configure(state="disabled")
        self._clear_feed()
        self._clear_result()
        self._add_step("Executando…", thinking=True)
        self._start_spinner()
        threading.Thread(
            target=lambda: self._display(
                self._bridge.execute_command(cmd, confirmed=True)),
            daemon=True).start()

    def _on_cancel(self) -> None:
        self._pending = None
        self._confirm_frame.pack_forget()
        self._show_result("Cancelado", "Nenhuma alteração feita", "success")
        self._finish()

    # ── Feed / Result ──

    def _add_step(self, text: str, thinking: bool = False) -> None:
        lbl = tk.Label(self._feed, text=f"  {'⟳' if thinking else '•'}  {text}",
                       font=self._f["step"], fg=FG_SEC if not thinking else FG_DIM,
                       bg=BG, anchor="w")
        lbl.pack(fill="x")
        self._step_widgets.append(lbl)
        self._feed.pack(fill="x")

    def _clear_feed(self) -> None:
        for w in self._step_widgets:
            w.destroy()
        self._step_widgets.clear()
        self._feed.pack_forget()

    def _show_result(self, title: str, body: str, status: str) -> None:
        self._result_frame.pack(fill="x", pady=(SP_DEFAULT, 0))
        colors = {"success": SUCCESS, "recovered": WARNING, "error": ERROR}
        icons = {"success": "✓", "recovered": "⟳", "error": "✗"}
        color = colors.get(status, FG)
        icon = icons.get(status, "•")

        self._res_title.configure(text=f"{icon}  {title}", fg=color)
        self._res_title.pack(fill="x", pady=(0, SP_TIGHT))
        if body:
            self._res_body.configure(text=body, fg=FG_SEC)
            self._res_body.pack(fill="x")

    def _clear_result(self) -> None:
        self._res_title.pack_forget()
        self._res_body.pack_forget()
        self._result_frame.pack_forget()

    def _finish(self) -> None:
        self._busy = False
        self._cancelled = False
        self._entry.configure(state="normal")
        self._entry.delete("1.0", "end")
        self._entry.focus_set()
        self._stop_spinner()
        self._spinner_frame.pack_forget()
        self._ph = False

    # ── Spinner ──

    def _start_spinner(self) -> None:
        self._spinner_frame.pack(before=self._feed, pady=(SP_DEFAULT, 0))
        self._spinner_phase = 0.0
        self._animate_spinner()

    def _stop_spinner(self) -> None:
        if self._spinner_anim_id:
            self._root.after_cancel(self._spinner_anim_id)
            self._spinner_anim_id = None
        self._spinner_frame.pack_forget()

    def _animate_spinner(self) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        self._spinner_phase += 12
        self._spinner_canvas.itemconfigure(
            self._spinner_arc, start=self._spinner_phase)
        # Pulse dot
        import math
        scale = 0.8 + 0.2 * math.sin(self._spinner_phase * 0.05)
        cx, cy = 18, 18
        r = 4 * scale
        self._spinner_canvas.coords(
            self._spinner_dot, cx - r, cy - r, cx + r, cy + r)
        self._spinner_anim_id = self._root.after(30, self._animate_spinner)

    # ── Placeholder ──

    def _ph_clear(self, _=None) -> None:
        if self._ph:
            self._entry.delete("1.0", "end")
            self._entry.configure(fg=FG)
            self._ph = False

    def _ph_restore(self, _=None) -> None:
        text = self._entry.get("1.0", "end").strip()
        if not text:
            self._entry.insert("1.0", "Diga o que precisa…")
            self._entry.configure(fg=FG_DIM)
            self._ph = True

    # ── Lifecycle ──

    def _grab_focus(self) -> None:
        """Force focus to this window and entry."""
        self._win.focus_force()
        self._win.lift()
        if not self._busy:
            self._entry.focus_set()

    def close(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.destroy()
