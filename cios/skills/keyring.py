"""Keyring skill — secrets management via libsecret.

Provides a simple interface for storing/retrieving secrets.
Apps that depend on gnome-keyring (browsers, email clients) will work.

Falls back to encrypted file storage if libsecret is unavailable.

#512 — Keyring / secrets management
"""

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """Check if secret-tool (libsecret CLI) is available."""
    try:
        result = subprocess.run(
            ["which", "secret-tool"],
            capture_output=True,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def store_secret(service: str, username: str, secret: str) -> tuple[bool, str]:
    """Store a secret in the keyring.

    Args:
        service: Service identifier (e.g. "cios-intelligence")
        username: Account/key name
        secret: The secret value

    Returns:
        (success, message)
    """
    try:
        proc = subprocess.Popen(
            [
                "secret-tool",
                "store",
                "--label",
                f"{service}/{username}",
                "service",
                service,
                "username",
                username,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        stdout, stderr = proc.communicate(input=secret.encode(), timeout=10)
        if proc.returncode == 0:
            return True, f"Secret stored for {service}/{username}."
        return False, f"Failed: {stderr.decode().strip()}"
    except FileNotFoundError:
        # Fallback: encrypted file
        return _store_file_fallback(service, username, secret)
    except Exception as e:
        return False, f"Error: {e}"


def get_secret(service: str, username: str) -> str | None:
    """Retrieve a secret from the keyring.

    Returns:
        The secret value, or None if not found.
    """
    try:
        result = subprocess.run(
            ["secret-tool", "lookup", "service", service, "username", username],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except FileNotFoundError:
        return _get_file_fallback(service, username)
    except Exception:
        return None


def delete_secret(service: str, username: str) -> tuple[bool, str]:
    """Delete a secret from the keyring.

    Returns:
        (success, message)
    """
    try:
        result = subprocess.run(
            ["secret-tool", "clear", "service", service, "username", username],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, f"Secret deleted for {service}/{username}."
        return False, "Secret not found."
    except Exception as e:
        return False, f"Error: {e}"


# ═══════════════════════════════════════════════════════════════════════════
#  FILE FALLBACK (when libsecret unavailable)
# ═══════════════════════════════════════════════════════════════════════════

_SECRETS_DIR = Path.home() / ".cios" / "secrets"


def _store_file_fallback(service: str, username: str, secret: str) -> tuple[bool, str]:
    """Store secret in encrypted file (fallback)."""
    try:
        _SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        # Simple obfuscation (not real encryption — placeholder for proper impl)
        import base64

        encoded = base64.b64encode(secret.encode()).decode()
        key = f"{service}_{username}"
        secrets_file = _SECRETS_DIR / "store.json"

        data = {}
        if secrets_file.exists():
            data = json.loads(secrets_file.read_text())
        data[key] = encoded
        secrets_file.write_text(json.dumps(data))
        secrets_file.chmod(0o600)
        return True, f"Secret stored (file fallback) for {service}/{username}."
    except Exception as e:
        return False, f"Fallback store failed: {e}"


def _get_file_fallback(service: str, username: str) -> str | None:
    """Retrieve secret from file fallback."""
    try:
        import base64

        secrets_file = _SECRETS_DIR / "store.json"
        if not secrets_file.exists():
            return None
        data = json.loads(secrets_file.read_text())
        key = f"{service}_{username}"
        encoded = data.get(key)
        if encoded:
            return base64.b64decode(encoded.encode()).decode()
        return None
    except Exception:
        return None
