"""Command Poller — fetches and executes remote commands from Maestro.

Polls GET /v1/commands/pending periodically and executes commands
received from other clients (Puccini, Intelligence Web).

This enables cross-device continuity:
- Puccini sends "update spreadsheet X" → Maestro queues it
- OS polls → receives command → executes via bridge → reports result

Lifecycle:
- Started by daemon or GUI on boot (if Intelligence is logged in)
- Runs as a daemon thread (dies with parent)
- Polls every 5 seconds (configurable)
- Graceful shutdown via stop()
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from cios.core.config import CIOS_HOME

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5  # seconds
_TIMEOUT = 10  # HTTP timeout
_AUTH_FILE = CIOS_HOME / "intelligence.json"


@dataclass
class RemoteCommand:
    """A command received from Maestro."""

    id: int
    command: str
    context: dict | None = None


class CommandPoller:
    """Polls Maestro for pending commands and executes them."""

    def __init__(self, bridge=None) -> None:
        """Initialize poller.

        Args:
            bridge: CIOSBridge instance for executing commands.
                    If None, commands are logged but not executed.
        """
        self._bridge = bridge
        self._running = False
        self._thread: threading.Thread | None = None
        self._api_base = ""
        self._token = ""
        self._poll_interval = _POLL_INTERVAL

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the polling thread."""
        if self._running:
            return

        if not self._load_auth():
            logger.info("CommandPoller: no auth, not starting")
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="command-poller")
        self._thread.start()
        logger.info("CommandPoller started (interval=%ds)", self._poll_interval)

    def stop(self) -> None:
        """Stop the polling thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._poll_interval + 2)
        self._thread = None
        logger.info("CommandPoller stopped")

    def _load_auth(self) -> bool:
        """Load API credentials from intelligence auth file."""
        if not _AUTH_FILE.exists():
            return False

        try:
            data = json.loads(_AUTH_FILE.read_text())
            self._token = data.get("token", "")
            # API base from intelligence module
            self._api_base = "https://api.cios-ai.com"
            return bool(self._token)
        except Exception as e:
            logger.warning("CommandPoller: failed to load auth: %s", e)
            return False

    def _poll_loop(self) -> None:
        """Main polling loop."""
        # Initial delay to let system boot
        time.sleep(3)

        while self._running:
            try:
                commands = self._fetch_pending()
                for cmd in commands:
                    self._execute_command(cmd)
            except Exception as e:
                logger.debug("CommandPoller poll error: %s", e)

            # Sleep in small increments for responsive shutdown
            for _ in range(self._poll_interval * 2):
                if not self._running:
                    return
                time.sleep(0.5)

    def _fetch_pending(self) -> list[RemoteCommand]:
        """Fetch pending commands from Maestro."""
        if not self._token:
            if not self._load_auth():
                return []

        url = f"{self._api_base}/v1/commands/pending?target_client=os"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read())
                commands = data.get("commands", [])
                result = []
                for cmd_data in commands:
                    result.append(
                        RemoteCommand(
                            id=cmd_data["id"],
                            command=cmd_data["command"],
                            context=cmd_data.get("context"),
                        )
                    )
                if result:
                    logger.info("CommandPoller: %d pending commands", len(result))
                return result
        except urllib.error.HTTPError as e:
            if e.code == 401:
                logger.warning("CommandPoller: token expired, reloading auth")
                self._token = ""
            else:
                logger.debug("CommandPoller: HTTP %d", e.code)
            return []
        except urllib.error.URLError:
            # Offline — silent
            return []
        except Exception as e:
            logger.debug("CommandPoller: fetch error: %s", e)
            return []

    def _execute_command(self, cmd: RemoteCommand) -> None:
        """Execute a remote command and report result."""
        logger.info("CommandPoller: executing command #%d: '%s'", cmd.id, cmd.command[:80])

        # Mark as delivered
        self._update_status(cmd.id, "delivered")

        result_text = ""
        success = False

        try:
            if self._bridge:
                # Execute via bridge (same as local commands)
                result = self._bridge.execute_command(cmd.command, confirmed=True)
                result_text = result.get("result", result.get("summary", ""))
                success = result.get("status") != "error"
            else:
                result_text = "Bridge not available"
                success = False
        except Exception as e:
            logger.warning("CommandPoller: execution failed for #%d: %s", cmd.id, e)
            result_text = f"Execution failed: {e}"
            success = False

        # Report result
        status = "executed" if success else "failed"
        self._update_status(cmd.id, status, result_text)
        logger.info(
            "CommandPoller: command #%d %s: %s",
            cmd.id,
            status,
            result_text[:100],
        )

    def _update_status(self, command_id: int, status: str, result: str | None = None) -> None:
        """Update command status on Maestro."""
        url = f"{self._api_base}/v1/commands/{command_id}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        body: dict = {"status": status}
        if result:
            body["result"] = result[:2000]  # Truncate to avoid payload issues

        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers=headers, method="PATCH")

        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT):
                pass  # 200 OK is enough
        except Exception as e:
            logger.debug("CommandPoller: failed to update status for #%d: %s", command_id, e)
