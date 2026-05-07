#!/usr/bin/env python3
"""Generate CIOS login background — dark gradient with centered logo."""

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
    """Generate dark background with subtle teal center glow and red accents on corners."""
    bg_top = (8, 10, 12)        # quase preto, levemente frio
    bg_bottom = (12, 14, 18)    # escuro com toque azulado
    glow_color = (30, 180, 160) # teal/ciano sutil (complementa o logo)
    red_accent = (180, 30, 40)  # vermelho escuro nos cantos

    cx, cy = width // 2, int(height * 0.45)
    max_radius = width * 0.45

    pixels = []
    for y in range(height):
        row = b"\x00"
        t = y / height

        br = int(bg_top[0] + (bg_bottom[0] - bg_top[0]) * t)
        bg = int(bg_top[1] + (bg_bottom[1] - bg_top[1]) * t)
        bb = int(bg_top[2] + (bg_bottom[2] - bg_top[2]) * t)

        for x in range(width):
            # Teal glow no centro
            dx = (x - cx) / max_radius
            dy = (y - cy) / max_radius
            dist = math.sqrt(dx * dx + dy * dy)
            glow = max(0, math.exp(-dist * dist * 3.0)) * 0.06

            # Red accent — superior esquerdo
            dx_tl = x / width
            dy_tl = y / height
            dist_tl = math.sqrt(dx_tl * dx_tl + dy_tl * dy_tl)
            red_tl = max(0, math.exp(-dist_tl * dist_tl * 4.0)) * 0.10

            # Red accent — inferior direito
            dx_br = (width - x) / width
            dy_br = (height - y) / height
            dist_br = math.sqrt(dx_br * dx_br + dy_br * dy_br)
            red_br = max(0, math.exp(-dist_br * dist_br * 4.0)) * 0.10

            red_total = red_tl + red_br

            r = min(255, int(br + glow_color[0] * glow + red_accent[0] * red_total))
            g = min(255, int(bg + glow_color[1] * glow + red_accent[1] * red_total))
            b = min(255, int(bb + glow_color[2] * glow + red_accent[2] * red_total))

            row += struct.pack("BBB", r, g, b)

        pixels.append(row)

    return make_png(width, height, pixels)


def generate_with_logo(width: int = 1920, height: int = 1080) -> None:
    """Generate background with centered CIOS logo using Pillow."""
    try:
        from PIL import Image, ImageDraw

        out_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(out_dir, "cios_logo.png")
        bg_path = os.path.join(out_dir, "background.png")

        # Generate base gradient first
        gradient_data = generate_gradient(width, height)
        with open(bg_path, "wb") as f:
            f.write(gradient_data)

        # Open gradient as PIL image
        bg = Image.open(bg_path).convert("RGBA")

        # Open and process logo
        if os.path.exists(logo_path):
            logo = Image.open(logo_path).convert("RGBA")
            w_logo, h_logo = logo.size

            # Remove dark background using flood-fill from corners
            # This is more accurate than a global threshold
            pixels = logo.load()
            tolerance = 70  # pixels within this brightness are considered background
            visited = set()
            queue = []

            # Seed from all 4 corners + edges
            seeds = []
            for x in range(w_logo):
                seeds.append((x, 0))
                seeds.append((x, h_logo - 1))
            for y in range(h_logo):
                seeds.append((0, y))
                seeds.append((w_logo - 1, y))

            for seed in seeds:
                r, g, b, a = pixels[seed[0], seed[1]]
                brightness = (r + g + b) / 3
                if brightness < tolerance and seed not in visited:
                    queue.append(seed)
                    visited.add(seed)

            # BFS flood fill
            while queue:
                batch = queue[:5000]
                queue = queue[5000:]
                for (x, y) in batch:
                    pixels[x, y] = (0, 0, 0, 0)
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w_logo and 0 <= ny < h_logo and (nx, ny) not in visited:
                            r, g, b, a = pixels[nx, ny]
                            brightness = (r + g + b) / 3
                            if brightness < tolerance:
                                visited.add((nx, ny))
                                queue.append((nx, ny))

            # Resize maintaining aspect ratio — fit to ~30% of screen width
            target_width = int(width * 0.30)
            aspect = h_logo / w_logo
            target_height = int(target_width * aspect)
            logo = logo.resize((target_width, target_height), Image.LANCZOS)

            # Apply semi-transparency (50% opacity on visible pixels)
            logo_data = logo.getdata()
            new_data = []
            for item in logo_data:
                new_data.append((item[0], item[1], item[2], int(item[3] * 0.5)))
            logo.putdata(new_data)

            # Center logo
            x = (width - target_width) // 2
            y = (height - target_height) // 2 - int(height * 0.03)

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
