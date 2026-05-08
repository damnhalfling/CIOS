"""Face clustering skill — organize photos by person.

Detects faces in images, computes embeddings, clusters them into groups
(one group per person), and allows naming clusters.

Architecture:
- Face detection + embedding: face_recognition library (dlib-based)
- Clustering: DBSCAN (manual implementation, no sklearn needed)
- Persistence: SQLite (~/.cios/faces.db) for embeddings + cluster labels
- Incremental: only processes new/modified images

Dependencies (optional, graceful degradation):
- face_recognition (pip install face_recognition)
- numpy (already available)

If face_recognition is not installed, the skill will offer to install it
and return a helpful error message.
"""

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from cios.core.config import CIOS_HOME

logger = logging.getLogger(__name__)

_DB_PATH = CIOS_HOME / "faces.db"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

_SEARCH_DIRS = [
    "~/Pictures",
    "~/Imagens",
    "~/Downloads",
    "~/Desktop",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS face_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    face_index INTEGER NOT NULL DEFAULT 0,
    embedding BLOB NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    cluster_id INTEGER DEFAULT -1,
    mtime REAL NOT NULL,
    cached_at REAL NOT NULL,
    UNIQUE(file_path, face_index)
);
CREATE INDEX IF NOT EXISTS idx_face_path ON face_embeddings(file_path);
CREATE INDEX IF NOT EXISTS idx_face_cluster ON face_embeddings(cluster_id);

