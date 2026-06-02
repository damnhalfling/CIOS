"""Backup skill — backup and restore via intent.

Uses rsync for file backup and supports Timeshift for system snapshots.

#526 — Backup/restore via intent
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = Path.home() / "Backups"


def backup_home(destination: str = "") -> tuple[list[str], bool, str]:
    """Backup home directory using rsync.

    Args:
        destination: Backup destination path (default: ~/Backups/YYYY-MM-DD/)

    Returns:
        (steps, success, message)
    """
    steps = ["Fazendo backup"]

    if not destination:
        date_str = datetime.now().strftime("%Y-%m-%d")
        dest_path = DEFAULT_BACKUP_DIR / date_str
    else:
        dest_path = Path(destination)

    dest_path.mkdir(parents=True, exist_ok=True)
    source = str(Path.home()) + "/"

    # Exclude common non-essential directories
    excludes = [
        "--exclude=.cache",
        "--exclude=.local/share/Trash",
        "--exclude=.venv",
        "--exclude=node_modules",
        "--exclude=__pycache__",
        "--exclude=.git/objects",
        "--exclude=snap",
    ]

    cmd = ["rsync", "-a", "--progress", "--delete"] + excludes + [source, str(dest_path) + "/"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return steps, True, f"Backup concluído em {dest_path}."
        return steps, False, f"Falha no backup: {result.stderr.strip()[:100]}"
    except subprocess.TimeoutExpired:
        return steps, False, "Backup demorou demais (timeout 10min)."
    except FileNotFoundError:
        return steps, False, "rsync não instalado. Instale com: sudo apt install rsync"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def backup_directory(source: str, destination: str = "") -> tuple[list[str], bool, str]:
    """Backup a specific directory.

    Returns:
        (steps, success, message)
    """
    steps = [f"Backup de {source}"]
    source_path = Path(source).expanduser().resolve()

    if not source_path.exists():
        return steps, False, f"Diretório não encontrado: {source}"

    if not destination:
        date_str = datetime.now().strftime("%Y-%m-%d")
        dest_path = DEFAULT_BACKUP_DIR / f"{source_path.name}_{date_str}"
    else:
        dest_path = Path(destination)

    dest_path.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            ["rsync", "-a", "--progress", str(source_path) + "/", str(dest_path) + "/"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return steps, True, f"Backup de '{source_path.name}' concluído em {dest_path}."
        return steps, False, f"Falha: {result.stderr.strip()[:100]}"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def list_backups() -> list[dict]:
    """List available backups."""
    backups = []
    if DEFAULT_BACKUP_DIR.exists():
        for item in sorted(DEFAULT_BACKUP_DIR.iterdir(), reverse=True):
            if item.is_dir():
                size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                backups.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "date": item.stat().st_mtime,
                        "size": size,
                    }
                )
    return backups[:20]


def create_system_snapshot() -> tuple[list[str], bool, str]:
    """Create a system snapshot using Timeshift (if available).

    Returns:
        (steps, success, message)
    """
    steps = ["Criando snapshot do sistema"]
    try:
        result = subprocess.run(
            [
                "sudo",
                "timeshift",
                "--create",
                "--comments",
                f"CIOS backup {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            return steps, True, "Snapshot do sistema criado."
        return steps, False, f"Falha: {result.stderr.strip()[:100]}"
    except FileNotFoundError:
        return steps, False, "Timeshift não instalado. Instale com: sudo apt install timeshift"
    except Exception as e:
        return steps, False, f"Erro: {e}"
