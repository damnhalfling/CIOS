"""Skill: file_search — find and open files by name or content.

Uses find + grep for fast local search. No LLM.
Designed to answer "onde está o contrato?" → actionable file list.
"""

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Max results to return
_MAX_RESULTS = 15
# Max search time (seconds)
_SEARCH_TIMEOUT = 10
# Directories to search by default
_SEARCH_DIRS = [
    "~/Documents", "~/Downloads", "~/Desktop",
    "~/Pictures", "~/Videos", "~/Music",
    "~",
]
# Directories to skip
_SKIP_DIRS = {
    ".git", ".cache", ".local", ".config", ".npm", ".cargo",
    "node_modules", "__pycache__", ".venv", "venv", ".tox",
    "snap", ".snap", ".mozilla", ".thunderbird",
}


@dataclass
class FileResult:
    """A single file search result."""
    path: str
    name: str
    size_human: str
    modified: str       # human-readable date
    file_type: str      # "document", "image", "video", "audio", "code", "archive", "other"
    match_type: str     # "name", "content"


@dataclass
class SearchReport:
    """Result of a file search."""
    plan_steps: list[str]
    results: list[FileResult]
    query: str
    searched_dirs: list[str]
    success: bool
    error: Optional[str] = None


def _size_human(b: int) -> str:
    """Convert bytes to human-readable string."""
    if b >= 1024 ** 3:
        return f"{b / (1024 ** 3):.1f}GB"
    if b >= 1024 ** 2:
        return f"{b / (1024 ** 2):.1f}MB"
    if b >= 1024:
        return f"{b / 1024:.0f}KB"
    return f"{b}B"


def _file_type(name: str) -> str:
    """Classify file by extension."""
    ext = Path(name).suffix.lower()
    _TYPES = {
        "document": {".pdf", ".doc", ".docx", ".odt", ".txt", ".rtf", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".ods"},
        "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff", ".heic"},
        "video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"},
        "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
        "code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php", ".sh", ".html", ".css", ".json", ".xml", ".yaml", ".yml", ".toml", ".md"},
        "archive": {".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz", ".deb"},
    }
    for ftype, exts in _TYPES.items():
        if ext in exts:
            return ftype
    return "other"


def _modified_human(timestamp: float) -> str:
    """Convert timestamp to human-readable date."""
    import time
    now = time.time()
    diff = now - timestamp

    if diff < 3600:
        mins = int(diff / 60)
        return f"{mins}min atrás" if mins > 0 else "agora"
    if diff < 86400:
        hours = int(diff / 3600)
        return f"{hours}h atrás"
    if diff < 86400 * 7:
        days = int(diff / 86400)
        return f"{days}d atrás"

    return time.strftime("%d/%m/%Y", time.localtime(timestamp))


def _build_prune_args() -> list[str]:
    """Build find -prune arguments for skipped directories."""
    parts = []
    parts.append("(")
    first = True
    for d in _SKIP_DIRS:
        if not first:
            parts.append("-o")
        parts.extend(["-name", d])
        first = False
    parts.extend([")", "-prune", "-o"])
    return parts


def search_files(query: str, search_dirs: Optional[list[str]] = None) -> SearchReport:
    """Search for files by name.

    Args:
        query: Search term (filename or partial name)
        search_dirs: Directories to search (defaults to common user dirs)

    Returns:
        SearchReport with results
    """
    plan_steps = ["Searching files"]
    results: list[FileResult] = []

    if not query:
        return SearchReport(
            plan_steps=plan_steps, results=[], query=query,
            searched_dirs=[], success=False, error="No search query")

    dirs = search_dirs or _SEARCH_DIRS
    resolved_dirs = []
    for d in dirs:
        p = Path(d).expanduser()
        if p.is_dir():
            resolved_dirs.append(str(p))

    if not resolved_dirs:
        return SearchReport(
            plan_steps=plan_steps, results=[], query=query,
            searched_dirs=dirs, success=False, error="No searchable directories found")

    plan_steps.append(f"Scanning {len(resolved_dirs)} directories")

    # Use find for name search (fast, no index needed)
    try:
        prune_args = _build_prune_args()
        cmd = ["find"] + resolved_dirs + prune_args + [
            "-iname", f"*{query}*",
            "-type", "f",
            "-print",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=_SEARCH_TIMEOUT,
        )

        if result.returncode == 0 or result.stdout.strip():
            for line in result.stdout.strip().splitlines()[:_MAX_RESULTS]:
                path = line.strip()
                if not path:
                    continue
                try:
                    stat = os.stat(path)
                    results.append(FileResult(
                        path=path,
                        name=os.path.basename(path),
                        size_human=_size_human(stat.st_size),
                        modified=_modified_human(stat.st_mtime),
                        file_type=_file_type(path),
                        match_type="name",
                    ))
                except OSError:
                    continue

    except subprocess.TimeoutExpired:
        plan_steps.append("Search timed out — showing partial results")
    except FileNotFoundError:
        return SearchReport(
            plan_steps=plan_steps, results=[], query=query,
            searched_dirs=dirs, success=False,
            error="find command not available")
    except Exception as e:
        logger.debug("File search error: %s", e)

    # If no name matches, try content search with grep
    if not results:
        plan_steps.append("Searching file contents")
        try:
            cmd = [
                "grep", "-rl", "--include=*.txt", "--include=*.md",
                "--include=*.pdf", "--include=*.doc", "--include=*.csv",
                "-i", query,
            ] + resolved_dirs[:3]  # limit dirs for content search

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=_SEARCH_TIMEOUT,
            )

            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().splitlines()[:_MAX_RESULTS]:
                    path = line.strip()
                    if not path:
                        continue
                    try:
                        stat = os.stat(path)
                        results.append(FileResult(
                            path=path,
                            name=os.path.basename(path),
                            size_human=_size_human(stat.st_size),
                            modified=_modified_human(stat.st_mtime),
                            file_type=_file_type(path),
                            match_type="content",
                        ))
                    except OSError:
                        continue
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

    return SearchReport(
        plan_steps=plan_steps,
        results=results,
        query=query,
        searched_dirs=dirs,
        success=True,
    )


def open_file(path: str) -> tuple[list[str], bool, Optional[str]]:
    """Open a file with the default application.

    Returns:
        (plan_steps, success, error)
    """
    plan_steps = [f"Opening {os.path.basename(path)}"]

    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        return plan_steps + ["File not found"], False, f"File not found: {path}"

    try:
        subprocess.Popen(
            ["xdg-open", str(resolved)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        plan_steps.append(f"{resolved.name} opened")
        return plan_steps, True, None
    except FileNotFoundError:
        return plan_steps, False, "xdg-open not available"
    except Exception as e:
        return plan_steps, False, str(e)


def find_and_open(query: str) -> tuple[list[str], bool, Optional[str]]:
    """Search for a file and open the best match.

    Returns:
        (plan_steps, success, error)
    """
    report = search_files(query)

    if not report.results:
        msg = f"File not found: {query}"
        return report.plan_steps + ["No results"], False, msg

    # Open the first (best) match
    best = report.results[0]
    open_steps, ok, err = open_file(best.path)
    return report.plan_steps + open_steps, ok, err
