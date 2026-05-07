"""Media Player skill — inline photo gallery, video, and audio playback.

Renders media inside the CIOS GUI without opening external apps.
Scans common directories and mounted media for content.

Features:
- Photo gallery: thumbnails grid → click to enlarge → Esc to go back
- Video player: embedded mpv via subprocess (Tk frame)
- Audio player: play/pause, progress bar, track info
- Auto-detect mounted USB/media drives
- Guided flow when multiple sources found

Dependencies:
- Pillow (thumbnails, image display)
- mpv (video/audio playback via subprocess)
- ffmpeg (video thumbnail extraction)
"""

import logging
import os
import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".heic", ".svg"}
_VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"}
_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus"}

_SEARCH_DIRS = [
    "~/Pictures", "~/Imagens",
    "~/Videos", "~/Vídeos",
    "~/Music", "~/Música",
    "~/Downloads",
    "~/Desktop",
]

_MOUNT_DIRS = ["/media", "/mnt", "/run/media"]


# ═══════════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MediaFile:
    """A discovered media file."""
    path: str
    name: str
    media_type: str  # "image", "video", "audio"
    size_bytes: int = 0
    source: str = ""  # "Pictures", "USB Kingston", etc.


@dataclass
class MediaSource:
    """A location containing media files."""
    name: str        # "Imagens", "Pendrive Kingston"
    path: str
    count: int = 0
    media_type: str = ""  # dominant type


@dataclass
class ScanResult:
    """Result of scanning for media."""
    files: list[MediaFile] = field(default_factory=list)
    sources: list[MediaSource] = field(default_factory=list)
    total: int = 0


@dataclass
class GallerySignal:
    """Structured gallery result from planner."""
    source_path: str
    media_type: str  # "image" or "video"
    total_count: int
    files: list[MediaFile]

    def to_dict(self) -> dict:
        return {
            "gallery": {
                "source_path": self.source_path,
                "media_type": self.media_type,
                "total_count": self.total_count,
                "files": [
                    {"path": f.path, "name": f.name, "media_type": f.media_type}
                    for f in self.files
                ],
            },
            "status": "success",
            "steps": [f"Escaneando {self.source_path}…", f"{self.total_count} arquivos encontrados"],
        }


# ═══════════════════════════════════════════════════════════════════════════
#  SCANNING
# ═══════════════════════════════════════════════════════════════════════════

def scan_media(media_type: str = "image", query: str = "") -> ScanResult:
    """Scan for media files in common locations + mounted drives.

    Args:
        media_type: "image", "video", "audio", or "all"
        query: optional filter (filename contains query)

    Returns:
        ScanResult with files and sources found.
    """
    exts = _get_extensions(media_type)
    files: list[MediaFile] = []
    sources: list[MediaSource] = []

    # Scan standard directories
    for dir_path in _SEARCH_DIRS:
        expanded = os.path.expanduser(dir_path)
        if not os.path.isdir(expanded):
            continue
        found = _scan_directory(expanded, exts, query, depth=2)
        if found:
            source_name = os.path.basename(expanded)
            files.extend(found)
            sources.append(MediaSource(
                name=source_name,
                path=expanded,
                count=len(found),
                media_type=media_type,
            ))

    # Scan mounted media (USB drives, etc.)
    for mount_root in _MOUNT_DIRS:
        if not os.path.isdir(mount_root):
            continue
        try:
            user = os.environ.get("USER", "")
            # /media/$USER/DriveName or /mnt/DriveName
            scan_root = os.path.join(mount_root, user) if user and os.path.isdir(os.path.join(mount_root, user)) else mount_root
            for entry in os.scandir(scan_root):
                if not entry.is_dir():
                    continue
                found = _scan_directory(entry.path, exts, query, depth=3)
                if found:
                    files.extend(found)
                    sources.append(MediaSource(
                        name=f"📀 {entry.name}",
                        path=entry.path,
                        count=len(found),
                        media_type=media_type,
                    ))
        except (PermissionError, OSError):
            continue

    return ScanResult(files=files, sources=sources, total=len(files))


def _scan_directory(path: str, exts: set, query: str, depth: int = 2) -> list[MediaFile]:
    """Recursively scan a directory for media files (limited depth)."""
    results = []
    try:
        _scan_recursive(path, exts, query, results, depth, 0)
    except (PermissionError, OSError):
        pass
    return results


def _scan_recursive(path: str, exts: set, query: str, results: list, max_depth: int, current_depth: int) -> None:
    """Recursive scanner with depth limit."""
    if current_depth > max_depth:
        return
    try:
        for entry in os.scandir(path):
            if entry.name.startswith("."):
                continue
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in exts:
                    if query and query.lower() not in entry.name.lower():
                        continue
                    media_type = _ext_to_type(ext)
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        size = 0
                    results.append(MediaFile(
                        path=entry.path,
                        name=entry.name,
                        media_type=media_type,
                        size_bytes=size,
                        source=os.path.basename(path),
                    ))
            elif entry.is_dir() and current_depth < max_depth:
                _scan_recursive(entry.path, exts, query, results, max_depth, current_depth + 1)
    except (PermissionError, OSError):
        pass


