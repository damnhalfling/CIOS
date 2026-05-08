"""Duplicate detection skill — finds identical and visually similar images.

Detection methods:
1. MD5 hash — finds byte-identical files (fast, exact)
2. Perceptual hash (pHash) — finds visually similar images (resize-tolerant)

Flow:
    scan_duplicates(paths) → list of DuplicateGroup
    Each group contains 2+ files that are duplicates of each other.

Dependencies:
- Pillow (for pHash computation)
- hashlib (stdlib, for MD5)
"""

import hashlib
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field

from cios.core.config import CIOS_HOME

logger = logging.getLogger(__name__)

_DB_PATH = CIOS_HOME / "duplicates_cache.db"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".heic"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS phash_cache (
    file_path TEXT PRIMARY KEY,
    phash TEXT NOT NULL,
    md5 TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_phash ON phash_cache(phash);
CREATE INDEX IF NOT EXISTS idx_md5 ON phash_cache(md5);
"""


# ═══════════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DuplicateFile:
    """A file within a duplicate group."""

    path: str
    name: str
    size_bytes: int
    mtime: float  # modification time
    phash: str
    md5: str


@dataclass
class DuplicateGroup:
    """A group of duplicate files."""

    files: list[DuplicateFile] = field(default_factory=list)
    match_type: str = "exact"  # "exact" (MD5) or "similar" (pHash)
    similarity: float = 1.0  # 1.0 = identical, 0.9+ = very similar

    @property
    def total_size(self) -> int:
        return sum(f.size_bytes for f in self.files)

    @property
    def wasted_size(self) -> int:
        """Size that could be freed by keeping only one copy."""
        if not self.files:
            return 0
        # Keep the largest (likely best quality), waste the rest
        sizes = sorted((f.size_bytes for f in self.files), reverse=True)
        return sum(sizes[1:])

    @property
    def best_file(self) -> DuplicateFile | None:
        """The 'best' file to keep (largest size = highest quality)."""
        if not self.files:
            return None
        return max(self.files, key=lambda f: f.size_bytes)


@dataclass
class DuplicateScanResult:
    """Result of a duplicate scan."""

    groups: list[DuplicateGroup] = field(default_factory=list)
    total_files_scanned: int = 0
    total_duplicates: int = 0
    wasted_bytes: int = 0
    scan_time_ms: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  PERCEPTUAL HASH (pHash)
# ═══════════════════════════════════════════════════════════════════════════


def compute_phash(image_path: str, hash_size: int = 8) -> str | None:
    """Compute perceptual hash of an image.

    Algorithm (average hash + gradient):
    1. Resize to (hash_size+1) x hash_size
    2. Convert to grayscale
    3. Compare each pixel to its right neighbor (horizontal gradient)
    4. Encode differences as bits → hex string

    This approach is more discriminative than simple average hash
    for solid-color or low-contrast images.

    Returns hex string (64 bits for hash_size=8) or None on failure.
    """
    try:
        from PIL import Image

        img = Image.open(image_path)
        # Resize to (hash_size+1) x hash_size for gradient comparison
        img = img.resize((hash_size + 1, hash_size), Image.LANCZOS).convert("L")

        pixels = list(img.getdata())
        width = hash_size + 1

        # Compute horizontal gradient: pixel[x] > pixel[x+1]
        bits = []
        for y in range(hash_size):
            for x in range(hash_size):
                idx = y * width + x
                bits.append("1" if pixels[idx] > pixels[idx + 1] else "0")

        # Convert to hex
        hash_int = int("".join(bits), 2)
        hex_str = format(hash_int, f"0{hash_size * hash_size // 4}x")
        return hex_str

    except Exception as e:
        logger.debug("pHash failed for %s: %s", image_path, e)
        return None


def compute_md5(file_path: str) -> str | None:
    """Compute MD5 hash of a file (reads in chunks for large files)."""
    try:
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()
    except OSError as e:
        logger.debug("MD5 failed for %s: %s", file_path, e)
        return None


def hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two hex hash strings."""
    if len(hash1) != len(hash2):
        return 64  # max distance
    # Convert hex to binary and count differing bits
    try:
        int1 = int(hash1, 16)
        int2 = int(hash2, 16)
        xor = int1 ^ int2
        return bin(xor).count("1")
    except ValueError:
        return 64


def phash_similarity(hash1: str, hash2: str) -> float:
    """Compute similarity between two pHash values (0.0 to 1.0)."""
    dist = hamming_distance(hash1, hash2)
    max_bits = len(hash1) * 4  # each hex char = 4 bits
    if max_bits == 0:
        return 0.0
    return 1.0 - (dist / max_bits)


# ═══════════════════════════════════════════════════════════════════════════
#  CACHE
# ═══════════════════════════════════════════════════════════════════════════


class _HashCache:
    """SQLite cache for computed hashes (survives restarts)."""

    def __init__(self) -> None:
        CIOS_HOME.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)

    def get(self, file_path: str) -> tuple[str, str] | None:
        """Get cached (phash, md5) for a file if still valid."""
        with self._lock:
            row = self._conn.execute(
                "SELECT phash, md5, mtime FROM phash_cache WHERE file_path = ?",
                (file_path,),
            ).fetchone()

        if not row:
            return None

        # Check if file was modified since caching
        try:
            current_mtime = os.path.getmtime(file_path)
            if abs(current_mtime - row["mtime"]) > 1.0:
                return None  # stale
        except OSError:
            return None

        return (row["phash"], row["md5"])

    def store(self, file_path: str, phash: str, md5: str, file_size: int, mtime: float) -> None:
        """Cache hash results for a file."""
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO phash_cache
                   (file_path, phash, md5, file_size, mtime, cached_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (file_path, phash, md5, file_size, mtime, time.time()),
            )
            self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


