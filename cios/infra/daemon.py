"""Daemon mode — Unix socket server for CIOS.

Runs CIOS as a background daemon, accepting commands via a Unix socket.
This allows other processes (hotkey, top bar, CLI) to communicate with
the running CIOS instance without starting a new process each time.

Usage:
    # Start daemon
    cios --daemon

    # Send command via socket
    echo '{"command": "status"}' | socat - UNIX-CONNECT:/tmp/cios.sock

Protocol:
    Request:  {"command": "...", "confirmed": false}
    Response: {"steps": [...], "result": "...", "status": "...", "confirm": "..."}

    Special commands:
    - "ping"     → {"status": "ok", "uptime": 123.4}
    - "shutdown" → graceful shutdown
    - "status"   → system status from MCP
    - "learned"  → list learned shortcuts
"""

import json
import logging
import os
import signal
import socket
import sys
import threading
import time

from cios.core.bridge import CIOSBridge
from cios.core.config import CIOS_HOME, ensure_dirs

logger = logging.getLogger(__name__)

SOCKET_PATH = "/tmp/cios.sock"
PID_FILE = CIOS_HOME / "daemon.pid"
_MAX_MSG_SIZE = 65536


class CIOSDaemon:
    """Unix socket daemon for CIOS."""

    def __init__(self) -> None:
        self._bridge: CIOSBridge | None = None
        self._server: socket.socket | None = None
        self._running = False
        self._start_time = 0.0
        self._clients: list[threading.Thread] = []
        self._command_poller = None

    def start(self) -> None:
        """Start the daemon. Blocks until shutdown."""
        ensure_dirs()
        self._start_time = time.time()

        # Check if another daemon is running
        if self._is_running():
            print(f"CIOS daemon already running (PID file: {PID_FILE})")
            sys.exit(1)

        # Clean up stale socket
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)

        # Initialize bridge
        self._bridge = CIOSBridge()

        # Start command poller (cross-device commands from Puccini/Web)
        try:
            from cios.core.command_poller import CommandPoller

            self._command_poller = CommandPoller(bridge=self._bridge)
            self._command_poller.start()
        except Exception as e:
            logger.warning("Failed to start command poller: %s", e)

        # Create Unix socket
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(SOCKET_PATH)
        self._server.listen(5)
        self._server.settimeout(1.0)  # allow periodic shutdown checks
        os.chmod(SOCKET_PATH, 0o600)  # only owner can connect

        # Write PID file
        PID_FILE.write_text(str(os.getpid()))

        # Signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self._running = True
        logger.info("CIOS daemon started on %s (PID %d)", SOCKET_PATH, os.getpid())
        print(f"CIOS daemon running on {SOCKET_PATH}")

        try:
            self._accept_loop()
        finally:
            self._cleanup()

    def _accept_loop(self) -> None:
        """Accept incoming connections."""
        while self._running:
            try:
                client, _ = self._server.accept()
                t = threading.Thread(target=self._handle_client, args=(client,), daemon=True)
                t.start()
                self._clients.append(t)
            except TimeoutError:
                continue
            except OSError:
                if self._running:
                    logger.error("Socket accept error")
                break

    def _handle_client(self, client: socket.socket) -> None:
        """Handle a single client connection."""
        try:
            client.settimeout(30.0)
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > _MAX_MSG_SIZE:
                    self._send_error(client, "Message too large")
                    return
                # Try to parse — if valid JSON, process it
                try:
                    request = json.loads(data.decode("utf-8"))
                    break
                except json.JSONDecodeError:
                    continue  # keep reading

            if not data:
                return

            try:
                request = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_error(client, "Invalid JSON")
                return

            response = self._process_request(request)
            client.sendall(json.dumps(response).encode("utf-8"))
        except TimeoutError:
            self._send_error(client, "Timeout")
        except Exception as e:
            logger.error("Client handler error: %s", e)
        finally:
            client.close()

    def _process_request(self, request: dict) -> dict:
        """Process a daemon request."""
        command = request.get("command", "").strip()
        confirmed = request.get("confirmed", False)

        # Special commands
        if command == "ping":
            return {
                "status": "ok",
                "uptime": round(time.time() - self._start_time, 1),
                "pid": os.getpid(),
            }

        if command == "shutdown":
            self._running = False
            return {"status": "ok", "result": "Daemon shutting down"}

        if command == "mcp_status":
            return self._bridge.get_system_status()

        if command == "activity":
            return {"activity": self._bridge.get_recent_activity()}

        if not command:
            return {"status": "error", "result": "No command provided"}

        # Regular command execution
        return self._bridge.execute_command(command, confirmed=confirmed)

    def _send_error(self, client: socket.socket, msg: str) -> None:
        """Send an error response."""
        try:
            client.sendall(json.dumps({"status": "error", "result": msg}).encode("utf-8"))
        except Exception:
            pass

    def _handle_signal(self, signum, frame) -> None:
        """Handle shutdown signals."""
        logger.info("Received signal %d, shutting down", signum)
        self._running = False

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._command_poller:
            self._command_poller.stop()
        if self._bridge:
            self._bridge.close()
        if self._server:
            self._server.close()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        if PID_FILE.exists():
            PID_FILE.unlink()
        logger.info("Daemon stopped")

    def _is_running(self) -> bool:
        """Check if another daemon instance is running."""
        if not PID_FILE.exists():
            return False
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)  # check if process exists
            return True
        except (ValueError, ProcessLookupError, PermissionError):
            # Stale PID file
            PID_FILE.unlink(missing_ok=True)
            return False


def send_command(command: str, confirmed: bool = False, timeout: float = 30.0) -> dict | None:
    """Send a command to the running daemon. Returns response or None."""
    if not os.path.exists(SOCKET_PATH):
        return None

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(SOCKET_PATH)

        request = json.dumps({"command": command, "confirmed": confirmed})
        sock.sendall(request.encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)  # signal end of request

        # Read response
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk

        sock.close()
        return json.loads(data.decode("utf-8")) if data else None
    except Exception as e:
        logger.debug("Daemon communication failed: %s", e)
        return None


def is_daemon_running() -> bool:
    """Check if the daemon is running and responsive."""
    result = send_command("ping", timeout=2.0)
    return result is not None and result.get("status") == "ok"


def run_daemon() -> None:
    """Entry point for daemon mode."""
    daemon = CIOSDaemon()
    daemon.start()
