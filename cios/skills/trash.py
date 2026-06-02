"""Trash skill — soft-delete files to XDG Trash before permanent removal.

Implements the FreeDesktop.org Trash specification:
- Files moved to ~/.local/share/Trash/files/
- Metadata stored in ~/.local/share/Trash/info/
- Supports restore (undo delete)

#513 — Trash / recycle bin (soft-delete)
"""

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TRASH_DIR = Path.home() / ".local" / "share" / "Trash"
TRASH_FILES = TRASH_DIR / "files"
TRASH_INFO = TRASH_DIR / "info"


@dataclass
class TrashItem:
    """An item in the trash."""
    name: str
    original_path: str
    deletion_date: str
    size: int
    is_dir: bool


def _ensure_trash_dirs():
    """Ensure trash directories exist."""
    TRASH_FILES.mkdir(parents=True, exist_ok=True)
    TRASH_INFO.mkdir(parents=True, exist_ok=True)


def trash_file(path: str) -> tuple[list[str], bool, str]:
    """Move a file/directory to trash (soft-delete).

    Creates .trashinfo metadata file for restore capability.

    Returns:
        (steps, success, message)
    """
    steps = ["Movendo para lixeira"]
    source = Path(path).expanduser().resolve()

    if not source.exists():
        return steps, False, f"Arquivo não encontrado: {path}"

    _ensure_trash_dirs()

    # Handle name conflicts in trash
    dest_name = source.name
    dest = TRASH_FILES / dest_name
    counter = 1
    while dest.exists():
        stem = source.stem
        suffix = source.suffix
        dest_name = f"{stem}_{counter}{suffix}"
        dest = TRASH_FILES / dest_name
        counter += 1

    # Create .trashinfo file
    info_content = (
        "[Trash Info]\n"
        f"Path={source}\n"
        f"DeletionDate={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n"
    )
    info_file = TRASH_INFO / f"{dest_name}.trashinfo"

    try:
        # Move file to trash
        shutil.move(str(source), str(dest))
        # Write metadata
        info_file.write_text(info_content)
        logger.info("Trashed: %s → %s", source, dest)
        return steps, True, f"'{source.name}' movido para a lixeira."
    except PermissionError:
        return steps, False, f"Sem permissão para mover '{source.name}'."
    except Exception as e:
        return steps, False, f"Erro ao mover para lixeira: {e}"


def restore_file(name: str) -> tuple[list[str], bool, str]:
    """Restore a file from trash to its original location.

    Returns:
        (steps, success, message)
    """
    steps = ["Restaurando da lixeira"]
    _ensure_trash_dirs()

    # Find the file in trash
    trash_path = TRASH_FILES / name
    info_path = TRASH_INFO / f"{name}.trashinfo"

    if not trash_path.exists():
        return steps, False, f"'{name}' não encontrado na lixeira."

    # Read original path from .trashinfo
    original_path = None
    if info_path.exists():
        for line in info_path.read_text().split("\n"):
            if line.startswith("Path="):
                original_path = line[5:].strip()
                break

    if not original_path:
        return steps, False, f"Não foi possível determinar o local original de '{name}'."

    dest = Path(original_path)

    # Check if destination already exists
    if dest.exists():
        return steps, False, f"Já existe um arquivo em '{original_path}'. Renomeie antes de restaurar."

    try:
        # Ensure parent directory exists
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Move back
        shutil.move(str(trash_path), str(dest))
        # Remove .trashinfo
        info_path.unlink(missing_ok=True)
        logger.info("Restored: %s → %s", trash_path, dest)
        return steps, True, f"'{name}' restaurado para {original_path}."
    except Exception as e:
        return steps, False, f"Erro ao restaurar: {e}"


def list_trash() -> list[TrashItem]:
    """List items in the trash."""
    _ensure_trash_dirs()
    items = []

    for item in TRASH_FILES.iterdir():
        info_path = TRASH_INFO / f"{item.name}.trashinfo"
        original_path = ""
        deletion_date = ""

        if info_path.exists():
            for line in info_path.read_text().split("\n"):
                if line.startswith("Path="):
                    original_path = line[5:].strip()
                elif line.startswith("DeletionDate="):
                    deletion_date = line[13:].strip()

        size = item.stat().st_size if item.is_file() else _dir_size(item)

        items.append(TrashItem(
            name=item.name,
            original_path=original_path,
            deletion_date=deletion_date,
            size=size,
            is_dir=item.is_dir(),
        ))

    # Sort by deletion date (most recent first)
    items.sort(key=lambda x: x.deletion_date, reverse=True)
    return items


def empty_trash() -> tuple[list[str], bool, str]:
    """Permanently delete all items in the trash.

    Returns:
        (steps, success, message)
    """
    steps = ["Esvaziando lixeira"]
    _ensure_trash_dirs()

    count = 0
    total_size = 0

    try:
        for item in TRASH_FILES.iterdir():
            size = item.stat().st_size if item.is_file() else _dir_size(item)
            total_size += size
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            count += 1

        # Clean info files
        for info in TRASH_INFO.iterdir():
            info.unlink()

        size_str = _format_size(total_size)
        return steps, True, f"Lixeira esvaziada: {count} item(ns), {size_str} liberados."
    except Exception as e:
        return steps, False, f"Erro ao esvaziar lixeira: {e}"


def get_trash_size() -> tuple[int, int]:
    """Get trash size (total_bytes, item_count)."""
    _ensure_trash_dirs()
    total = 0
    count = 0
    for item in TRASH_FILES.iterdir():
        total += item.stat().st_size if item.is_file() else _dir_size(item)
        count += 1
    return total, count


def _dir_size(path: Path) -> int:
    """Calculate directory size recursively."""
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except Exception:
        pass
    return total


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
