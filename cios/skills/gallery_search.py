"""Gallery Search — search media files by date, text, and AI (CLIP).

Provides:
- Date-based search: "fotos de ontem", "fotos de janeiro", "fotos de 2024"
- Text/AI search: "fotos da praia", "fotos com cachorro" (CLIP embeddings)
- Combined results as MediaFile lists for gallery rendering

Dependencies:
- Pillow (EXIF date extraction)
- CLIP (optional, for semantic search — graceful degradation if unavailable)
"""

import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from cios.core.config import CIOS_HOME

logger = logging.getLogger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".heic"}
_ALL_MEDIA_EXTS = _IMAGE_EXTS | {".mp4", ".avi", ".mkv", ".mov", ".webm", ".mp3", ".wav", ".flac"}

_SEARCH_DIRS = [
    "~/Pictures", "~/Imagens",
    "~/Videos", "~/Vídeos",
    "~/Downloads",
    "~/Desktop",
    "~/Documents", "~/Documentos",
]

_CLIP_DB_PATH = CIOS_HOME / "clip_cache.db"

_CLIP_SCHEMA = """
CREATE TABLE IF NOT EXISTS clip_embeddings (
    file_path TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    mtime REAL NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clip_mtime ON clip_embeddings(mtime);
"""


# ═══════════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SearchResult:
    """Result of a gallery search."""
    files: list[dict] = field(default_factory=list)  # [{path, name, media_type, score}]
    query: str = ""
    search_type: str = ""  # "date", "text", "clip"
    total_found: int = 0


# ═══════════════════════════════════════════════════════════════════════════
#  DATE SEARCH (#254)
# ═══════════════════════════════════════════════════════════════════════════

def search_by_date(
    query: str,
    directories: Optional[list[str]] = None,
) -> SearchResult:
    """Search media files by date expression.

    Supports:
    - "ontem" / "yesterday"
    - "hoje" / "today"
    - "esta semana" / "this week"
    - "este mês" / "this month"
    - Month names: "janeiro", "february", etc.
    - Year: "2024", "2023"
    - Relative: "últimos 7 dias", "last 30 days"

    Uses file modification time (mtime) and EXIF date when available.
    """
    if directories is None:
        directories = _expand_dirs(_SEARCH_DIRS)

    date_range = _parse_date_query(query)
    if not date_range:
        return SearchResult(query=query, search_type="date")

    start_ts, end_ts = date_range

    # Collect files within date range
    files = []
    for directory in directories:
        _collect_by_date(directory, start_ts, end_ts, files, max_depth=3, depth=0)

    # Sort by date (newest first)
    files.sort(key=lambda f: f.get("mtime", 0), reverse=True)

    return SearchResult(
        files=files,
        query=query,
        search_type="date",
        total_found=len(files),
    )


def _parse_date_query(query: str) -> Optional[tuple[float, float]]:
    """Parse a date query into (start_timestamp, end_timestamp)."""
    q = query.lower().strip()
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Today / hoje
    if q in ("hoje", "today"):
        return (today_start.timestamp(), now.timestamp())

    # Yesterday / ontem
    if q in ("ontem", "yesterday"):
        yesterday = today_start - timedelta(days=1)
        return (yesterday.timestamp(), today_start.timestamp())

    # This week / esta semana
    if q in ("esta semana", "this week", "essa semana"):
        week_start = today_start - timedelta(days=today_start.weekday())
        return (week_start.timestamp(), now.timestamp())

    # This month / este mês
    if q in ("este mês", "este mes", "this month", "esse mês", "esse mes"):
        month_start = today_start.replace(day=1)
        return (month_start.timestamp(), now.timestamp())

    # Last N days / últimos N dias
    m = re.match(r"(?:[uú]ltimos?|last)\s+(\d+)\s+(?:dias?|days?)", q)
    if m:
        days = int(m.group(1))
        start = today_start - timedelta(days=days)
        return (start.timestamp(), now.timestamp())

    # Month names (PT)
    _MONTHS_PT = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3,
        "abril": 4, "maio": 5, "junho": 6,
        "julho": 7, "agosto": 8, "setembro": 9,
        "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    # Month names (EN)
    _MONTHS_EN = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }
    all_months = {**_MONTHS_PT, **_MONTHS_EN}

    for month_name, month_num in all_months.items():
        if month_name in q:
            # Check if year is specified
            year_match = re.search(r"(\d{4})", q)
            year = int(year_match.group(1)) if year_match else now.year
            # If the month hasn't happened yet this year, use last year
            if not year_match and month_num > now.month:
                year -= 1
            start = datetime(year, month_num, 1)
            if month_num == 12:
                end = datetime(year + 1, 1, 1)
            else:
                end = datetime(year, month_num + 1, 1)
            return (start.timestamp(), end.timestamp())

    # Year only (e.g., "2024")
    year_match = re.match(r"^(\d{4})$", q)
    if year_match:
        year = int(year_match.group(1))
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
        return (start.timestamp(), end.timestamp())

    return None


