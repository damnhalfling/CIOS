"""Disk Analysis skill — find what's eating disk space and clean it.

No LLM. Direct execution via du, find, and os.stat.
Designed to feel like magic: "libera espaço" → actionable report.
"""

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DiskHog:
    path: str
    size_bytes: int
    category: str  # "downloads", "cache", "logs", "node_modules", "trash", "videos", "other"
    description: str  # human-friendly name
    cleanable: bool  # safe to suggest deletion?


@dataclass
class DiskReport:
    plan_steps: list[str]
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent_used: float
    hogs: list[DiskHog]
    cleanable_bytes: int
    summary_lines: list[str]


def _size_human(b: int) -> str:
    """Convert bytes to human-readable string."""
    if b >= 1024**3:
        return f"{b / (1024**3):.1f}GB"
    if b >= 1024**2:
        return f"{b / (1024**2):.1f}MB"
    if b >= 1024:
        return f"{b / 1024:.0f}KB"
    return f"{b}B"


def _dir_size(path: str, max_depth: int = 3, timeout_files: int = 50000) -> int:
    """Get directory size. Stops early if too many files (avoids hanging)."""
    total = 0
    count = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            # Skip hidden dirs and symlinks
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for f in filenames:
                count += 1
                if count > timeout_files:
                    return total  # good enough estimate
                try:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        pass
    return total


def _find_hogs(home: str) -> list[DiskHog]:
    """Find the biggest space consumers in the user's home."""
    hogs: list[DiskHog] = []
    home_path = Path(home)

    # Known directories to scan
    targets = [
        ("Downloads", "downloads", "Downloads", True),
        ("Documents", "documents", "Documentos", False),
        ("Videos", "videos", "Vídeos", False),
        ("Pictures", "pictures", "Imagens", False),
        ("Music", "music", "Música", False),
        (".cache", "cache", "Cache do sistema", True),
        (".local/share/Trash", "trash", "Lixeira", True),
        ("snap", "cache", "Pacotes Snap", True),
        (".npm", "cache", "Cache npm", True),
        (".cargo", "cache", "Cache Cargo/Rust", True),
    ]

    for dirname, category, description, cleanable in targets:
        dirpath = home_path / dirname
        if dirpath.is_dir():
            size = _dir_size(str(dirpath))
            if size > 50 * 1024 * 1024:  # Only report > 50MB
                hogs.append(
                    DiskHog(
                        path=str(dirpath),
                        size_bytes=size,
                        category=category,
                        description=description,
                        cleanable=cleanable,
                    )
                )

    # Scan for node_modules (common space hog)
    nm_total = 0
    nm_count = 0
    try:
        for dirpath, dirnames, _ in os.walk(home):
            dirnames[:] = [
                d
                for d in dirnames
                if d not in (".cache", ".local", "snap", ".venv", ".git") and not d.startswith(".")
            ]
            if "node_modules" in dirnames:
                nm_path = os.path.join(dirpath, "node_modules")
                size = _dir_size(nm_path, max_depth=1)
                nm_total += size
                nm_count += 1
                dirnames.remove("node_modules")  # don't recurse into it
    except (OSError, PermissionError):
        pass

    if nm_total > 100 * 1024 * 1024:  # > 100MB
        hogs.append(
            DiskHog(
                path="~/*/node_modules",
                size_bytes=nm_total,
                category="node_modules",
                description=f"node_modules ({nm_count} projetos)",
                cleanable=True,
            )
        )

    # Scan for .venv directories
    venv_total = 0
    venv_count = 0
    try:
        for dirpath, dirnames, _ in os.walk(home):
            dirnames[:] = [
                d
                for d in dirnames
                if d not in (".cache", ".local", "snap", "node_modules") and not d.startswith(".")
            ]
            if ".venv" in dirnames:
                venv_path = os.path.join(dirpath, ".venv")
                size = _dir_size(venv_path, max_depth=1)
                venv_total += size
                venv_count += 1
                dirnames.remove(".venv")
    except (OSError, PermissionError):
        pass

    if venv_total > 100 * 1024 * 1024:
        hogs.append(
            DiskHog(
                path="~/*/.venv",
                size_bytes=venv_total,
                category="cache",
                description=f"Python venvs ({venv_count} projetos)",
                cleanable=True,
            )
        )

    # Sort by size descending
    hogs.sort(key=lambda h: h.size_bytes, reverse=True)
    return hogs[:10]


def analyze_disk() -> DiskReport:
    """Analyze disk usage and find space hogs.

    Returns a report with actionable suggestions.
    """
    plan_steps = ["Checking disk usage", "Scanning directories", "Finding large files"]

    # Overall disk stats
    usage = shutil.disk_usage("/")
    home = str(Path.home())

    # Find hogs
    hogs = _find_hogs(home)
    cleanable = sum(h.size_bytes for h in hogs if h.cleanable)

    # Build summary
    summary = []
    percent = (usage.used / usage.total) * 100

    if percent > 90:
        summary.append(
            f"⚠ Disk is {percent:.0f}% full — {_size_human(usage.free)} free of {_size_human(usage.total)}"
        )
    elif percent > 75:
        summary.append(
            f"Disk is {percent:.0f}% full — {_size_human(usage.free)} free of {_size_human(usage.total)}"
        )
    else:
        summary.append(
            f"Disk is fine — {_size_human(usage.free)} free of {_size_human(usage.total)}"
        )

    if hogs:
        summary.append("")
        summary.append("Biggest space consumers:")
        for h in hogs[:6]:
            marker = " 🧹" if h.cleanable else ""
            summary.append(f"  {h.description}: {_size_human(h.size_bytes)}{marker}")

    if cleanable > 100 * 1024 * 1024:
        summary.append("")
        summary.append(f"Can safely free up ~{_size_human(cleanable)} (marked with 🧹)")

    return DiskReport(
        plan_steps=plan_steps,
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        percent_used=percent,
        hogs=hogs,
        cleanable_bytes=cleanable,
        summary_lines=summary,
    )


def clean_safe(categories: list[str] | None = None) -> tuple[list[str], int, list[str]]:
    """Clean safe-to-delete directories.

    Args:
        categories: which categories to clean. Default: ["cache", "trash"]

    Returns:
        (plan_steps, bytes_freed, errors)
    """
    if categories is None:
        categories = ["cache", "trash"]

    home = str(Path.home())
    plan_steps = ["Cleaning safe directories"]
    freed = 0
    errors: list[str] = []

    # Map categories to actual paths
    clean_targets = {
        "cache": [
            os.path.join(home, ".cache"),
            os.path.join(home, ".npm"),
        ],
        "trash": [
            os.path.join(home, ".local", "share", "Trash"),
        ],
    }

    for cat in categories:
        if cat not in clean_targets:
            continue
        for target in clean_targets[cat]:
            if not os.path.isdir(target):
                continue
            try:
                size_before = _dir_size(target)
                # For cache: remove contents but keep the directory
                for item in os.listdir(target):
                    item_path = os.path.join(target, item)
                    try:
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                    except (OSError, PermissionError) as e:
                        errors.append(f"Could not remove {item}: {e}")
                size_after = _dir_size(target)
                freed += size_before - size_after
                plan_steps.append(
                    f"Cleaned {os.path.basename(target)}: {_size_human(size_before - size_after)} freed"
                )
            except Exception as e:
                errors.append(f"Error cleaning {target}: {e}")

    plan_steps.append(f"Total freed: {_size_human(freed)}")
    return plan_steps, freed, errors