CREATE TABLE IF NOT EXISTS cluster_labels (
    cluster_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_label_name ON cluster_labels(name);
"""


# ═══════════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class FaceEntry:
    """A detected face with its embedding and cluster assignment."""

    id: int
    file_path: str
    face_index: int
    embedding: np.ndarray
    location: tuple  # (top, right, bottom, left)
    cluster_id: int


@dataclass
class PersonCluster:
    """A cluster of faces representing one person."""

    cluster_id: int
    name: str  # user-assigned name or "Pessoa N"
    face_count: int
    sample_paths: list[str] = field(default_factory=list)  # up to 5 sample images


@dataclass
class FaceScanResult:
    """Result of a face scan operation."""

    total_images_scanned: int = 0
    total_faces_found: int = 0
    new_faces: int = 0
    clusters: list[PersonCluster] = field(default_factory=list)
    scan_time_ms: float = 0.0
    error: str = ""


# ═══════════════════════════════════════════════════════════════════════════
#  DEPENDENCY CHECK
# ═══════════════════════════════════════════════════════════════════════════

_face_recognition_available: bool | None = None


def is_face_recognition_available() -> bool:
    """Check if face_recognition library is installed."""
    global _face_recognition_available
    if _face_recognition_available is not None:
        return _face_recognition_available

    try:
        import face_recognition  # noqa: F401

        _face_recognition_available = True
    except ImportError:
        _face_recognition_available = False

    return _face_recognition_available


def get_install_instructions() -> str:
    """Return instructions for installing face_recognition."""
    return (
        "Para organizar fotos por pessoa, instale a biblioteca de reconhecimento facial:\n"
        "  pip install face_recognition\n\n"
        "Requisitos: Python 3.8+, cmake, dlib.\n"
        "No Ubuntu/Debian: sudo apt install cmake libboost-all-dev"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  FACE DETECTION + EMBEDDING
# ═══════════════════════════════════════════════════════════════════════════


def detect_faces(image_path: str) -> list[tuple[np.ndarray, tuple]]:
    """Detect faces in an image and return (embedding, location) pairs.

    Returns list of (128-d embedding array, (top, right, bottom, left)) tuples.
    Returns empty list if no faces found or library unavailable.
    """
    if not is_face_recognition_available():
        return []

    try:
        import face_recognition

        # Load image
        image = face_recognition.load_image_file(image_path)

        # Detect face locations (HOG-based, faster than CNN)
        locations = face_recognition.face_locations(image, model="hog")

        if not locations:
            return []

        # Compute 128-d embeddings
        encodings = face_recognition.face_encodings(image, locations)

        return list(zip(encodings, locations, strict=False))

    except Exception as e:
        logger.debug("Face detection failed for %s: %s", image_path, e)
        return []


# ═══════════════════════════════════════════════════════════════════════════
#  DBSCAN CLUSTERING (manual, no sklearn needed)
# ═══════════════════════════════════════════════════════════════════════════


def dbscan_cluster(
    embeddings: np.ndarray,
    eps: float = 0.5,
    min_samples: int = 2,
) -> np.ndarray:
    """Simple DBSCAN implementation for face clustering.

    Args:
        embeddings: (N, 128) array of face embeddings.
        eps: Maximum distance between two samples in the same cluster.
             For face_recognition embeddings, 0.5 is a good threshold
             (faces with distance < 0.6 are typically the same person).
        min_samples: Minimum number of faces to form a cluster.

    Returns:
        Array of cluster labels (length N). -1 = noise/unclustered.
    """
    n = len(embeddings)
    if n == 0:
        return np.array([], dtype=int)

    # Compute pairwise distances (Euclidean)
    # For N < 10000 this is fast enough
    distances = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            dist = np.linalg.norm(embeddings[i] - embeddings[j])
            distances[i, j] = dist
            distances[j, i] = dist

    labels = np.full(n, -1, dtype=int)
    cluster_id = 0
    visited = np.zeros(n, dtype=bool)

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True

        # Find neighbors
        neighbors = _region_query(distances, i, eps)

        if len(neighbors) < min_samples:
            # Noise point
            continue

        # Start new cluster
        labels[i] = cluster_id
        seed_set = list(neighbors - {i})

        j = 0
        while j < len(seed_set):
            q = seed_set[j]
            if not visited[q]:
                visited[q] = True
                q_neighbors = _region_query(distances, q, eps)
                if len(q_neighbors) >= min_samples:
                    # Add new neighbors to seed set
                    for nb in q_neighbors:
                        if nb not in seed_set and labels[nb] == -1:
                            seed_set.append(nb)

            if labels[q] == -1:
                labels[q] = cluster_id
            j += 1

        cluster_id += 1

    return labels


def _region_query(distances: np.ndarray, point_idx: int, eps: float) -> set:
    """Find all points within eps distance of point_idx."""
    return set(np.where(distances[point_idx] <= eps)[0])


# ═══════════════════════════════════════════════════════════════════════════
#  FACE STORE (SQLite persistence)
# ═══════════════════════════════════════════════════════════════════════════


class FaceStore:
    """SQLite-backed store for face embeddings and cluster labels."""

    def __init__(self) -> None:
        CIOS_HOME.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)

    def get_cached_paths(self) -> set[str]:
        """Get all file paths that already have cached embeddings."""
        with self._lock:
            rows = self._conn.execute("SELECT DISTINCT file_path FROM face_embeddings").fetchall()
        return {row["file_path"] for row in rows}

    def is_stale(self, file_path: str) -> bool:
        """Check if cached embedding is stale (file modified since caching)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT mtime FROM face_embeddings WHERE file_path = ? LIMIT 1",
                (file_path,),
            ).fetchone()
        if not row:
            return True
        try:
            current_mtime = os.path.getmtime(file_path)
            return abs(current_mtime - row["mtime"]) > 1.0
        except OSError:
            return True

    def store_faces(self, file_path: str, faces: list[tuple[np.ndarray, tuple]]) -> None:
        """Store face embeddings for an image (replaces existing)."""
        now = time.time()
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            mtime = now

        with self._lock:
            # Remove old entries for this file
            self._conn.execute("DELETE FROM face_embeddings WHERE file_path = ?", (file_path,))
            # Insert new entries
            for idx, (embedding, location) in enumerate(faces):
                self._conn.execute(
                    """INSERT INTO face_embeddings
                       (file_path, face_index, embedding, location, cluster_id, mtime, cached_at)
                       VALUES (?, ?, ?, ?, -1, ?, ?)""",
                    (file_path, idx, embedding.tobytes(), json.dumps(location), mtime, now),
                )
            self._conn.commit()

    def get_all_embeddings(self) -> list[FaceEntry]:
        """Get all face entries with embeddings."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, file_path, face_index, embedding, location, cluster_id FROM face_embeddings"
            ).fetchall()

        entries = []
        for row in rows:
            embedding = np.frombuffer(row["embedding"], dtype=np.float64)
            location = tuple(json.loads(row["location"])) if row["location"] else ()
            entries.append(
                FaceEntry(
                    id=row["id"],
                    file_path=row["file_path"],
                    face_index=row["face_index"],
                    embedding=embedding,
                    location=location,
                    cluster_id=row["cluster_id"],
                )
            )
        return entries

    def update_clusters(self, assignments: list[tuple[int, int]]) -> None:
        """Update cluster assignments. assignments = [(face_id, cluster_id), ...]"""
        with self._lock:
            for face_id, cluster_id in assignments:
                self._conn.execute(
                    "UPDATE face_embeddings SET cluster_id = ? WHERE id = ?",
                    (cluster_id, face_id),
                )
            self._conn.commit()

    def get_cluster_files(self, cluster_id: int) -> list[str]:
        """Get all file paths in a cluster (unique, most recent first)."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT DISTINCT file_path FROM face_embeddings
                   WHERE cluster_id = ? ORDER BY mtime DESC""",
                (cluster_id,),
            ).fetchall()
        return [row["file_path"] for row in rows]

    def get_clusters(self) -> list[PersonCluster]:
        """Get all clusters with counts and sample paths."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT cluster_id, COUNT(*) as cnt
                   FROM face_embeddings
                   WHERE cluster_id >= 0
                   GROUP BY cluster_id
                   ORDER BY cnt DESC"""
            ).fetchall()

        clusters = []
        for row in rows:
            cid = row["cluster_id"]
            count = row["cnt"]

            # Get label
            name = self._get_label(cid)

            # Get sample paths
            samples = self.get_cluster_files(cid)[:5]

            clusters.append(
                PersonCluster(
                    cluster_id=cid,
                    name=name,
                    face_count=count,
                    sample_paths=samples,
                )
            )

        return clusters

    def _get_label(self, cluster_id: int) -> str:
        """Get the user-assigned label for a cluster."""
        row = self._conn.execute(
            "SELECT name FROM cluster_labels WHERE cluster_id = ?",
            (cluster_id,),
        ).fetchone()
        if row:
            return row["name"]
        return f"Pessoa {cluster_id + 1}"

    def set_label(self, cluster_id: int, name: str) -> None:
        """Set or update the label for a cluster."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO cluster_labels (cluster_id, name, created_at)
                   VALUES (?, ?, ?)""",
                (cluster_id, name, now),
            )
            self._conn.commit()

    def find_cluster_by_name(self, name: str) -> int | None:
        """Find a cluster ID by its label name (case-insensitive)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT cluster_id FROM cluster_labels WHERE LOWER(name) = LOWER(?)",
                (name,),
            ).fetchone()
        return row["cluster_id"] if row else None

    def total_faces(self) -> int:
        """Total number of face embeddings stored."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM face_embeddings").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

_store: FaceStore | None = None


def _get_store() -> FaceStore:
    global _store
    if _store is None:
        _store = FaceStore()
    return _store


def scan_and_cluster(
    directories: list[str] | None = None,
    on_progress: callable | None = None,
) -> FaceScanResult:
    """Scan images for faces, compute embeddings, and cluster.

    This is the main entry point. It:
    1. Collects image files from directories
    2. Detects faces (skipping already-cached files)
    3. Runs DBSCAN clustering on all embeddings
    4. Returns clusters

    Args:
        directories: Paths to scan. If None, uses defaults.
        on_progress: Optional callback(current, total, stage_msg).

    Returns:
        FaceScanResult with clusters and stats.
    """
    if not is_face_recognition_available():
        return FaceScanResult(
            error=get_install_instructions(),
        )

    t0 = time.monotonic()
    store = _get_store()

    if directories is None:
        directories = _expand_dirs(_SEARCH_DIRS)

    # 1. Collect image files
    all_files = _collect_images(directories)
    total = len(all_files)

    if total == 0:
        return FaceScanResult(scan_time_ms=0)

    # 2. Detect faces (incremental — skip cached)
    cached_paths = store.get_cached_paths()
    new_faces = 0

    for i, file_path in enumerate(all_files):
        if on_progress and i % 5 == 0:
            on_progress(i, total, "Detectando rostos…")

        # Skip if already cached and not stale
        if file_path in cached_paths and not store.is_stale(file_path):
            continue

        faces = detect_faces(file_path)
        if faces:
            store.store_faces(file_path, faces)
            new_faces += len(faces)

    if on_progress:
        on_progress(total, total, "Agrupando…")

    # 3. Get all embeddings and cluster
    entries = store.get_all_embeddings()
    total_faces = len(entries)

    if total_faces < 2:
        return FaceScanResult(
            total_images_scanned=total,
            total_faces_found=total_faces,
            new_faces=new_faces,
            scan_time_ms=(time.monotonic() - t0) * 1000,
        )

    # Build embedding matrix
    embeddings = np.array([e.embedding for e in entries])

    # Run DBSCAN
    labels = dbscan_cluster(embeddings, eps=0.5, min_samples=2)

    # 4. Update cluster assignments in DB
    assignments = [(entries[i].id, int(labels[i])) for i in range(len(entries))]
    store.update_clusters(assignments)

    # 5. Get final clusters
    clusters = store.get_clusters()

    elapsed = (time.monotonic() - t0) * 1000

    return FaceScanResult(
        total_images_scanned=total,
        total_faces_found=total_faces,
        new_faces=new_faces,
        clusters=clusters,
        scan_time_ms=elapsed,
    )


def get_person_photos(name: str) -> list[str]:
    """Get all photo paths for a named person.

    Args:
        name: Person name (as assigned by user via set_label).

    Returns:
        List of file paths containing that person's face.
    """
    store = _get_store()
    cluster_id = store.find_cluster_by_name(name)
    if cluster_id is None:
        return []
    return store.get_cluster_files(cluster_id)


def list_people() -> list[PersonCluster]:
    """List all known people (clusters with labels)."""
    store = _get_store()
    return store.get_clusters()


def name_person(cluster_id: int, name: str) -> None:
    """Assign a name to a face cluster."""
    store = _get_store()
    store.set_label(cluster_id, name)


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _expand_dirs(dirs: list[str]) -> list[str]:
    result = []
    for d in dirs:
        expanded = os.path.expanduser(d)
        if os.path.isdir(expanded):
            result.append(expanded)
    return result


def _collect_images(directories: list[str], max_depth: int = 3) -> list[str]:
    files = []
    for directory in directories:
        _collect_recursive(directory, files, max_depth, 0)
    return files


def _collect_recursive(path: str, results: list, max_depth: int, depth: int) -> None:
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
