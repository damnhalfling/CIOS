"""Printer skill — print documents via CUPS.

Supports listing printers, printing files, and checking print queue.

#520 — Printer support ("imprime este documento")
"""

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Printer:
    """A configured printer."""
    name: str
    description: str
    is_default: bool
    state: str  # "idle", "printing", "stopped"


def list_printers() -> list[Printer]:
    """List configured printers."""
    printers = []
    try:
        result = subprocess.run(
            ["lpstat", "-p", "-d"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []

        default_name = ""
        for line in result.stdout.split("\n"):
            if "system default destination:" in line.lower():
                default_name = line.split(":")[-1].strip()

        result2 = subprocess.run(
            ["lpstat", "-p"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result2.stdout.strip().split("\n"):
            if line.startswith("printer"):
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[1]
                    state = "idle"
                    if "disabled" in line.lower():
                        state = "stopped"
                    elif "printing" in line.lower():
                        state = "printing"
                    printers.append(Printer(
                        name=name,
                        description=name,
                        is_default=name == default_name,
                        state=state,
                    ))
    except Exception as e:
        logger.debug("Failed to list printers: %s", e)
    return printers


def print_file(file_path: str, printer: str = "", copies: int = 1) -> tuple[list[str], bool, str]:
    """Print a file.

    Args:
        file_path: Path to the file to print
        printer: Printer name (empty = default)
        copies: Number of copies

    Returns:
        (steps, success, message)
    """
    steps = [f"Imprimindo {file_path}"]
    cmd = ["lp"]

    if printer:
        cmd.extend(["-d", printer])
    if copies > 1:
        cmd.extend(["-n", str(copies)])
    cmd.append(file_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return steps, True, "Documento enviado para impressão."
        return steps, False, f"Falha: {result.stderr.strip()[:100]}"
    except FileNotFoundError:
        return steps, False, "CUPS não instalado. Instale com: sudo apt install cups"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def get_queue() -> tuple[list[str], bool, str]:
    """Get print queue status."""
    steps = ["Verificando fila de impressão"]
    try:
        result = subprocess.run(
            ["lpstat", "-o"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            if not output:
                return steps, True, "Fila de impressão vazia."
            return steps, True, f"Fila de impressão:\n{output}"
        return steps, True, "Fila de impressão vazia."
    except Exception as e:
        return steps, False, f"Erro: {e}"


def cancel_job(job_id: str = "") -> tuple[list[str], bool, str]:
    """Cancel a print job (or all jobs if no ID)."""
    steps = ["Cancelando impressão"]
    cmd = ["cancel"]
    if job_id:
        cmd.append(job_id)
    else:
        cmd.append("-a")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return steps, True, "Impressão cancelada."
        return steps, False, f"Falha: {result.stderr.strip()}"
    except Exception as e:
        return steps, False, f"Erro: {e}"
