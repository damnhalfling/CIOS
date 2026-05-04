"""Hotkey global — Ctrl+Space overlay for quick commands.

Listens for a global hotkey (default: Ctrl+Space) and shows a minimal
floating input overlay. Commands are sent to the daemon via Unix socket.

Requires: xdotool (for key grabbing) or Xlib.

Architecture:
- Runs as a separate lightweight process
- Communicates with daemon via Unix socket
- Shows a minimal Tkinter overlay (no full GUI)
- Auto-hides after command execution
"""

import logging
import os
import subprocess
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_HOTKEY = os.environ.get("HARMONI_HOTKEY", "ctrl+space")


def _grab_hotkey_xdotool(callback) -> None:
    """Use xdotool/xbindkeys approach for hotkey detection."""
    # We use a subprocess-based approach with xbindkeys
    # This is more reliable than python-xlib for global hotkeys
    import subprocess
    import tempfile

    # Create xbindkeys config
    config = f'"{sys.executable} -c \\"import harmoni.hotkey; harmoni.hotkey._show_overlay()\\""\\n  Control + space\\n'

    config_path = os.path.expanduser("~/.xbindkeysrc.harmoni")
    with open(config_path, "w") as f:
        f.write(config)

    # Start xbindkeys with our config
    try:
        subprocess.Popen(
            ["xbindkeys", "-f", config_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Hotkey registered: %s", _HOTKEY)
    except FileNotFoundError:
        logger.warning("xbindkeys not found — hotkey disabled")


def _show_overlay() -> None:
    """Show the minimal floating input overlay with state ring."""
    try:
        import tkinter as tk
    except ImportError:
        logger.error("Tkinter not available for overlay")
        return

    from harmoni.infra.daemon import send_command, is_daemon_running
    from harmoni.ui.theme import (
        BG_PANEL, BG_INPUT, BG_CARD, BG_HOVER,
        FG, FG_SEC, FG_DIM,
        ACCENT, ACCENT_LT, ACCENT_DK,
        SUCCESS, ERROR, WARNING,
        RING_IDLE, RING_PROCESSING, RING_SUCCESS, RING_ERROR,
        T_RING, lerp,
    )

    if not is_daemon_running():
        # Try to start daemon in background
        subprocess.Popen(
            [sys.executable, "-m", "harmoni", "--daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

    root = tk.Tk()
    root.title("Harmoni")
    root.overrideredirect(True)  # no window decorations
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.97)

    # Center on screen — wider to feel like the main interface
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    w, h = 560, 72
    x = (screen_w - w) // 2
    y = (screen_h - h) // 3  # upper third

    root.geometry(f"{w}x{h}+{x}+{y}")
    root.configure(bg=BG_PANEL)

    # Input frame
    frame = tk.Frame(root, bg=BG_PANEL, padx=16, pady=14)
    frame.pack(fill=tk.BOTH, expand=True)

    # State ring (mini version)
    ring_canvas = tk.Canvas(
        frame, width=32, height=32,
        bg=BG_PANEL, highlightthickness=0, bd=0)
    ring_canvas.pack(side=tk.LEFT, padx=(0, 12))
    ring_id = ring_canvas.create_oval(4, 4, 28, 28, outline=RING_IDLE, width=2)
    symbol_id = ring_canvas.create_text(16, 16, text="✦", fill=ACCENT_LT,
                                         font=("Helvetica", 11))

    # Breathing animation for ring
    ring_phase = [0.0]
    ring_state = ["idle"]
    ring_anim_id = [None]

    def animate_ring():
        import math
        if not root.winfo_exists():
            return
        ring_phase[0] += 0.05 if ring_state[0] == "idle" else 0.12
        t = (math.sin(ring_phase[0]) + 1) / 2
        if ring_state[0] == "idle":
            color = lerp(ACCENT_DK, ACCENT_LT, t)
            ring_canvas.itemconfig(ring_id, outline=color, width=2)
            sym_color = lerp(FG_DIM, ACCENT_LT, t * 0.6)
            ring_canvas.itemconfig(symbol_id, fill=sym_color)
        elif ring_state[0] == "processing":
            color = lerp(ACCENT_DK, ACCENT_LT, t)
            ring_canvas.itemconfig(ring_id, outline=color, width=3)
            sym_color = lerp(FG_DIM, ACCENT, t)
            ring_canvas.itemconfig(symbol_id, fill=sym_color)
        ring_anim_id[0] = root.after(T_RING, animate_ring)

    animate_ring()

    # Input field
    entry = tk.Entry(
        frame,
        font=("Helvetica", 15),
        fg=FG,
        bg=BG_INPUT,
        insertbackground=ACCENT,
        relief=tk.FLAT,
        highlightthickness=1,
        highlightcolor=ACCENT,
        highlightbackground=BG_CARD,
    )
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
    entry.focus_set()

    # Result label (hidden initially)
    result_var = tk.StringVar()
    result_label = tk.Label(
        root, textvariable=result_var,
        font=("Helvetica", 11), fg=FG_SEC, bg=BG_PANEL,
        wraplength=520, justify=tk.LEFT,
    )

    def submit(event=None):
        text = entry.get().strip()
        if not text:
            root.destroy()
            return

        entry.config(state=tk.DISABLED)
        ring_state[0] = "processing"
        ring_canvas.itemconfig(symbol_id, text="⟳")

        def execute():
            response = send_command(text)
            if response:
                status = response.get("status", "error")
                result = response.get("result", "")
                if status in ("success", "recovered"):
                    color = SUCCESS
                    ring_canvas.itemconfig(ring_id, outline=RING_SUCCESS)
                    ring_canvas.itemconfig(symbol_id, text="✓", fill=RING_SUCCESS)
                else:
                    color = ERROR
                    ring_canvas.itemconfig(ring_id, outline=RING_ERROR)
                    ring_canvas.itemconfig(symbol_id, text="✗", fill=RING_ERROR)
                ring_state[0] = "done"
                result_var.set(result[:120])
                result_label.config(fg=color)
                result_label.pack(padx=16, pady=(0, 8))
                root.geometry(f"{w}x{h + 30}+{x}+{y}")
            else:
                ring_state[0] = "done"
                ring_canvas.itemconfig(ring_id, outline=RING_ERROR)
                ring_canvas.itemconfig(symbol_id, text="✗", fill=RING_ERROR)
                result_var.set("Daemon não está rodando")
                result_label.config(fg=ERROR)
                result_label.pack(padx=16, pady=(0, 8))
                root.geometry(f"{w}x{h + 30}+{x}+{y}")

            # Auto-close after 2 seconds
            root.after(2000, root.destroy)

        threading.Thread(target=execute, daemon=True).start()

    def cancel(event=None):
        root.destroy()

    entry.bind("<Return>", submit)
    entry.bind("<Escape>", cancel)
    root.bind("<FocusOut>", cancel)

    root.mainloop()


def start_hotkey_listener() -> None:
    """Start the global hotkey listener (runs in background thread)."""
    thread = threading.Thread(target=_grab_hotkey_xdotool, args=(None,), daemon=True)
    thread.start()
    logger.info("Hotkey listener started")


def run_overlay() -> None:
    """Entry point for showing the overlay directly."""
    _show_overlay()
