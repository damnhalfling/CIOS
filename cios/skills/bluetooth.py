"""Bluetooth skill — device management via bluetoothctl.

All execution is direct (no LLM). Deterministic and fast.
Handles: scan, pair, connect, disconnect, list, remove, trust.

Uses bluetoothctl (BlueZ) which is standard on Debian/Ubuntu.
"""

import re
import subprocess
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BluetoothDevice:
    address: str        # MAC address (XX:XX:XX:XX:XX:XX)
    name: str           # Human-readable name
    paired: bool = False
    connected: bool = False
    trusted: bool = False
    icon: str = ""      # device type: audio-headset, phone, computer, etc.

    @property
    def display_name(self) -> str:
        return self.name if self.name and self.name != self.address else self.address

    @property
    def type_icon(self) -> str:
        """Human-friendly device type icon."""
        icons = {
            "audio-headset": "🎧",
            "audio-headphones": "🎧",
            "audio-card": "🔊",
            "phone": "📱",
            "computer": "💻",
            "input-keyboard": "⌨️",
            "input-mouse": "🖱️",
            "input-gaming": "🎮",
        }
        return icons.get(self.icon, "📶")


def _run_btctl(*args: str, timeout: int = 10) -> tuple[bool, str, str]:
    """Run bluetoothctl command. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["bluetoothctl"] + list(args),
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", "bluetoothctl not found — BlueZ not installed"
    except subprocess.TimeoutExpired:
        return False, "", "Bluetooth operation timed out"
    except Exception as e:
        return False, "", str(e)


def is_available() -> bool:
    """Check if Bluetooth controller is available and powered on."""
    ok, stdout, _ = _run_btctl("show")
    if not ok:
        return False
    return "Powered: yes" in stdout


def is_powered() -> bool:
    """Check if Bluetooth is powered on."""
    ok, stdout, _ = _run_btctl("show")
    if not ok:
        return False
    return "Powered: yes" in stdout


def power_on() -> tuple[list[str], bool, str]:
    """Turn Bluetooth on."""
    if is_powered():
        return ["Checking Bluetooth"], True, "Bluetooth already on"
    ok, _, stderr = _run_btctl("power", "on")
    if ok:
        return ["Turning on Bluetooth"], True, "Bluetooth on"
    return ["Turning on Bluetooth"], False, _humanize_error(stderr)


def power_off() -> tuple[list[str], bool, str]:
    """Turn Bluetooth off."""
    if not is_powered():
        return ["Checking Bluetooth"], True, "Bluetooth already off"
    ok, _, stderr = _run_btctl("power", "off")
    if ok:
        return ["Turning off Bluetooth"], True, "Bluetooth off"
    return ["Turning off Bluetooth"], False, _humanize_error(stderr)


def list_devices() -> list[BluetoothDevice]:
    """List all known (paired + nearby) Bluetooth devices."""
    devices: list[BluetoothDevice] = []
    seen: set[str] = set()

    # Get paired devices
    ok, stdout, _ = _run_btctl("devices", "Paired")
    if ok:
        for dev in _parse_device_list(stdout):
            dev.paired = True
            _enrich_device(dev)
            devices.append(dev)
            seen.add(dev.address)

    # Get all known devices (includes recently scanned)
    ok, stdout, _ = _run_btctl("devices")
    if ok:
        for dev in _parse_device_list(stdout):
            if dev.address not in seen:
                _enrich_device(dev)
                devices.append(dev)
                seen.add(dev.address)

    # Sort: connected first, then paired, then by name
    devices.sort(key=lambda d: (not d.connected, not d.paired, d.display_name.lower()))
    return devices


def list_paired() -> list[BluetoothDevice]:
    """List only paired devices."""
    ok, stdout, _ = _run_btctl("devices", "Paired")
    if not ok:
        return []
    devices = _parse_device_list(stdout)
    for dev in devices:
        dev.paired = True
        _enrich_device(dev)
    devices.sort(key=lambda d: (not d.connected, d.display_name.lower()))
    return devices


def list_connected() -> list[BluetoothDevice]:
    """List currently connected devices."""
    ok, stdout, _ = _run_btctl("devices", "Connected")
    if not ok:
        return []
    devices = _parse_device_list(stdout)
    for dev in devices:
        dev.connected = True
        dev.paired = True
        _enrich_device(dev)
    return devices


def scan(duration: int = 5) -> list[BluetoothDevice]:
    """Scan for nearby Bluetooth devices.

    Starts scan, waits, then returns discovered devices.
    """
    # Ensure powered on
    if not is_powered():
        _run_btctl("power", "on")
        time.sleep(0.5)

    # Start scanning
    _run_btctl("scan", "on")
    time.sleep(duration)
    _run_btctl("scan", "off")

    # Return all devices (includes newly discovered)
    return list_devices()


def connect(address_or_name: str) -> tuple[list[str], bool, str]:
    """Connect to a Bluetooth device by address or name.

    Returns: (plan_steps, success, message)
    """
    device = _resolve_device(address_or_name)
    if not device:
        return (
            [f"Searching for {address_or_name}"],
            False,
            f"Device not found: {address_or_name}",
        )

    plan_steps = [f"Connecting to {device.display_name}"]

    # If not paired, pair first
    if not device.paired:
        plan_steps.append(f"Pairing with {device.display_name}")
        ok, _, stderr = _run_btctl("pair", device.address, timeout=15)
        if not ok:
            return plan_steps, False, _humanize_error(stderr)
        # Trust the device (auto-connect in future)
        _run_btctl("trust", device.address)

    # Connect
    ok, stdout, stderr = _run_btctl("connect", device.address, timeout=15)
    if ok or "successful" in stdout.lower():
        plan_steps.append(f"Connected to {device.display_name}")
        return plan_steps, True, f"Connected to {device.display_name}"

    return plan_steps, False, _humanize_error(stderr)


def disconnect(address_or_name: str = "") -> tuple[list[str], bool, str]:
    """Disconnect from a Bluetooth device.

    If no device specified, disconnects all connected devices.
    """
    if not address_or_name:
        # Disconnect all
        connected = list_connected()
        if not connected:
            return ["Checking Bluetooth"], True, "No devices connected"
        results = []
        for dev in connected:
            ok, _, _ = _run_btctl("disconnect", dev.address)
            results.append((dev.display_name, ok))
        all_ok = all(ok for _, ok in results)
        names = ", ".join(name for name, _ in results)
        if all_ok:
            return ["Disconnecting all"], True, f"Disconnected from {names}"
        return ["Disconnecting all"], False, "Some devices failed to disconnect"

    device = _resolve_device(address_or_name)
    if not device:
        return [f"Searching for {address_or_name}"], False, f"Device not found: {address_or_name}"

    ok, _, stderr = _run_btctl("disconnect", device.address)
    if ok:
        return (
            [f"Disconnecting from {device.display_name}"],
            True,
            f"Disconnected from {device.display_name}",
        )
    return [f"Disconnecting from {device.display_name}"], False, _humanize_error(stderr)


def remove(address_or_name: str) -> tuple[list[str], bool, str]:
    """Remove (unpair) a Bluetooth device."""
    device = _resolve_device(address_or_name)
    if not device:
        return [f"Searching for {address_or_name}"], False, f"Device not found: {address_or_name}"

    ok, _, stderr = _run_btctl("remove", device.address)
    if ok:
        return (
            [f"Removing {device.display_name}"],
            True,
            f"Removed {device.display_name}",
        )
    return [f"Removing {device.display_name}"], False, _humanize_error(stderr)


def trust(address_or_name: str) -> tuple[list[str], bool, str]:
    """Trust a device (auto-connect in future)."""
    device = _resolve_device(address_or_name)
    if not device:
        return [f"Searching for {address_or_name}"], False, f"Device not found: {address_or_name}"

    ok, _, stderr = _run_btctl("trust", device.address)
    if ok:
        return (
            [f"Trusting {device.display_name}"],
            True,
            f"Trusted {device.display_name}",
        )
    return [f"Trusting {device.display_name}"], False, _humanize_error(stderr)


# ═══════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _parse_device_list(output: str) -> list[BluetoothDevice]:
    """Parse bluetoothctl device list output.

    Format: "Device XX:XX:XX:XX:XX:XX Device Name"
    """
    devices = []
    for line in output.splitlines():
        match = re.match(
            r"(?:Device\s+)?([0-9A-Fa-f:]{17})\s+(.+)",
            line.strip(),
        )
        if match:
            devices.append(BluetoothDevice(
                address=match.group(1),
                name=match.group(2).strip(),
            ))
    return devices


def _enrich_device(device: BluetoothDevice) -> None:
    """Enrich device with info from bluetoothctl info."""
    ok, stdout, _ = _run_btctl("info", device.address)
    if not ok:
        return

    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Connected:"):
            device.connected = "yes" in line.lower()
        elif line.startswith("Paired:"):
            device.paired = "yes" in line.lower()
        elif line.startswith("Trusted:"):
            device.trusted = "yes" in line.lower()
        elif line.startswith("Icon:"):
            device.icon = line.split(":", 1)[1].strip()
        elif line.startswith("Name:"):
            name = line.split(":", 1)[1].strip()
            if name and name != device.address:
                device.name = name


def _resolve_device(query: str) -> Optional[BluetoothDevice]:
    """Find a device by address or name (fuzzy match)."""
    query_lower = query.lower().strip()

    # MAC address match
    if re.match(r"^[0-9a-f:]{17}$", query_lower):
        devices = list_devices()
        for dev in devices:
            if dev.address.lower() == query_lower:
                return dev
        return None

    # Name match — search paired first, then all
    devices = list_devices()

    # Exact match
    for dev in devices:
        if dev.display_name.lower() == query_lower:
            return dev

    # Contains match
    for dev in devices:
        if query_lower in dev.display_name.lower():
            return dev

    # Partial match (any word)
    for dev in devices:
        if any(query_lower in word.lower() for word in dev.display_name.split()):
            return dev

    return None


def _humanize_error(stderr: str) -> str:
    """Convert bluetoothctl errors to human language."""
    s = stderr.lower()
    if "not available" in s or "no default controller" in s:
        return "Bluetooth not available on this device"
    if "not found" in s and "bluetoothctl" in s:
        return "Bluetooth not installed"
    if "not found" in s or "does not exist" in s:
        return "Device not found"
    if "failed" in s and "pair" in s:
        return "Pairing failed — make sure the device is in pairing mode"
    if "failed" in s and "connect" in s:
        return "Connection failed — device may be out of range"
    if "rejected" in s:
        return "Connection rejected by device"
    if "timeout" in s:
        return "Bluetooth operation timed out"
    if "already" in s and "connected" in s:
        return "Already connected"
    if "not powered" in s or "powered: no" in s:
        return "Bluetooth is turned off"
    if "bluetoothctl not found" in s:
        return "Bluetooth not installed"
    return stderr[:100] if stderr else "Bluetooth operation failed"