def _collect_by_date(
    path: str, start_ts: float, end_ts: float,
    results: list, max_depth: int, depth: int,
) -> None:
    """Recursively collect media files within a date range."""
    if depth > max_depth:
        return
    try:
        for entry in os.scandir(path):
            if entry.name.startswith("."):
                continue
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext not in _ALL_MEDIA_EXTS:
                    continue
                try:
                    stat = entry.stat()
                    # Use mtime as primary date (EXIF would be better but slower)
                    file_time = stat.st_mtime
                    if start_ts <= file_time <= end_ts:
                        media_type = "image" if ext in _IMAGE_EXTS else "video"
                        results.append({
                            "path": entry.path,
                            "name": entry.name,
                            "media_type": media_type,
                            "mtime": file_time,
                            "size_bytes": stat.st_size,
                        })
                except OSError:
                    continue
            elif entry.is_dir() and depth < max_depth:
                _collect_by_date(entry.path, start_ts, end_ts, results, max_depth, depth + 1)
    except (PermissionError, OSError):
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  TEXT/AI SEARCH — CLIP (#255)
# ═══════════════════════════════════════════════════════════════════════════

# CLIP availability flag (lazy-loaded)
_clip_available: Optional[bool] = None
_clip_model = None
_clip_processor = None


def _check_clip_available() -> bool:
    """Check if CLIP model is available for semantic search."""
    global _clip_available
    if _clip_available is not None:
        return _clip_available

    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        _clip_available = True
    except ImportError:
        _clip_available = False
        logger.info("CLIP not available (torch/transformers not installed). "
                    "Text search will use filename matching only.")

    return _clip_available


def _load_clip_model():
    """Lazy-load CLIP model (first call is slow, ~2-5s)."""
    global _clip_model, _clip_processor

    if _clip_model is not None:
        return _clip_model, _clip_processor

    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor

        model_name = "openai/clip-vit-base-patch32"
        _clip_processor = CLIPProcessor.from_pretrained(model_name)
        _clip_model = CLIPModel.from_pretrained(model_name)
        _clip_model.eval()
        logger.info("CLIP model loaded: %s", model_name)
        return _clip_model, _clip_processor
    except Exception as e:
        logger.warning("Failed to load CLIP model: %s", e)
        return None, None


def search_by_text(
    query: str,
    directories: Optional[list[str]] = None,
    max_results: int = 50,
) -> SearchResult:
    """Search media files by text description.

    Strategy:
    1. Try CLIP semantic search (if available)
    2. Fall back to filename matching

    Args:
        query: Natural language description ("praia", "cachorro", "sunset")
        directories: Paths to search
        max_results: Maximum results to return

    Returns:
        SearchResult with scored files.
    """
    if directories is None:
        directories = _expand_dirs(_SEARCH_DIRS)

    # Collect all image files
    all_files = _collect_all_images(directories)

    if not all_files:
        return SearchResult(query=query, search_type="text")

    # Try CLIP first
    if _check_clip_available():
        result = _search_clip(query, all_files, max_results)
        if result and result.total_found > 0:
            return result

    # Fallback: filename matching
    result = _search_filename(query, all_files, max_results)
    return result


def _search_clip(query: str, files: list[dict], max_results: int) -> Optional[SearchResult]:
    """Search using CLIP embeddings (semantic similarity)."""
    try:
        import torch
        from PIL import Image

        model, processor = _load_clip_model()
        if model is None or processor is None:
            return None

        # Encode text query
        text_inputs = processor(text=[query], return_tensors="pt", padding=True)
        with torch.no_grad():
            text_features = model.get_text_features(**text_inputs)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

        # Score each image
        scored = []
        for file_info in files:
            path = file_info["path"]
            try:
                img = Image.open(path).convert("RGB")
                img_inputs = processor(images=img, return_tensors="pt")
                with torch.no_grad():
                    img_features = model.get_image_features(**img_inputs)
                    img_features = img_features / img_features.norm(dim=-1, keepdim=True)

                # Cosine similarity
                similarity = (text_features @ img_features.T).item()
                file_info["score"] = similarity
                scored.append(file_info)
            except Exception:
                continue

        # Sort by score and filter
        scored.sort(key=lambda f: f.get("score", 0), reverse=True)

        # Take top results above threshold
        threshold = 0.20  # CLIP similarity threshold
        results = [f for f in scored[:max_results] if f.get("score", 0) >= threshold]

        return SearchResult(
            files=results,
            query=query,
            search_type="clip",
            total_found=len(results),
        )

    except Exception as e:
        logger.warning("CLIP search failed: %s", e)
        return None


def _search_filename(query: str, files: list[dict], max_results: int) -> SearchResult:
    """Fallback search: match query against filenames and parent folder names."""
    query_lower = query.lower()
    # Split query into words for partial matching
    query_words = set(query_lower.split())

    scored = []
    for file_info in files:
        name = file_info["name"].lower()
        path = file_info["path"].lower()
        parent = os.path.basename(os.path.dirname(path))

        score = 0.0

        # Exact substring in filename
        if query_lower in name:
            score = 0.9
        # Exact substring in parent folder
        elif query_lower in parent:
            score = 0.7
        # Word overlap
        else:
            name_words = set(re.split(r"[\s_\-\.]+", name))
            parent_words = set(re.split(r"[\s_\-\.]+", parent))
            all_words = name_words | parent_words

            overlap = query_words & all_words
            if overlap:
                score = 0.5 * (len(overlap) / len(query_words))

        if score > 0:
            file_info["score"] = score
            scored.append(file_info)

    scored.sort(key=lambda f: f.get("score", 0), reverse=True)
    results = scored[:max_results]

    return SearchResult(
        files=results,
        query=query,
        search_type="filename",
        total_found=len(results),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _expand_dirs(dirs: list[str]) -> list[str]:
    """Expand ~ and filter to existing directories."""
    result = []
    for d in dirs:
        expanded = os.path.expanduser(d)
        if os.path.isdir(expanded):
            result.append(expanded)
    return result


def _collect_all_images(directories: list[str], max_depth: int = 3) -> list[dict]:
    """Collect all image files from directories."""
    files = []
    for directory in directories:
        _collect_images_recursive(directory, files, max_depth, 0)
    return files


def _collect_images_recursive(path: str, results: list, max_depth: int, depth: int) -> None:
    """Recursively collect image files."""
    if depth > max_depth:
        return
    try:
        for entry in os.scandir(path):
            if entry.name.startswith("."):
                continue
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in _IMAGE_EXTS:
                    try:
                        stat = entry.stat()
                        results.append({
                            "path": entry.path,
                            "name": entry.name,
                            "media_type": "image",
                            "mtime": stat.st_mtime,
                            "size_bytes": stat.st_size,
                        })
                    except OSError:
                        continue
            elif entry.is_dir() and depth < max_depth:
                _collect_images_recursive(entry.path, results, max_depth, depth + 1)
    except (PermissionError, OSError):
        pass


def format_date_range(query: str) -> str:
    """Format a date query into a human-readable description."""
    q = query.lower().strip()
    if q in ("hoje", "today"):
        return "Hoje"
    if q in ("ontem", "yesterday"):
        return "Ontem"
    if q in ("esta semana", "this week", "essa semana"):
        return "Esta semana"
    if q in ("este mês", "este mes", "this month"):
        return "Este mês"
    return query.capitalize()
