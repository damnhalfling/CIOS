"""VPN skill — connect/disconnect VPN via intent.

Supports WireGuard (wg-quick) and OpenVPN (nmcli) connections.
Detects available VPN configs and manages connections.

#510 — VPN via intent ("conecta VPN", "disconnect VPN")
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VPNConnection:
    """A VPN connection."""
    name: str
    type: str  # "wireguard" | "openvpn" | "nmcli"
    active: bool
    interface: str = ""


def list_vpns() -> list[VPNConnection]:
    """List available VPN connections.

    Checks:
    1. nmcli VPN connections (OpenVPN, WireGuard via NetworkManager)
    2. WireGuard configs in /etc/wireguard/
    """
    vpns = []

    # 1. nmcli VPN connections
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE,ACTIVE", "connection", "show"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = line.split(":")
                if len(parts) >= 3 and "vpn" in parts[1].lower():
                    vpns.append(VPNConnection(
                        name=parts[0],
                        type="nmcli",
                        active=parts[2].lower() == "yes",
                    ))
    except Exception as e:
        logger.debug("nmcli VPN list failed: %s", e)

    # 2. WireGuard configs
    wg_dir = Path("/etc/wireguard")
    if wg_dir.exists():
        for conf in wg_dir.glob("*.conf"):
            name = conf.stem
            # Check if interface is active
            active = _is_wg_active(name)
            if not any(v.name == name for v in vpns):
                vpns.append(VPNConnection(
                    name=name,
                    type="wireguard",
                    active=active,
                    interface=name,
                ))

    return vpns


def connect_vpn(name: str = "") -> tuple[list[str], bool, str]:
    """Connect to a VPN.

    If name is empty, connects to the first available VPN.
    Tries WireGuard first, then nmcli.

    Returns:
        (steps, success, message)
    """
    steps = ["Conectando VPN"]

    # If no name specified, find first available
    if not name:
        vpns = list_vpns()
        inactive = [v for v in vpns if not v.active]
        if not inactive:
            if vpns:
                return steps, False, "Todas as VPNs já estão conectadas."
            return steps, False, "Nenhuma VPN configurada. Configure em /etc/wireguard/ ou via nmcli."
        name = inactive[0].name
        vpn_type = inactive[0].type
    else:
        # Determine type
        vpns = list_vpns()
        match = next((v for v in vpns if v.name.lower() == name.lower()), None)
        vpn_type = match.type if match else "wireguard"

    # Try WireGuard
    if vpn_type == "wireguard":
        try:
            result = subprocess.run(
                ["sudo", "wg-quick", "up", name],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return steps, True, f"VPN '{name}' conectada (WireGuard)."
            # Might need password — try nmcli
            logger.debug("wg-quick failed: %s", result.stderr)
        except Exception as e:
            logger.debug("wg-quick error: %s", e)

    # Try nmcli
    try:
        result = subprocess.run(
            ["nmcli", "connection", "up", name],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return steps, True, f"VPN '{name}' conectada."
        return steps, False, f"Falha ao conectar VPN '{name}': {result.stderr.strip()[:100]}"
    except Exception as e:
        return steps, False, f"Erro ao conectar VPN: {e}"


def disconnect_vpn(name: str = "") -> tuple[list[str], bool, str]:
    """Disconnect from a VPN.

    If name is empty, disconnects all active VPNs.

    Returns:
        (steps, success, message)
    """
    steps = ["Desconectando VPN"]

    if not name:
        vpns = list_vpns()
        active = [v for v in vpns if v.active]
        if not active:
            return steps, False, "Nenhuma VPN ativa."
        # Disconnect all
        for vpn in active:
            _disconnect_single(vpn)
        return steps, True, f"VPN desconectada ({len(active)} conexão(ões))."

    # Disconnect specific
    vpns = list_vpns()
    match = next((v for v in vpns if v.name.lower() == name.lower()), None)
    if match:
        success = _disconnect_single(match)
        if success:
            return steps, True, f"VPN '{name}' desconectada."
        return steps, False, f"Falha ao desconectar VPN '{name}'."

    return steps, False, f"VPN '{name}' não encontrada."


def get_vpn_status() -> tuple[list[str], bool, str]:
    """Get current VPN status.

    Returns:
        (steps, success, message)
    """
    vpns = list_vpns()
    active = [v for v in vpns if v.active]

    if active:
        names = ", ".join(v.name for v in active)
        return ["Verificando VPN"], True, f"VPN ativa: {names}"
    elif vpns:
        names = ", ".join(v.name for v in vpns)
        return ["Verificando VPN"], True, f"VPN disponível mas desconectada: {names}"
    else:
        return ["Verificando VPN"], True, "Nenhuma VPN configurada."


def _is_wg_active(interface: str) -> bool:
    """Check if a WireGuard interface is active."""
    try:
        result = subprocess.run(
            ["ip", "link", "show", interface],
            capture_output=True, text=True, timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def _disconnect_single(vpn: VPNConnection) -> bool:
    """Disconnect a single VPN connection."""
    if vpn.type == "wireguard":
        try:
            result = subprocess.run(
                ["sudo", "wg-quick", "down", vpn.name],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            pass

    # nmcli fallback
    try:
        result = subprocess.run(
            ["nmcli", "connection", "down", vpn.name],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False
