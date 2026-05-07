"""Image editing skill — basic non-destructive image operations.

Provides:
- Rotate 90° (CW/CCW)
- Flip horizontal / vertical
- Crop (with coordinates)
- Brightness / Contrast adjustment
- EXIF metadata extraction
- Share via xdg-open

All edits save to a new file (non-destructive) unless overwrite is requested.
"""

import logging
import os
import subprocess
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  EXIF METADATA (#257)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ImageMetadata:
    """Extracted image metadata."""
    width: int = 0
    height: int = 0
    format: str = ""
    file_size: int = 0
    date_taken: str = ""
    camera_make: str = ""
    camera_model: str = ""
    focal_length: str = ""
    exposure: str = ""
    iso: str = ""
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    orientation: int = 1


def get_metadata(file_path: str) -> Optional[ImageMetadata]:
    """Extract EXIF and basic metadata from an image file.

    Returns ImageMetadata or None if file cannot be read.
    """
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        img = Image.open(file_path)
        stat = os.stat(file_path)

        meta = ImageMetadata(
            width=img.width,
            height=img.height,
            format=img.format or os.path.splitext(file_path)[1].upper().lstrip("."),
            file_size=stat.st_size,
        )

        # Extract EXIF data
        exif_data = img.getexif()
        if exif_data:
            # Date taken
            date_taken = exif_data.get(36867) or exif_data.get(306)  # DateTimeOriginal or DateTime
            if date_taken:
                meta.date_taken = str(date_taken)

            # Camera
            make = exif_data.get(271)  # Make
            model = exif_data.get(272)  # Model
            if make:
                meta.camera_make = str(make).strip()
            if model:
                meta.camera_model = str(model).strip()

            # Exposure settings
            focal = exif_data.get(37386)  # FocalLength
            if focal:
                if hasattr(focal, 'numerator'):
                    meta.focal_length = f"{focal.numerator / focal.denominator:.0f}mm"
                else:
                    meta.focal_length = f"{focal}mm"

            exposure = exif_data.get(33434)  # ExposureTime
            if exposure:
                if hasattr(exposure, 'numerator') and exposure.numerator > 0:
                    if exposure.numerator == 1:
                        meta.exposure = f"1/{exposure.denominator}s"
                    else:
                        meta.exposure = f"{exposure.numerator}/{exposure.denominator}s"
                else:
                    meta.exposure = str(exposure)

            iso = exif_data.get(34855)  # ISOSpeedRatings
            if iso:
                meta.iso = f"ISO {iso}"

            # Orientation
            orientation = exif_data.get(274)  # Orientation
            if orientation:
                meta.orientation = int(orientation)

            # GPS
            gps_info = exif_data.get(34853)  # GPSInfo
            if gps_info and isinstance(gps_info, dict):
                try:
                    lat = _convert_gps(gps_info.get(2), gps_info.get(1))
                    lon = _convert_gps(gps_info.get(4), gps_info.get(3))
                    if lat is not None and lon is not None:
                        meta.gps_lat = lat
                        meta.gps_lon = lon
                except Exception:
                    pass

        img.close()
        return meta

    except Exception as e:
        logger.debug("Failed to read metadata for %s: %s", file_path, e)
        return None


def _convert_gps(coords, ref) -> Optional[float]:
    """Convert GPS coordinates from EXIF format to decimal degrees."""
    if not coords or not ref:
        return None
    try:
        degrees = float(coords[0])
        minutes = float(coords[1])
        seconds = float(coords[2])
        decimal = degrees + minutes / 60 + seconds / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except (TypeError, IndexError, ValueError):
        return None


def format_metadata(meta: ImageMetadata) -> str:
    """Format metadata into a human-readable multi-line string."""
    lines = []
    lines.append(f"{meta.width} × {meta.height} px")
    lines.append(f"{meta.format} · {_format_size(meta.file_size)}")

    if meta.date_taken:
        lines.append(f"📅 {meta.date_taken}")

    camera_parts = []
    if meta.camera_make:
        camera_parts.append(meta.camera_make)
    if meta.camera_model:
        camera_parts.append(meta.camera_model)
    if camera_parts:
        lines.append(f"📷 {' '.join(camera_parts)}")

    settings = []
    if meta.focal_length:
        settings.append(meta.focal_length)
    if meta.exposure:
        settings.append(meta.exposure)
    if meta.iso:
        settings.append(meta.iso)
    if settings:
        lines.append(" · ".join(settings))

    if meta.gps_lat is not None and meta.gps_lon is not None:
        lines.append(f"📍 {meta.gps_lat:.4f}, {meta.gps_lon:.4f}")

    return "\n".join(lines)


def _format_size(bytes_val: int) -> str:
    """Format bytes to human-readable."""
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    else:
        return f"{bytes_val / (1024 * 1024):.1f} MB"


# ═══════════════════════════════════════════════════════════════════════════
#  IMAGE EDITING (#258)
# ═══════════════════════════════════════════════════════════════════════════

def rotate_image(file_path: str, degrees: int = 90, overwrite: bool = True) -> Optional[str]:
    """Rotate an image by 90, 180, or 270 degrees.

    Args:
        file_path: Path to the image.
        degrees: Rotation angle (90=CW, -90/270=CCW, 180=flip).
        overwrite: If True, saves over original. Otherwise creates _edited copy.

    Returns:
        Path to the saved file, or None on failure.
    """
    try:
        from PIL import Image

        img = Image.open(file_path)

        # PIL rotate is counter-clockwise, so negate for CW
        if degrees == 90:
            img = img.transpose(Image.ROTATE_270)
        elif degrees == -90 or degrees == 270:
            img = img.transpose(Image.ROTATE_90)
        elif degrees == 180:
            img = img.transpose(Image.ROTATE_180)
        else:
            return None

        output_path = file_path if overwrite else _edited_path(file_path)
        img.save(output_path, quality=95)
        img.close()
        return output_path

    except Exception as e:
        logger.warning("Rotate failed for %s: %s", file_path, e)
        return None


def flip_image(file_path: str, direction: str = "horizontal", overwrite: bool = True) -> Optional[str]:
    """Flip an image horizontally or vertically.

    Args:
        file_path: Path to the image.
        direction: "horizontal" or "vertical".
        overwrite: If True, saves over original.

    Returns:
        Path to the saved file, or None on failure.
    """
    try:
        from PIL import Image

        img = Image.open(file_path)

        if direction == "horizontal":
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        elif direction == "vertical":
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        else:
            return None

        output_path = file_path if overwrite else _edited_path(file_path)
        img.save(output_path, quality=95)
        img.close()
        return output_path

    except Exception as e:
        logger.warning("Flip failed for %s: %s", file_path, e)
        return None


def crop_image(
    file_path: str,
    left: int, top: int, right: int, bottom: int,
    overwrite: bool = True,
) -> Optional[str]:
    """Crop an image to the specified rectangle.

    Args:
        file_path: Path to the image.
        left, top, right, bottom: Crop box coordinates (pixels).
        overwrite: If True, saves over original.

    Returns:
        Path to the saved file, or None on failure.
    """
    try:
        from PIL import Image

        img = Image.open(file_path)

        # Validate bounds
        w, h = img.size
        left = max(0, min(left, w))
        top = max(0, min(top, h))
        right = max(left + 1, min(right, w))
        bottom = max(top + 1, min(bottom, h))

        img = img.crop((left, top, right, bottom))

        output_path = file_path if overwrite else _edited_path(file_path)
        img.save(output_path, quality=95)
        img.close()
        return output_path

    except Exception as e:
        logger.warning("Crop failed for %s: %s", file_path, e)
        return None


def adjust_image(
    file_path: str,
    brightness: float = 1.0,
    contrast: float = 1.0,
    overwrite: bool = True,
) -> Optional[str]:
    """Adjust brightness and contrast of an image.

    Args:
        file_path: Path to the image.
        brightness: Factor (1.0 = no change, >1 = brighter, <1 = darker).
        contrast: Factor (1.0 = no change, >1 = more contrast).
        overwrite: If True, saves over original.

    Returns:
        Path to the saved file, or None on failure.
    """
    try:
        from PIL import Image, ImageEnhance

        img = Image.open(file_path)

        if brightness != 1.0:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(brightness)

        if contrast != 1.0:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(contrast)

        output_path = file_path if overwrite else _edited_path(file_path)
        img.save(output_path, quality=95)
        img.close()
        return output_path

    except Exception as e:
        logger.warning("Adjust failed for %s: %s", file_path, e)
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  SHARE (#259)
# ═══════════════════════════════════════════════════════════════════════════

def share_file(file_path: str) -> tuple[bool, str]:
    """Share a file using xdg-open (opens system share dialog).

    Returns (success, message).
    """
    if not os.path.isfile(file_path):
        return False, "Arquivo não encontrado"

    # Try xdg-email for sharing via email, fall back to xdg-open
    if shutil.which("xdg-email"):
        try:
            subprocess.Popen(
                ["xdg-email", f"--attach={file_path}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, "Abrindo email com anexo…"
        except Exception:
            pass

    # Fallback: xdg-open (opens with default app)
    if shutil.which("xdg-open"):
        try:
            subprocess.Popen(
                ["xdg-open", file_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True, "Arquivo aberto"
        except Exception as e:
            return False, f"Erro: {e}"

    return False, "xdg-open não disponível"


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _edited_path(file_path: str) -> str:
    """Generate an _edited variant of a file path."""
    stem = Path(file_path).stem
    suffix = Path(file_path).suffix
    parent = Path(file_path).parent
    return str(parent / f"{stem}_edited{suffix}")
