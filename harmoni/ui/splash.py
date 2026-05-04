"""Splash screen — shown instantly while Harmoni loads.

Displays a minimal, branded loading screen that:
- Appears in <100ms (before any heavy imports)
- Shows real boot progress stages (not just "Iniciando…")
- Matches the main GUI color scheme (seamless transition)
- Closes automatically when the main GUI signals ready
- Uses the same state ring visual language as the main interface

Can also run standalone for the session script:
    python3 -m harmoni.splash &
    SPLASH_PID=$!
    # ... start main app ...
    kill $SPLASH_PID
"""

import os
import sys
import signal
import time


# ═══════════════════════════════════════════════════════════════════════════
#  PROGRESS FILE PROTOCOL
# ═══════════════════════════════════════════════════════════════════════════
# Main app writes progress to ~/.harmoni/.splash_progress
# Format: "stage_text|current|total"  e.g. "Detectando wifi…|2|6"
# Splash polls this file every 80ms for smooth updates.
# When ~/.harmoni/.splash_done exists, splash closes.

_READY_FILE = os.path.expanduser("~/.harmoni/.splash_done")
_PROGRESS_FILE = os.path.expanduser("~/.harmoni/.splash_progress")


def show_splash() -> None:
    """Show splash screen. Blocks until killed or timeout (10s)."""
    # Clean up stale files
    for f in (_READY_FILE, _PROGRESS_FILE):
        try:
            os.unlink(f)
        except OSError:
            pass

    try:
        import tkinter as tk
    except ImportError:
        _wait_for_signal()
        return

    # Import theme tokens (lightweight, no heavy deps)
    from harmoni.ui.theme import (
        BG, ACCENT, ACCENT_LT, ACCENT_DK, FG, FG_DIM, BG_CARD, lerp,
    )

    root = tk.Tk()
    root.title("Harmoni")
    root.attributes("-fullscreen", True)
    root.configure(bg=BG)
    root.overrideredirect(True)

    # Center content
    frame = tk.Frame(root, bg=BG)
    frame.place(relx=0.5, rely=0.45, anchor=tk.CENTER)

    # State ring (same visual as main GUI — creates continuity)
    ring_size = 72
    ring_canvas = tk.Canvas(
        frame, width=ring_size, height=ring_size,
        bg=BG, highlightthickness=0, bd=0)
    ring_canvas.pack(pady=(0, 16))
    ring_id = ring_canvas.create_oval(
        6, 6, ring_size - 6, ring_size - 6,
        outline=ACCENT_LT, width=3)

    # Logo (PNG if available, fallback to symbol inside ring)
    from harmoni.core.config import get_logo_path
    _logo_img = None  # prevent GC
    logo_path = get_logo_path()
    if logo_path:
        try:
            raw = tk.PhotoImage(file=str(logo_path))
            scale = max(1, raw.width() // 48)
            _logo_img = raw.subsample(scale, scale)
            logo_item = ring_canvas.create_image(
                ring_size // 2, ring_size // 2, image=_logo_img)
            ring_canvas.image = _logo_img  # prevent GC
        except Exception:
            _logo_img = None

    if not _logo_img:
        ring_canvas.create_text(
            ring_size // 2, ring_size // 2,
            text="✦", font=("Helvetica", 24), fill=ACCENT_LT)

    # Brand name
    brand = tk.Label(
        frame, text="Harmoni", font=("Helvetica", 28, "bold"),
        fg=FG, bg=BG,
    )
    brand.pack(pady=(0, 8))

    # Loading text (updates with real progress)
    loading = tk.Label(
        frame, text="Iniciando…", font=("Helvetica", 12),
        fg=FG_DIM, bg=BG,
    )
    loading.pack(pady=(0, 12))

    # Progress bar (thin, elegant)
    screen_w = root.winfo_screenwidth()
    bar_width = min(300, screen_w // 4)
    bar_frame = tk.Frame(frame, bg=BG_CARD, height=3, width=bar_width)
    bar_frame.pack(pady=(0, 0))
    bar_frame.pack_propagate(False)

    bar_fill = tk.Frame(bar_frame, bg=ACCENT, height=3, width=0)
    bar_fill.place(x=0, y=0, height=3, width=0)

    # Breathing animation on ring (same as main GUI state ring)
    import math
    _phase = {"val": 0.0}

    def pulse():
        _phase["val"] += 0.05
        t = (math.sin(_phase["val"]) + 1) / 2
        color = lerp(ACCENT_DK, ACCENT_LT, t)
        ring_canvas.itemconfig(ring_id, outline=color)
        root.after(60, pulse)

    pulse()

    # Auto-close after 10s (safety net)
    root.after(10000, root.destroy)

    # Handle SIGTERM/SIGINT gracefully
    def on_signal(sig, frame):
        try:
            root.destroy()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    # ── Fade-out transition ──────────────────────────────────────────────
    _FADE_DURATION_MS = 300
    _FADE_STEPS = 15  # 300ms / 15 = 20ms per step

    def _fade_out(step: int = 0) -> None:
        """Fade splash to transparent over 300ms, then destroy."""
        if step > _FADE_STEPS:
            try:
                os.unlink(_PROGRESS_FILE)
            except OSError:
                pass
            root.destroy()
            return
        alpha = 1.0 - (step / _FADE_STEPS)
        try:
            root.attributes("-alpha", alpha)
        except Exception:
            root.destroy()
            return
        root.after(_FADE_DURATION_MS // _FADE_STEPS, lambda: _fade_out(step + 1))

    # Poll for progress updates and ready signal
    def check_updates():
        # Check ready signal
        if os.path.exists(_READY_FILE):
            try:
                os.unlink(_READY_FILE)
            except OSError:
                pass
            # Fade out instead of instant destroy
            _fade_out(0)
            return

        # Check progress updates
        try:
            if os.path.exists(_PROGRESS_FILE):
                with open(_PROGRESS_FILE, "r") as f:
                    data = f.read().strip()
                if "|" in data:
                    parts = data.split("|")
                    stage_text = parts[0]
                    current = int(parts[1]) if len(parts) > 1 else 0
                    total = int(parts[2]) if len(parts) > 2 else 0

                    loading.config(text=stage_text)

                    if total > 0:
                        pct = min(1.0, current / total)
                        fill_w = int(bar_width * pct)
                        bar_fill.place(x=0, y=0, height=3, width=fill_w)
        except Exception:
            pass

        root.after(80, check_updates)

    check_updates()

    try:
        root.mainloop()
    except Exception:
        pass


def signal_splash_done() -> None:
    """Signal the splash screen to close (called by main app when ready)."""
    try:
        os.makedirs(os.path.dirname(_READY_FILE), exist_ok=True)
        with open(_READY_FILE, "w") as f:
            f.write("1")
    except Exception:
        pass


def update_splash_progress(stage: str, current: int = 0, total: int = 0) -> None:
    """Update splash screen progress (called by main app during boot).

    Args:
        stage: Human-readable stage name, e.g. "Detectando wifi…"
        current: Current step number (0-based)
        total: Total number of steps
    """
    try:
        os.makedirs(os.path.dirname(_PROGRESS_FILE), exist_ok=True)
        with open(_PROGRESS_FILE, "w") as f:
            f.write(f"{stage}|{current}|{total}")
    except Exception:
        pass


def _wait_for_signal() -> None:
    """Fallback: just wait for SIGTERM."""
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    show_splash()
