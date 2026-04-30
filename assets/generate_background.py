#!/usr/bin/env python3
"""Generate Symbiont login background — dark gradient with purple glow."""

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


def generate(width: int = 1920, height: int = 1080) -> bytes:
    """Generate dark background with subtle purple radial glow."""
    # Colors
    bg_top = (11, 15, 20)       # #0b0f14
    bg_bottom = (17, 24, 39)    # #111827
    glow_color = (124, 58, 237) # #7c3aed (purple accent)

    cx, cy = width // 2, int(height * 0.45)  # glow center (slightly above middle)
    max_radius = width * 0.4

    pixels = []
    for y in range(height):
        row = b"\x00"  # PNG filter byte
        t = y / height

        # Base gradient (top to bottom)
        br = int(bg_top[0] + (bg_bottom[0] - bg_top[0]) * t)
        bg = int(bg_top[1] + (bg_bottom[1] - bg_top[1]) * t)
        bb = int(bg_top[2] + (bg_bottom[2] - bg_top[2]) * t)

        for x in range(width):
            # Distance from glow center
            dx = (x - cx) / max_radius
            dy = (y - cy) / max_radius
            dist = math.sqrt(dx * dx + dy * dy)

            # Glow intensity (gaussian falloff)
            glow = max(0, math.exp(-dist * dist * 2.5)) * 0.12

            r = min(255, int(br + glow_color[0] * glow))
            g = min(255, int(bg + glow_color[1] * glow))
            b = min(255, int(bb + glow_color[2] * glow))

            row += struct.pack("BBB", r, g, b)

        pixels.append(row)

    return make_png(width, height, pixels)


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(out_dir, "background.png")
    data = generate()
    with open(path, "wb") as f:
        f.write(data)
    print(f"Generated: {path} ({len(data)} bytes)")
