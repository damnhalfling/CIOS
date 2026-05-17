"""CIOS GTK4 IPC Listener — Receives events from the compositor.

Maintains a persistent connection to the compositor's Unix socket
and dispatches events (key_intercepted, logout_requested, etc.)
to the GTK4 application via GLib.idle_add.
"""

import json
import logging
import os
import socket
import threading

from gi.repository import GLib

logger = logging.getLogger(__name__)


class IPCListener:
    """Persistent IPC connection to cios-shell compositor."""

    def __init__(self, on_hotkey=None, on_logout=None):
        self._on_hotkey = on_hotkey
        self._on_logout = on_logout
        self._socket = None
        self._running = False
        self._thread = None

    def start(self):
        """Start listening for compositor events in background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the listener."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass

    def _listen_loop(self):
        """Main loop: connect to socket and read events."""
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        sock_path = os.path.join(runtime_dir, "cios-shell.sock")

        while self._running:
            try:
                self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._socket.connect(sock_path)
                self._socket.settimeout(1.0)
                logger.info("IPC listener connected to compositor")

                # Send ready to register as persistent client
                msg = json.dumps({"v": 1, "id": "ipc-listen", "command": "ready"}) + "\n"
                self._socket.sendall(msg.encode())

                # Read events
                buffer = ""
                while self._running:
                    try:
                        data = self._socket.recv(4096)
                        if not data:
                            break  # Connection closed
                        buffer += data.decode()

                        # Process complete messages (newline-delimited)
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if line.strip():
                                self._handle_message(line.strip())
                    except TimeoutError:
                        continue
                    except OSError:
                        break

            except (ConnectionRefusedError, FileNotFoundError):
                pass
            except Exception as e:
                logger.debug("IPC listener error: %s", e)

            # Reconnect after 2s
            if self._running:
                import time

                time.sleep(2)

    def _handle_message(self, raw: str):
        """Parse and dispatch a JSON message from the compositor."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        event = msg.get("event")
        if not event:
            return  # Response, not event

        if event == "key_intercepted":
            key = msg.get("key", "")
            if "ctrl+space" in key and self._on_hotkey:
                GLib.idle_add(self._on_hotkey)

        elif event == "logout_requested":
            if self._on_logout:
                GLib.idle_add(self._on_logout)
