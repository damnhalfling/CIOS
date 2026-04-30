"""Entry point for the Harmoni OS.

Modes:
  1. --cli       → terminal UI
  2. --daemon    → background daemon (Unix socket)
  3. --overlay   → hotkey overlay (Ctrl+Space)
  4. --topbar    → system status bar (standalone)
  5. --setup     → re-run onboarding wizard
  6. (default)   → native Tkinter GUI + topbar
"""

import sys
import logging
from harmoni.core.config import LOG_DIR, ensure_dirs


def main() -> None:
    # Quick flags (no logging needed)
    if "--version" in sys.argv or "-V" in sys.argv:
        from harmoni import __version__
        print(f"Harmoni OS v{__version__}")
        return

    ensure_dirs()

    logging.basicConfig(
        filename=str(LOG_DIR / "harmoni.log"),
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Onboarding check (first run)
    if "--setup" in sys.argv:
        from harmoni.ui.onboarding import run_onboarding
        run_onboarding()
        return

    # Check if first run (no --cli, --daemon, etc.)
    if not any(arg.startswith("--") for arg in sys.argv[1:]):
        from harmoni.ui.onboarding import needs_onboarding
        if needs_onboarding():
            from harmoni.ui.onboarding import run_onboarding
            if not run_onboarding():
                return

    # Daemon mode
    if "--daemon" in sys.argv or "-d" in sys.argv:
        from harmoni.infra.daemon import run_daemon
        try:
            run_daemon()
        except Exception as e:
            logging.exception("Fatal error in daemon mode")
            print(f"\n[FATAL] {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Hotkey overlay
    if "--overlay" in sys.argv:
        from harmoni.ui.hotkey import run_overlay
        run_overlay()
        return

    # Top bar
    if "--topbar" in sys.argv:
        from harmoni.ui.topbar import run_topbar
        try:
            run_topbar()
        except Exception as e:
            logging.exception("Fatal error in topbar mode")
            print(f"\n[FATAL] {e}", file=sys.stderr)
            sys.exit(1)
        return

    # CLI mode
    if "--cli" in sys.argv or "-c" in sys.argv:
        from harmoni.ui.cli import run_ui
        try:
            run_ui()
        except Exception as e:
            logging.exception("Fatal error in CLI mode")
            print(f"\n[FATAL] {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Native Tkinter GUI (default)
    try:
        import tkinter  # noqa: F401 — test availability
        from harmoni.ui.gui import run_gui
        run_gui()
    except ImportError:
        print("\n  Tkinter não encontrado.")
        print("  Instale com: sudo apt install python3-tk")
        print("\n  Alternativas:")
        print("    harmoni --cli    → Modo terminal")
        print("    harmoni --daemon → Modo daemon (socket Unix)\n")
        sys.exit(1)
    except Exception as e:
        logging.exception("Fatal error in GUI mode")
        print(f"\n[FATAL] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
