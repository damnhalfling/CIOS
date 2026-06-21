"""Gallery Store — SQLite persistence for favorites, albums, and file metadata.

Provides:
- Favorites: toggle, list, check
- Albums: create, rename, delete, add/remove files
- Trash: move files to XDG trash with undo support
- File metadata cache (for future use: faces, embeddings, etc.)

Database: ~/.cios/gallery.db
"""

import logging
import os
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from cios.core.config import CIOS_HOME

logger = logging.getLogger(__name__)

_DB_PATH = CIOS_HOME / "gallery.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    added_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fav_path ON favorites(file_path);

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_album_name ON albums(name);

CREATE TABLE IF NOT EXISTS album_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    added_at REAL NOT NULL,
    FOREIGN KEY (album_id) REFERENCES albums(id) ON DELETE CASCADE,
    UNIQUE(album_id, file_path)
);
CREATE INDEX IF NOT EXISTS idx_af_album ON album_files(album_id);
CREATE INDEX IF NOT EXISTS idx_af_path ON album_files(file_path);

CREATE TABLE IF NOT EXISTS trash_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path TEXT NOT NULL,
    trash_path TEXT NOT NULL,
    deleted_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trash_time ON trash_log(deleted_at DESC);
"""


# ═══════════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class Album:
    """An album/collection of media files."""

    id: int
    name: str
    created_at: float
    updated_at: float
    file_count: int = 0


@dataclass
class TrashEntry:
    """A file that was moved to trash."""

    original_path: str
    trash_path: str
    deleted_at: float


# ═══════════════════════════════════════════════════════════════════════════
#  TRASH HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _get_trash_dir() -> Path:
    """Get XDG trash directory (~/.local/share/Trash/)."""
    xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    trash_dir = Path(xdg_data) / "Trash"
    (trash_dir / "files").mkdir(parents=True, exist_ok=True)
    (trash_dir / "info").mkdir(parents=True, exist_ok=True)
    return trash_dir


def _move_to_trash(file_path: str) -> str | None:
    """Move a file to XDG trash. Returns trash path or None on failure.

    Creates a .trashinfo file per the freedesktop.org Trash spec.
    """
    src = Path(file_path)
    if not src.exists():
        return None

    trash_dir = _get_trash_dir()
    dest_name = src.name
    dest = trash_dir / "files" / dest_name

    # Handle name collisions
    counter = 1
    while dest.exists():
        stem = src.stem
        suffix = src.suffix
        dest_name = f"{stem}.{counter}{suffix}"
        dest = trash_dir / "files" / dest_name
        counter += 1

    # Write .trashinfo file (freedesktop spec)
    info_path = trash_dir / "info" / f"{dest_name}.trashinfo"
    deletion_date = time.strftime("%Y-%m-%dT%H:%M:%S")
    info_content = f"[Trash Info]\nPath={file_path}\nDeletionDate={deletion_date}\n"

    try:
        info_path.write_text(info_content)
        shutil.move(str(src), str(dest))
        return str(dest)
    except (OSError, shutil.Error) as e:
        logger.warning("Failed to trash %s: %s", file_path, e)
        # Clean up info file if move failed
        if info_path.exists():
            info_path.unlink()
        return None


def _restore_from_trash(trash_path: str, original_path: str) -> bool:
    """Restore a file from trash to its original location."""
    src = Path(trash_path)
    if not src.exists():
        return False

    dest = Path(original_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(src), str(dest))
        # Remove .trashinfo file
        trash_dir = _get_trash_dir()
        info_path = trash_dir / "info" / f"{src.name}.trashinfo"
        if info_path.exists():
            info_path.unlink()
        return True
    except (OSError, shutil.Error) as e:
        logger.warning("Failed to restore %s: %s", trash_path, e)
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  GALLERY STORE
# ═══════════════════════════════════════════════════════════════════════════


class GalleryStore:
    """SQLite-backed store for gallery metadata (favorites, albums, trash)."""

    def __init__(self) -> None:
        CIOS_HOME.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)

    # ─── Favorites ────────────────────────────────────────────────────

    def is_favorite(self, file_path: str) -> bool:
        """Check if a file is favorited."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM favorites WHERE file_path = ?", (file_path,)
            ).fetchone()
        return row is not None

    def toggle_favorite(self, file_path: str) -> bool:
        """Toggle favorite status. Returns new state (True = favorited)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM favorites WHERE file_path = ?", (file_path,)
            ).fetchone()
            if row:
                self._conn.execute("DELETE FROM favorites WHERE file_path = ?", (file_path,))
                self._conn.commit()
                return False
            else:
                self._conn.execute(
                    "INSERT INTO favorites (file_path, added_at) VALUES (?, ?)",
                    (file_path, time.time()),
                )
                self._conn.commit()
                return True

    def add_favorite(self, file_path: str) -> None:
        """Add a file to favorites (idempotent)."""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO favorites (file_path, added_at) VALUES (?, ?)",
                (file_path, time.time()),
            )
            self._conn.commit()

    def remove_favorite(self, file_path: str) -> None:
        """Remove a file from favorites."""
        with self._lock:
            self._conn.execute("DELETE FROM favorites WHERE file_path = ?", (file_path,))
            self._conn.commit()

    def list_favorites(self) -> list[str]:
        """List all favorited file paths (most recent first)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT file_path FROM favorites ORDER BY added_at DESC"
            ).fetchall()
        return [row["file_path"] for row in rows]

    def favorites_count(self) -> int:
        """Count total favorites."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM favorites").fetchone()
        return row[0] if row else 0

    # ─── Albums ───────────────────────────────────────────────────────

    def create_album(self, name: str) -> Album | None:
        """Create a new album. Returns None if name already exists."""
        now = time.time()
        with self._lock:
            try:
                cursor = self._conn.execute(
                    "INSERT INTO albums (name, created_at, updated_at) VALUES (?, ?, ?)",
                    (name, now, now),
                )
                self._conn.commit()
                return Album(
                    id=cursor.lastrowid, name=name, created_at=now, updated_at=now, file_count=0
                )
            except sqlite3.IntegrityError:
                return None

    def rename_album(self, album_id: int, new_name: str) -> bool:
        """Rename an album. Returns False if name conflict."""
        with self._lock:
            try:
                self._conn.execute(
                    "UPDATE albums SET name = ?, updated_at = ? WHERE id = ?",
                    (new_name, time.time(), album_id),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_album(self, album_id: int) -> None:
        """Delete an album (files are NOT deleted, just the association)."""
        with self._lock:
            self._conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
            self._conn.commit()

    def list_albums(self) -> list[Album]:
        """List all albums with file counts."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT a.id, a.name, a.created_at, a.updated_at,
                          COUNT(af.id) as file_count
                   FROM albums a
                   LEFT JOIN album_files af ON af.album_id = a.id
                   GROUP BY a.id
                   ORDER BY a.updated_at DESC"""
            ).fetchall()
        return [
            Album(
                id=r["id"],
                name=r["name"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                file_count=r["file_count"],
            )
            for r in rows
        ]

    def get_album_by_name(self, name: str) -> Album | None:
        """Find an album by name (case-insensitive)."""
        with self._lock:
            row = self._conn.execute(
                """SELECT a.id, a.name, a.created_at, a.updated_at,
                          COUNT(af.id) as file_count
                   FROM albums a
                   LEFT JOIN album_files af ON af.album_id = a.id
                   WHERE LOWER(a.name) = LOWER(?)
                   GROUP BY a.id""",
                (name,),
            ).fetchone()
        if row:
            return Album(
                id=row["id"],
                name=row["name"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                file_count=row["file_count"],
            )
        return None

    def add_to_album(self, album_id: int, file_path: str) -> None:
        """Add a file to an album (idempotent)."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO album_files (album_id, file_path, added_at) VALUES (?, ?, ?)",
                (album_id, file_path, now),
            )
            self._conn.execute("UPDATE albums SET updated_at = ? WHERE id = ?", (now, album_id))
            self._conn.commit()

    def remove_from_album(self, album_id: int, file_path: str) -> None:
        """Remove a file from an album."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM album_files WHERE album_id = ? AND file_path = ?",
                (album_id, file_path),
            )
            self._conn.commit()

    def get_album_files(self, album_id: int) -> list[str]:
        """Get all file paths in an album (most recent first)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT file_path FROM album_files WHERE album_id = ? ORDER BY added_at DESC",
                (album_id,),
            ).fetchall()
        return [row["file_path"] for row in rows]

    # ─── Trash ────────────────────────────────────────────────────────

    def trash_file(self, file_path: str) -> TrashEntry | None:
        """Move a file to XDG trash and log it. Returns entry or None on failure."""
        trash_path = _move_to_trash(file_path)
        if not trash_path:
            return None

        now = time.time()
        entry = TrashEntry(original_path=file_path, trash_path=trash_path, deleted_at=now)

        with self._lock:
            self._conn.execute(
                "INSERT INTO trash_log (original_path, trash_path, deleted_at) VALUES (?, ?, ?)",
                (file_path, trash_path, now),
            )
            # Also remove from favorites if it was favorited
            self._conn.execute("DELETE FROM favorites WHERE file_path = ?", (file_path,))
            # Remove from any albums
            self._conn.execute("DELETE FROM album_files WHERE file_path = ?", (file_path,))
            self._conn.commit()

        return entry

    def trash_files(self, file_paths: list[str]) -> list[TrashEntry]:
        """Move multiple files to trash. Returns list of successful entries."""
        entries = []
        for path in file_paths:
            entry = self.trash_file(path)
            if entry:
                entries.append(entry)
        return entries

    def undo_last_trash(self) -> str | None:
        """Restore the most recently trashed file. Returns original path or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, original_path, trash_path FROM trash_log ORDER BY deleted_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None

            original_path = row["original_path"]
            trash_path = row["trash_path"]
            row_id = row["id"]

        if _restore_from_trash(trash_path, original_path):
            with self._lock:
                self._conn.execute("DELETE FROM trash_log WHERE id = ?", (row_id,))
                self._conn.commit()
            return original_path
        return None

    def recent_trash(self, limit: int = 20) -> list[TrashEntry]:
        """List recently trashed files."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT original_path, trash_path, deleted_at FROM trash_log ORDER BY deleted_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            TrashEntry(
                original_path=r["original_path"],
                trash_path=r["trash_path"],
                deleted_at=r["deleted_at"],
            )
            for r in rows
        ]

    # ─── Cleanup ──────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

_store: GalleryStore | None = None


def get_store() -> GalleryStore:
    """Get or create the gallery store singleton."""
    global _store
    if _store is None:
        _store = GalleryStore()
    return _store