_cache: _HashCache | None = None


def _get_cache() -> _HashCache:
    global _cache
    if _cache is None:
        _cache = _HashCache()
    return _cache


# ═══════════════════════════════════════════════════════════════════════════
#  SCANNER
# ═══════════════════════════════════════════════════════════════════════════


def scan_duplicates(
    directories: list[str] | None = None,
    similarity_threshold: float = 0.90,
    on_progress: callable | None = None,
) -> DuplicateScanResult:
    """Scan for duplicate images in given directories.

    Args:
        directories: Paths to scan. If None, uses default media dirs.
        similarity_threshold: pHash similarity threshold (0.90 = very similar).
        on_progress: Optional callback(current, total) for progress reporting.

    Returns:
        DuplicateScanResult with groups of duplicates found.
    """
    t0 = time.monotonic()

    if directories is None:
        directories = _default_scan_dirs()

    # 1. Collect all image files
    all_files = _collect_image_files(directories)
    total = len(all_files)

    if total == 0:
        return DuplicateScanResult(scan_time_ms=0)

    # 2. Compute hashes for all files (with cache)
    cache = _get_cache()
    file_hashes: list[DuplicateFile] = []

    for i, file_path in enumerate(all_files):
        if on_progress and i % 10 == 0:
            on_progress(i, total)

        cached = cache.get(file_path)
        if cached:
            phash, md5 = cached
        else:
            phash = compute_phash(file_path)
            md5 = compute_md5(file_path)
            if phash is None or md5 is None:
                continue
            try:
                stat = os.stat(file_path)
                cache.store(file_path, phash, md5, stat.st_size, stat.st_mtime)
            except OSError:
                continue

        try:
            stat = os.stat(file_path)
            file_hashes.append(
                DuplicateFile(
                    path=file_path,
                    name=os.path.basename(file_path),
                    size_bytes=stat.st_size,
                    mtime=stat.st_mtime,
                    phash=phash,
                    md5=md5,
                )
            )
        except OSError:
            continue

    if on_progress:
        on_progress(total, total)

    # 3. Group by MD5 (exact duplicates)
    exact_groups = _group_by_md5(file_hashes)

    # 4. Group by pHash similarity (visually similar, excluding exact dupes)
    exact_paths = set()
    for g in exact_groups:
        for f in g.files:
            exact_paths.add(f.path)

    remaining = [f for f in file_hashes if f.path not in exact_paths]
    similar_groups = _group_by_phash(remaining, similarity_threshold)

    # 5. Combine results
    all_groups = exact_groups + similar_groups
    total_duplicates = sum(len(g.files) - 1 for g in all_groups)
    wasted = sum(g.wasted_size for g in all_groups)

    elapsed = (time.monotonic() - t0) * 1000

    return DuplicateScanResult(
        groups=all_groups,
        total_files_scanned=total,
        total_duplicates=total_duplicates,
        wasted_bytes=wasted,
        scan_time_ms=elapsed,
    )


