#!/usr/bin/env python3
"""Generate Harmoni login background — dark gradient with centered logo."""

import struct
import zlib
import math
import os


def make_png(width: int, height: int, pixels: list[bytes]) -> bytes:
    """Create a PNG file from raw pixel rows."""
    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw = b"".join(pixels)
    idat = chunk(b"IDAT", zlib.compress(raw, 9))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def generate_gradient(width: int = 1920, height: int = 1080) -> bytes:
    """Generate dark background with subtle purple radial glow."""
    bg_top = (11, 15, 20)       # #0b0f14
    bg_bottom = (17, 24, 39)    # #111827
    glow_color = (124, 58, 237) # #7c3aed (purple accent)

    cx, cy = width // 2, int(height * 0.45)
    max_radius = width * 0.4

    pixels = []
    for y in range(height):
        row = b"\x00"
        t = y / height

        br = int(bg_top[0] + (bg_bottom[0] - bg_top[0]) * t)
        bg = int(bg_top[1] + (bg_bottom[1] - bg_top[1]) * t)
        bb = int(bg_top[2] + (bg_bottom[2] - bg_top[2]) * t)

        for x in range(width):
            dx = (x - cx) / max_radius
            dy = (y - cy) / max_radius
            dist = math.sqrt(dx * dx + dy * dy)
            glow = max(0, math.exp(-dist * dist * 2.5)) * 0.12

            r = min(255, int(br + glow_color[0] * glow))
            g = min(255, int(bg + glow_color[1] * glow))
            b = min(255, int(bb + glow_color[2] * glow))

            row += struct.pack("BBB", r, g, b)

        pixels.append(row)

    return make_png(width, height, pixels)


def generate_with_logo(width: int = 1920, height: int = 1080) -> None:
    """Generate background with centered Harmoni logo using Pillow."""
    try:
        from PIL import Image, ImageFilter

        out_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(out_dir, "harmoni_logo.png")
        bg_path = os.path.join(out_dir, "background.png")

        # Generate base gradient first
        gradient_data = generate_gradient(width, height)
        with open(bg_path, "wb") as f:
            f.write(gradient_data)

        # Open gradient as PIL image
        bg = Image.open(bg_path).convert("RGBA")

        # Open and resize logo
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")

            # Resize logo to ~15% of screen width
            logo_size = int(width * 0.12)
            logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

            # Make logo semi-transparent (subtle, not overpowering)
            logo_data = logo.getdata()
            new_data = []
            for item in logo_data:
                # Reduce opacity to 40%
                new_data.append((item[0], item[1], item[2], int(item[3] * 0.4)))
            logo.putdata(new_data)

            # Center logo
            x = (width - logo_size) // 2
            y = (height - logo_size) // 2 - int(height * 0.05)  # slightly above center

            # Paste logo onto background
            bg.paste(logo, (x, y), logo)

        # Save as RGB PNG
        bg.convert("RGB").save(bg_path, "PNG", optimize=True)
        print(f"Generated with logo: {bg_path}")
        return

    except ImportError:
        print("Pillow not available, generating gradient-only background")


def generate_fallback(width: int = 1920, height: int = 1080) -> None:
    """Fallback: generate gradient-only background (no Pillow needed)."""
    out_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(out_dir, "background.png")
    data = generate_gradient(width, height)
    with open(path, "wb") as f:
        f.write(data)
    print(f"Generated (gradient only): {path} ({len(data)} bytes)")


if __name__ == "__main__":
    generate_with_logo()
    # If Pillow failed, check if file exists
    out_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(out_dir, "background.png")
    if not os.path.exists(path):
        generate_fallback()
