"""Entry point for the CIOS.

Modes:
  1. --cli       → terminal UI
  2. --daemon    → background daemon (Unix socket)
  3. --overlay   → hotkey overlay (Ctrl+Space)
  4. --topbar    → system status bar (standalone)
  5. --setup     → re-run onboarding wizard
  6. (default)   → native Tkinter GUI + topbar
"""

import logging
import sys

from cios.core.config import LOG_DIR, ensure_dirs


def main() -> None:
    # Quick flags (no logging needed)
    if "--version" in sys.argv or "-V" in sys.argv:
        from cios import __version__

        print(f"CIOS v{__version__}")
        return

    ensure_dirs()

    logging.basicConfig(
        filename=str(LOG_DIR / "cios.log"),
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Onboarding check (first run)
    if "--setup" in sys.argv:
        from cios.ui.onboarding import run_onboarding

        run_onboarding()
        return

    # Check if first run (no --cli, --daemon, etc.)
    if not any(arg.startswith("--") for arg in sys.argv[1:]):
        from cios.ui.onboarding import needs_onboarding

        if needs_onboarding():
            from cios.ui.onboarding import run_onboarding

            if not run_onboarding():
                return

    # Daemon mode
    if "--daemon" in sys.argv or "-d" in sys.argv:
        from cios.infra.daemon import run_daemon

        try:
            run_daemon()
        except Exception as e:
            logging.exception("Fatal error in daemon mode")
            print(f"\n[FATAL] {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Hotkey overlay
    if "--overlay" in sys.argv:
        from cios.ui.hotkey import run_overlay

        run_overlay()
        return

    # Top bar
    if "--topbar" in sys.argv:
        from cios.ui.topbar import run_topbar

        try:
            run_topbar()
        except Exception as e:
            logging.exception("Fatal error in topbar mode")
            print(f"\n[FATAL] {e}", file=sys.stderr)
            sys.exit(1)
        return

    # CLI mode
    if "--cli" in sys.argv or "-c" in sys.argv:
        from cios.ui.cli import run_ui

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

        from cios.ui.gui import run_gui

        run_gui()
    except ImportError:
        logging.warning("Tkinter not available, falling back to CLI mode in xterm")
        import subprocess

        # Launch CLI in a terminal emulator (xterm is always available in X sessions)
        terminal = None
        for term in ["xterm", "x-terminal-emulator", "xfce4-terminal", "gnome-terminal"]:
            try:
                subprocess.run(["which", term], capture_output=True, check=True)
                terminal = term
                break
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue

        if terminal:
            subprocess.run([terminal, "-e", f"{sys.executable} -m cios --cli"])
        else:
            print("\n  Tkinter não encontrado e nenhum terminal disponível.")
            print("  Instale com: sudo apt install python3-tk")
            sys.exit(1)
    except Exception as e:
        logging.exception("Fatal error in GUI mode")
        print(f"\n[FATAL] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
