"""Skill: file_organize — organize files in a directory by type."""

import os
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from harmoni.core.executor import Executor, ExecResult

# File type → folder name mapping
_TYPE_MAP: dict[str, str] = {
    # Images
    ".jpg": "Images", ".jpeg": "Images", ".png": "Images", ".gif": "Images",
    ".bmp": "Images", ".svg": "Images", ".webp": "Images", ".ico": "Images",
    ".tiff": "Images", ".heic": "Images",
    # Documents
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
    ".xls": "Documents", ".xlsx": "Documents", ".ppt": "Documents",
    ".pptx": "Documents", ".odt": "Documents", ".ods": "Documents",
    ".txt": "Documents", ".rtf": "Documents", ".csv": "Documents",
    # Videos
    ".mp4": "Videos", ".avi": "Videos", ".mkv": "Videos", ".mov": "Videos",
    ".wmv": "Videos", ".flv": "Videos", ".webm": "Videos",
    # Audio
    ".mp3": "Audio", ".wav": "Audio", ".flac": "Audio", ".aac": "Audio",
    ".ogg": "Audio", ".wma": "Audio", ".m4a": "Audio",
    # Archives
    ".zip": "Archives", ".tar": "Archives", ".gz": "Archives",
    ".rar": "Archives", ".7z": "Archives", ".bz2": "Archives",
    ".xz": "Archives", ".deb": "Archives",
    # Code
    ".py": "Code", ".js": "Code", ".ts": "Code", ".java": "Code",
    ".c": "Code", ".cpp": "Code", ".h": "Code", ".go": "Code",
    ".rs": "Code", ".rb": "Code", ".php": "Code", ".sh": "Code",
    ".html": "Code", ".css": "Code", ".json": "Code", ".xml": "Code",
    ".yaml": "Code", ".yml": "Code", ".toml": "Code", ".md": "Code",
    # Installers
    ".exe": "Installers", ".msi": "Installers", ".dmg": "Installers",
    ".AppImage": "Installers", ".snap": "Installers",
}


@dataclass
class OrganizeResult:
    plan_steps: list[str]
    moved: int
    folders_created: list[str]
    errors: list[str]


def organize_directory(directory: str, dry_run: bool = False) -> OrganizeResult:
    """
    Organize files in a directory by type.

    Returns an OrganizeResult with plan steps suitable for the UI feed.
    """
    target = Path(directory).expanduser().resolve()
    if not target.is_dir():
        return OrganizeResult(
            plan_steps=[f"Directory not found: {directory}"],
            moved=0,
            folders_created=[],
            errors=[f"Not a directory: {directory}"],
        )

    plan_steps = [f"Scanning {target.name}"]

    # Collect files (skip hidden, skip directories)
    files = [f for f in target.iterdir() if f.is_file() and not f.name.startswith(".")]

    if not files:
        plan_steps.append("No files to organize")
        return OrganizeResult(plan_steps=plan_steps, moved=0, folders_created=[], errors=[])

    # Group by type
    groups: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        ext = f.suffix.lower()
        folder = _TYPE_MAP.get(ext, "Other")
        groups[folder].append(f)

    plan_steps.append("Grouping files by type")

    moved = 0
    folders_created = []
    errors = []

    for folder_name, file_list in sorted(groups.items()):
        dest_dir = target / folder_name
        already_existed = dest_dir.exists()

        if not dry_run:
            dest_dir.mkdir(exist_ok=True)
            if not already_existed:
                folders_created.append(folder_name)

        plan_steps.append(f"Moving {len(file_list)} files to {folder_name}")

        for f in file_list:
            if dry_run:
                moved += 1
                continue
            try:
                dest = dest_dir / f.name
                # Handle name conflicts
                if dest.exists():
                    stem = f.stem
                    suffix = f.suffix
                    counter = 1
                    while dest.exists():
                        dest = dest_dir / f"{stem}_{counter}{suffix}"
                        counter += 1
                shutil.move(str(f), str(dest))
                moved += 1
            except Exception as e:
                errors.append(f"Could not move {f.name}: {e}")

    return OrganizeResult(
        plan_steps=plan_steps,
        moved=moved,
        folders_created=folders_created,
        errors=errors,
    )
