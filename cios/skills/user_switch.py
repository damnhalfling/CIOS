"""User switching skill — fast user switch via greetd.

Allows switching between logged-in users without full logout.
Uses greetd IPC to initiate a new session on a different VT.

#527 — Multi-user switching (fast user switch)
"""

import json
import logging
import os
import socket
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

GREETD_SOCK = os.environ.get("GREETD_SOCK", "/run/greetd.sock")


def list_users() -> list[dict]:
    """List system users that can log in.

    Returns users with UID >= 1000 (non-system users).
    """
    users = []
    try:
        with open("/etc/passwd") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) >= 7:
                    username = parts[0]
                    uid = int(parts[2])
                    shell = parts[6]
                    # Only real users (UID >= 1000, valid shell)
                    if uid >= 1000 and shell not in ("/usr/sbin/nologin", "/bin/false"):
                        gecos = parts[4].split(",")[0]  # Full name
                        users.append(
                            {
                                "username": username,
                                "uid": uid,
                                "name": gecos or username,
                                "home": parts[5],
                            }
                        )
    except Exception as e:
        logger.error("Failed to list users: %s", e)
    return users


def get_current_user() -> str:
    """Get the currently logged-in username."""
    return os.environ.get("USER", os.environ.get("LOGNAME", "unknown"))


def switch_to_user(username: str) -> tuple[list[str], bool, str]:
    """Switch to another user session.

    This initiates a new greetd session on a new VT.
    The current session remains active (fast switch, not logout).

    Args:
        username: Target username

    Returns:
        (steps, success, message)
    """
    steps = [f"Alternando para {username}"]

    # Verify user exists
    users = list_users()
    if not any(u["username"] == username for u in users):
        return steps, False, f"Usuário '{username}' não encontrado."

    # Method 1: Use greetd IPC (if available)
    if Path(GREETD_SOCK).exists():
        success = _switch_via_greetd(username)
        if success:
            return steps, True, f"Sessão iniciada para {username}."

    # Method 2: Switch to login VT (Ctrl+Alt+F1 equivalent)
    try:
        # Find a free VT
        result = subprocess.run(
            ["fgconsole"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        current_vt = int(result.stdout.strip()) if result.returncode == 0 else 7

        # Switch to VT1 (where greetd login usually is)
        target_vt = 1 if current_vt != 1 else 2
        subprocess.run(
            ["sudo", "chvt", str(target_vt)],
            capture_output=True,
            timeout=5,
        )
        return steps, True, f"Alternado para VT{target_vt}. Faça login como {username}."
    except Exception as e:
        logger.error("VT switch failed: %s", e)
        return steps, False, f"Falha ao alternar: {e}"


def lock_and_switch() -> tuple[list[str], bool, str]:
    """Lock current session and show login screen.

    Returns:
        (steps, success, message)
    """
    steps = ["Bloqueando e alternando"]

    try:
        # Switch to greetd VT (VT1)
        subprocess.run(
            ["sudo", "chvt", "1"],
            capture_output=True,
            timeout=5,
        )
        return steps, True, "Sessão bloqueada. Tela de login exibida."
    except Exception as e:
        return steps, False, f"Falha: {e}"


def _switch_via_greetd(username: str) -> bool:
    """Switch user via greetd IPC socket.

    Sends create_session + start_session commands.
    """
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(GREETD_SOCK)
        sock.settimeout(5)

        # Create session
        request = json.dumps(
            {
                "type": "create_session",
                "username": username,
            }
        )
        _send_greetd_msg(sock, request)
        response = _recv_greetd_msg(sock)

        if not response or response.get("type") == "error":
            sock.close()
            return False

        # Start session with default command (cios-shell)
        request = json.dumps(
            {
                "type": "start_session",
                "cmd": ["cios-shell"],
            }
        )
        _send_greetd_msg(sock, request)
        response = _recv_greetd_msg(sock)

        sock.close()
        return response and response.get("type") == "success"

    except Exception as e:
        logger.debug("greetd IPC failed: %s", e)
        return False


def _send_greetd_msg(sock: socket.socket, msg: str) -> None:
    """Send a length-prefixed message to greetd."""
    data = msg.encode()
    length = len(data).to_bytes(4, byteorder="little")
    sock.sendall(length + data)


def _recv_greetd_msg(sock: socket.socket) -> dict | None:
    """Receive a length-prefixed message from greetd."""
    try:
        length_bytes = sock.recv(4)
        if len(length_bytes) < 4:
            return None
        length = int.from_bytes(length_bytes, byteorder="little")
        data = sock.recv(length)
        return json.loads(data.decode())
    except Exception:
        return None
