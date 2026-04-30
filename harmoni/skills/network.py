"""Network skill — Wi-Fi management via nmcli.

All execution is direct (no LLM). Deterministic and fast.
Consults MCP for context-aware decisions.
"""

import re
import subprocess
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WifiNetwork:
    ssid: str
    signal: int       # 0-100
    security: str     # "WPA2", "WPA3", "Open", etc.
    active: bool = False


def _run_nmcli(*args: str, timeout: int = 10) -> tuple[bool, str, str]:
    """Run nmcli command. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["nmcli"] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", "nmcli not found — NetworkManager not installed"
    except subprocess.TimeoutExpired:
        return False, "", "Network operation timed out"
    except Exception as e:
        return False, "", str(e)


def is_available() -> bool:
    """Check if NetworkManager/nmcli is available."""
    ok, _, _ = _run_nmcli("general", "status")
    return ok


def list_networks() -> list[WifiNetwork]:
    """List available Wi-Fi networks."""
    ok, stdout, _ = _run_nmcli(
        "-t", "-f", "ACTIVE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
        "--rescan", "auto",
    )
    if not ok:
        return []

    networks = []
    seen: set[str] = set()
    for line in stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 4:
            ssid = parts[1].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            networks.append(WifiNetwork(
                ssid=ssid,
                signal=int(parts[2]) if parts[2].isdigit() else 0,
                security=parts[3] if parts[3] else "Open",
                active=parts[0].lower() in ("yes", "sim"),
            ))

    # Sort by signal strength (strongest first)
    networks.sort(key=lambda n: (-n.active, -n.signal))
    return networks


def get_current_connection() -> Optional[dict]:
    """Get current Wi-Fi connection info."""
    ok, stdout, _ = _run_nmcli(
        "-t", "-f", "NAME,TYPE,DEVICE", "con", "show", "--active",
    )
    if not ok:
        return None

    for line in stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and "wireless" in parts[1].lower():
            device = parts[2]
            # Get IP
            ip_ok, ip_out, _ = _run_nmcli(
                "-t", "-f", "IP4.ADDRESS", "dev", "show", device,
            )
            ip = ""
            if ip_ok:
                for ip_line in ip_out.splitlines():
                    if ":" in ip_line:
                        addr = ip_line.split(":", 1)[1].strip()
                        ip = addr.split("/")[0] if "/" in addr else addr
                        break
            return {"ssid": parts[0], "device": device, "ip": ip}
    return None


def connect(ssid: str, password: str = "") -> tuple[list[str], bool, str]:
    """Connect to a Wi-Fi network.

    Returns: (plan_steps, success, message)
    """
    plan_steps = [f"Connecting to {ssid}"]

    if password:
        ok, stdout, stderr = _run_nmcli(
            "dev", "wifi", "connect", ssid, "password", password,
            timeout=30,
        )
    else:
        # Try connecting without password (saved or open network)
        ok, stdout, stderr = _run_nmcli(
            "dev", "wifi", "connect", ssid,
            timeout=30,
        )

    if ok:
        plan_steps.append(f"Connected to {ssid}")
        return plan_steps, True, f"Connected to {ssid}"

    # Parse error
    msg = _humanize_nmcli_error(stderr)
    plan_steps.append(f"Failed: {msg}")
    return plan_steps, False, msg


def disconnect() -> tuple[list[str], bool, str]:
    """Disconnect from current Wi-Fi."""
    conn = get_current_connection()
    if not conn:
        return ["Check Wi-Fi"], True, "Not connected to any network"

    ok, _, stderr = _run_nmcli("dev", "disconnect", conn["device"])
    if ok:
        return [f"Disconnecting from {conn['ssid']}"], True, f"Disconnected from {conn['ssid']}"
    return ["Disconnecting"], False, _humanize_nmcli_error(stderr)


def get_known_networks() -> list[str]:
    """Get list of saved/known Wi-Fi networks."""
    ok, stdout, _ = _run_nmcli("-t", "-f", "NAME,TYPE", "con", "show")
    if not ok:
        return []
    networks = []
    for line in stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and "wireless" in parts[1].lower():
            networks.append(parts[0])
    return networks


def _humanize_nmcli_error(stderr: str) -> str:
    """Convert nmcli errors to human language."""
    s = stderr.lower()
    if "no network with ssid" in s or "not found" in s:
        return "Network not found"
    if "secrets were required" in s or "password" in s or "psk" in s:
        return "Wrong password"
    if "no wifi device" in s or "wifi is disabled" in s:
        return "Wi-Fi is disabled or not available"
    if "already active" in s:
        return "Already connected"
    if "timeout" in s:
        return "Connection timed out"
    if "nmcli not found" in s:
        return "NetworkManager not installed"
    return stderr[:100] if stderr else "Connection failed"
