"""Firewall skill — manage firewall rules via intent.

Uses ufw (Uncomplicated Firewall) as the primary interface.
Falls back to iptables if ufw is not available.

#511 — Firewall via intent ("bloqueia porta 8080", "libera porta 22")
"""

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FirewallRule:
    """A firewall rule."""
    number: int
    action: str  # "ALLOW" | "DENY" | "REJECT"
    direction: str  # "IN" | "OUT"
    port: str
    protocol: str  # "tcp" | "udp" | "any"
    from_addr: str


def get_status() -> tuple[list[str], bool, str]:
    """Get firewall status.

    Returns:
        (steps, success, message)
    """
    steps = ["Verificando firewall"]

    try:
        result = subprocess.run(
            ["sudo", "ufw", "status", "verbose"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if "inactive" in output.lower():
                return steps, True, "Firewall inativo. Use 'ativar firewall' para habilitar."
            return steps, True, f"Firewall ativo.\n{output}"
        return steps, False, "Não foi possível verificar o firewall."
    except FileNotFoundError:
        return steps, False, "ufw não instalado. Instale com: sudo apt install ufw"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def enable_firewall() -> tuple[list[str], bool, str]:
    """Enable the firewall."""
    steps = ["Ativando firewall"]
    try:
        result = subprocess.run(
            ["sudo", "ufw", "--force", "enable"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return steps, True, "Firewall ativado."
        return steps, False, f"Falha: {result.stderr.strip()}"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def disable_firewall() -> tuple[list[str], bool, str]:
    """Disable the firewall."""
    steps = ["Desativando firewall"]
    try:
        result = subprocess.run(
            ["sudo", "ufw", "disable"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return steps, True, "Firewall desativado."
        return steps, False, f"Falha: {result.stderr.strip()}"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def allow_port(port: int, protocol: str = "tcp") -> tuple[list[str], bool, str]:
    """Allow incoming traffic on a port.

    Args:
        port: Port number
        protocol: "tcp", "udp", or "any"

    Returns:
        (steps, success, message)
    """
    steps = [f"Liberando porta {port}/{protocol}"]
    rule = f"{port}/{protocol}" if protocol != "any" else str(port)

    try:
        result = subprocess.run(
            ["sudo", "ufw", "allow", rule],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return steps, True, f"Porta {port}/{protocol} liberada."
        return steps, False, f"Falha: {result.stderr.strip()}"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def deny_port(port: int, protocol: str = "tcp") -> tuple[list[str], bool, str]:
    """Block incoming traffic on a port.

    Args:
        port: Port number
        protocol: "tcp", "udp", or "any"

    Returns:
        (steps, success, message)
    """
    steps = [f"Bloqueando porta {port}/{protocol}"]
    rule = f"{port}/{protocol}" if protocol != "any" else str(port)

    try:
        result = subprocess.run(
            ["sudo", "ufw", "deny", rule],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return steps, True, f"Porta {port}/{protocol} bloqueada."
        return steps, False, f"Falha: {result.stderr.strip()}"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def delete_rule(port: int, action: str = "allow", protocol: str = "tcp") -> tuple[list[str], bool, str]:
    """Delete a firewall rule.

    Returns:
        (steps, success, message)
    """
    steps = [f"Removendo regra {action} {port}/{protocol}"]
    rule = f"{port}/{protocol}" if protocol != "any" else str(port)

    try:
        result = subprocess.run(
            ["sudo", "ufw", "delete", action, rule],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return steps, True, f"Regra removida: {action} {port}/{protocol}."
        return steps, False, f"Falha: {result.stderr.strip()}"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def list_rules() -> list[FirewallRule]:
    """List current firewall rules."""
    rules = []
    try:
        result = subprocess.run(
            ["sudo", "ufw", "status", "numbered"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.startswith("["):
                    # Parse: [ 1] 22/tcp ALLOW IN Anywhere
                    parts = line.split("]", 1)
                    if len(parts) == 2:
                        num = int(parts[0].strip("[ "))
                        rest = parts[1].strip().split()
                        if len(rest) >= 3:
                            rules.append(FirewallRule(
                                number=num,
                                port=rest[0],
                                action=rest[1],
                                direction=rest[2] if len(rest) > 2 else "IN",
                                protocol="tcp" if "/" not in rest[0] else rest[0].split("/")[1],
                                from_addr=rest[3] if len(rest) > 3 else "Anywhere",
                            ))
    except Exception as e:
        logger.debug("Failed to list firewall rules: %s", e)
    return rules
