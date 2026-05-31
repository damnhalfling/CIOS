"""CIOS GTK4 IPC Listener — Receives events from the compositor.

Maintains a persistent connection to the compositor's Unix socket
and dispatches events (key_intercepted, logout_requested, etc.)
to the GTK4 application via GLib.idle_add.

Also provides send_command() for skills that need to communicate
with the compositor (e.g. monitor configuration).
"""

import json
import logging
import os
import socket
import threading
import time as _time

from gi.repository import GLib

logger = logging.getLogger(__name__)


class IPCListener:
    """Persistent IPC connection to cios-shell compositor."""

    _instance = None

    def __init__(self, on_hotkey=None, on_logout=None, on_search=None):
        self._on_hotkey = on_hotkey
        self._on_logout = on_logout
        self._on_search = on_search
        self._socket = None
        self._running = False
        self._thread = None
        # Command support: pending responses keyed by message ID
        self._pending_responses: dict[str, threading.Event] = {}
        self._response_data: dict[str, dict] = {}
        self._send_lock = threading.Lock()
        IPCListener._instance = self

    @classmethod
    def get_instance(cls):
        """Get the singleton IPCListener instance."""
        return cls._instance

    def send_command(self, command: dict, timeout: float = 3.0) -> dict | None:
        """Send a command to the compositor and wait for response.

        Thread-safe. The listener thread will capture the response by ID.
        """
        if not self._socket:
            return None

        msg_id = f"cmd_{id(command)}_{_time.monotonic_ns()}"
        cmd_name = command.pop("cmd", "unknown")
        payload = {"v": 1, "id": msg_id, "command": cmd_name, **command}

        # Register pending response
        event = threading.Event()
        self._pending_responses[msg_id] = event

        try:
            with self._send_lock:
                msg = json.dumps(payload) + "\n"
                self._socket.sendall(msg.encode())

            # Wait for the listener thread to capture the response
            if event.wait(timeout=timeout):
                return self._response_data.pop(msg_id, None)
            else:
                logger.debug("IPC send_command timeout for %s", cmd_name)
                return None
        except OSError as e:
            logger.debug("IPC send_command failed: %s", e)
            return None
        finally:
            self._pending_responses.pop(msg_id, None)

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
                _time.sleep(2)

    def _handle_message(self, raw: str):
        """Parse and dispatch a JSON message from the compositor."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Check if this is a response to a pending command
        msg_id = msg.get("id", "")
        if msg_id in self._pending_responses:
            self._response_data[msg_id] = msg
            self._pending_responses[msg_id].set()
            return

        event = msg.get("event")
        if not event:
            return  # Response to unknown command, ignore

        if event == "key_intercepted":
            key = msg.get("key", "")
            if "ctrl+space" in key and self._on_hotkey:
                GLib.idle_add(self._on_hotkey)
            elif "ctrl+k" in key and self._on_search:
                GLib.idle_add(self._on_search)

        elif event == "logout_requested":
            if self._on_logout:
                GLib.idle_add(self._on_logout)
