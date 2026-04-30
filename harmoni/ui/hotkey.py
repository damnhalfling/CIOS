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
    """Show the minimal floating input overlay."""
    try:
        import tkinter as tk
    except ImportError:
        logger.error("Tkinter not available for overlay")
        return

    from harmoni.infra.daemon import send_command, is_daemon_running

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
    root.attributes("-alpha", 0.95)

    # Center on screen
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    w, h = 500, 60
    x = (screen_w - w) // 2
    y = (screen_h - h) // 3  # upper third

    root.geometry(f"{w}x{h}+{x}+{y}")
    root.configure(bg="#1a1a2e")

    # Input frame
    frame = tk.Frame(root, bg="#1a1a2e", padx=16, pady=12)
    frame.pack(fill=tk.BOTH, expand=True)

    # Prompt icon
    icon = tk.Label(frame, text="✦", font=("Inter", 16), fg="#7c6ff7", bg="#1a1a2e")
    icon.pack(side=tk.LEFT, padx=(0, 10))

    # Input field
    entry = tk.Entry(
        frame,
        font=("Inter", 14),
        fg="#e2e2e8",
        bg="#16161e",
        insertbackground="#7c6ff7",
        relief=tk.FLAT,
        highlightthickness=1,
        highlightcolor="#7c6ff7",
        highlightbackground="#2a2a3e",
    )
    entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    entry.focus_set()

    # Result label (hidden initially)
    result_var = tk.StringVar()
    result_label = tk.Label(
        root, textvariable=result_var,
        font=("Inter", 11), fg="#8a8a9a", bg="#1a1a2e",
        wraplength=460, justify=tk.LEFT,
    )

    def submit(event=None):
        text = entry.get().strip()
        if not text:
            root.destroy()
            return

        entry.config(state=tk.DISABLED)
        icon.config(text="⟳")

        def execute():
            response = send_command(text)
            if response:
                status = response.get("status", "error")
                result = response.get("result", "")
                color = "#4ade80" if status == "success" else (
                    "#facc15" if status == "recovered" else "#f87171"
                )
                result_var.set(result[:100])
                result_label.config(fg=color)
                result_label.pack(padx=16, pady=(0, 8))
                root.geometry(f"{w}x{h + 30}+{x}+{y}")
            else:
                result_var.set("Daemon not running")
                result_label.config(fg="#f87171")
                result_label.pack(padx=16, pady=(0, 8))
                root.geometry(f"{w}x{h + 30}+{x}+{y}")

            icon.config(text="✓" if response and response.get("status") == "success" else "✗")
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