def _get_extensions(media_type: str) -> set:
    """Get file extensions for a media type."""
    if media_type == "image":
        return _IMAGE_EXTS
    elif media_type == "video":
        return _VIDEO_EXTS
    elif media_type == "audio":
        return _AUDIO_EXTS
    else:  # "all"
        return _IMAGE_EXTS | _VIDEO_EXTS | _AUDIO_EXTS


def _ext_to_type(ext: str) -> str:
    """Map extension to media type."""
    if ext in _IMAGE_EXTS:
        return "image"
    elif ext in _VIDEO_EXTS:
        return "video"
    elif ext in _AUDIO_EXTS:
        return "audio"
    return "other"


# ═══════════════════════════════════════════════════════════════════════════
#  THUMBNAIL GENERATION
# ═══════════════════════════════════════════════════════════════════════════

_THUMB_DIR = Path.home() / ".cios" / "thumbnails"


def get_thumbnail(file_path: str, size: tuple = (160, 160)) -> Optional[str]:
    """Get or generate a thumbnail for a media file.

    Returns path to thumbnail PNG, or None if generation fails.
    """
    _THUMB_DIR.mkdir(parents=True, exist_ok=True)

    # Hash-based cache key
    import hashlib
    key = hashlib.md5(f"{file_path}:{size}".encode()).hexdigest()
    thumb_path = _THUMB_DIR / f"{key}.png"

    if thumb_path.exists():
        return str(thumb_path)

    ext = os.path.splitext(file_path)[1].lower()

    if ext in _IMAGE_EXTS:
        return _thumb_image(file_path, thumb_path, size)
    elif ext in _VIDEO_EXTS:
        return _thumb_video(file_path, thumb_path, size)
    elif ext in _AUDIO_EXTS:
        return None  # Audio doesn't have visual thumbnails

    return None


def _thumb_image(src: str, dest: Path, size: tuple) -> Optional[str]:
    """Generate thumbnail for an image using Pillow."""
    try:
        from PIL import Image
        img = Image.open(src)
        img.thumbnail(size, Image.LANCZOS)
        img.save(str(dest), "PNG")
        return str(dest)
    except Exception as e:
        logger.debug("Thumbnail failed for %s: %s", src, e)
        return None


def _thumb_video(src: str, dest: Path, size: tuple) -> Optional[str]:
    """Generate thumbnail for a video using ffmpeg."""
    if not shutil.which("ffmpeg"):
        return None
    try:
        # Extract frame at 10% of duration
        result = subprocess.run(
            ["ffmpeg", "-i", src, "-ss", "00:00:03", "-vframes", "1",
             "-vf", f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=decrease",
             "-y", str(dest)],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0 and dest.exists():
            return str(dest)
    except Exception as e:
        logger.debug("Video thumbnail failed for %s: %s", src, e)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  PLAYBACK
# ═══════════════════════════════════════════════════════════════════════════

def play_media(file_path: str) -> tuple[bool, str]:
    """Play a media file using mpv (embedded or standalone).

    Returns (success, message).
    """
    if not os.path.isfile(file_path):
        return False, "Arquivo não encontrado"

    # Check for mpv
    if not shutil.which("mpv"):
        return False, "mpv não instalado. Instale com: instalar mpv"

    ext = os.path.splitext(file_path)[1].lower()
    name = os.path.basename(file_path)

    try:
        # Launch mpv with minimal UI
        cmd = ["mpv", "--force-window=yes", "--osd-level=1"]

        if ext in _AUDIO_EXTS:
            # Audio: small window with visualizer
            cmd.extend(["--force-window=yes", "--geometry=400x100"])

        cmd.append(file_path)

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, name
    except Exception as e:
        logger.warning("Failed to play %s: %s", file_path, e)
        return False, f"Erro ao reproduzir: {name}"


def stop_playback() -> tuple[bool, str]:
    """Stop any running mpv instance."""
    try:
        subprocess.run(["pkill", "-f", "mpv"], capture_output=True, timeout=5)
        return True, "Reprodução parada"
    except Exception:
        return False, "Nenhuma reprodução ativa"


# ═══════════════════════════════════════════════════════════════════════════
#  DEPENDENCY CHECK
# ═══════════════════════════════════════════════════════════════════════════

def check_dependencies() -> dict:
    """Check which media dependencies are available."""
    deps = {
        "pillow": False,
        "mpv": shutil.which("mpv") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
    }
    try:
        import PIL
        deps["pillow"] = True
    except ImportError:
        pass
    return deps