def _default_scan_dirs() -> list[str]:
    """Default directories to scan for duplicates."""
    dirs = [
        "~/Pictures",
        "~/Imagens",
        "~/Downloads",
        "~/Desktop",
        "~/Documents",
        "~/Documentos",
    ]
    result = []
    for d in dirs:
        expanded = os.path.expanduser(d)
        if os.path.isdir(expanded):
            result.append(expanded)
    return result


def _collect_image_files(directories: list[str], max_depth: int = 3) -> list[str]:
    """Recursively collect image files from directories."""
    files = []
    for directory in directories:
        _collect_recursive(directory, files, max_depth, 0)
    return files


def _collect_recursive(path: str, results: list, max_depth: int, depth: int) -> None:
    """Recursive file collector with depth limit."""
    if depth > max_depth:
        return
    try:
        for entry in os.scandir(path):
            if entry.name.startswith("."):
                continue
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in _IMAGE_EXTS:
                    results.append(entry.path)
            elif entry.is_dir() and depth < max_depth:
                _collect_recursive(entry.path, results, max_depth, depth + 1)
    except (PermissionError, OSError):
        pass


def _group_by_md5(files: list[DuplicateFile]) -> list[DuplicateGroup]:
    """Group files by identical MD5 hash."""
    md5_map: dict[str, list[DuplicateFile]] = {}
    for f in files:
        md5_map.setdefault(f.md5, []).append(f)

    groups = []
    for _md5, group_files in md5_map.items():
        if len(group_files) >= 2:
            groups.append(
                DuplicateGroup(
                    files=group_files,
                    match_type="exact",
                    similarity=1.0,
                )
            )

    return groups


def _group_by_phash(files: list[DuplicateFile], threshold: float) -> list[DuplicateGroup]:
    """Group files by perceptual hash similarity using union-find.

    Uses a simple O(n²) comparison — acceptable for typical photo collections
    (< 10k files). For larger collections, could use LSH.
    """
    n = len(files)
    if n < 2:
        return []

    # Union-Find
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Compare all pairs
    for i in range(n):
        for j in range(i + 1, n):
            sim = phash_similarity(files[i].phash, files[j].phash)
            if sim >= threshold:
                union(i, j)

    # Collect groups
    group_map: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        group_map.setdefault(root, []).append(i)

    groups = []
    for indices in group_map.values():
        if len(indices) >= 2:
            group_files = [files[i] for i in indices]
            # Compute average similarity within group
            sims = []
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    sims.append(phash_similarity(files[indices[a]].phash, files[indices[b]].phash))
            avg_sim = sum(sims) / len(sims) if sims else 0.9

            groups.append(
                DuplicateGroup(
                    files=group_files,
                    match_type="similar",
                    similarity=avg_sim,
                )
            )

    return groups


# ═══════════════════════════════════════════════════════════════════════════
#  UTILITY
# ═══════════════════════════════════════════════════════════════════════════


def format_size(bytes_val: int) -> str:
    """Format bytes to human-readable string."""
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"
