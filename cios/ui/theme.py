"""CIOS — Unified Design Tokens.

Single source of truth for all visual properties across every surface:
GUI, CLI, topbar, splash, onboarding, hotkey overlay.

Every color, spacing, timing, and font decision lives here.
Import from here — never hardcode values in UI modules.

Design language: Tron-inspired — dark, glowing edges, floating elements,
minimal borders, neon accents on deep black. No 90s dividers.
"""

import os
import time

# ═══════════════════════════════════════════════════════════════════════════
#  COLORS — Tron-inspired palette
# ═══════════════════════════════════════════════════════════════════════════

# Backgrounds (deep black → subtle elevation)
BG = "#00050d"
BG_PANEL = "#000a14"
BG_CARD = "#001020"
BG_INPUT = "#001225"
BG_HOVER = "#001a30"
BG_PRESS = "#002040"

# Borders (subtle glow, not solid lines)
BORDER = "#002040"
BORDER_LT = "#003060"

# Foreground
FG = "#e0f4ff"
FG_SEC = "#7eb8d8"
FG_DIM = "#3a6080"

# Accent (electric cyan — Tron: Legacy signature)
ACCENT = "#00e5ff"
ACCENT_LT = "#40f0ff"
ACCENT_DK = "#009db8"
ACCENT_GLOW = "rgba(0,229,255,0.25)"

# Semantic
SUCCESS = "#00e676"
SUCCESS_BG = "#001a0f"
WARNING = "#ff6d00"
ERROR = "#ff1744"
CYAN = "#00e5ff"

# State ring colors
RING_IDLE = "#00e5ff"
RING_PROCESSING = "#00b8d4"
RING_SUCCESS = "#00e676"
RING_ERROR = "#ff1744"
RING_CLOUD = "#ff6d00"


# ═══════════════════════════════════════════════════════════════════════════
#  SPACING (px)
# ═══════════════════════════════════════════════════════════════════════════

SP_MICRO = 4
SP_TIGHT = 6
SP_COMPACT = 10
SP_DEFAULT = 14
SP_SECTION = 20
SP_BLOCK = 28
SP_PAGE = 32


# ═══════════════════════════════════════════════════════════════════════════
#  TIMING (ms)
# ═══════════════════════════════════════════════════════════════════════════

T_FAST = 100
T_NORMAL = 180
T_SLOW = 300
T_STEP = 400
T_DOTS = 500
T_RING = 60  # state ring animation frame rate


# ═══════════════════════════════════════════════════════════════════════════
#  LAYOUT
# ═══════════════════════════════════════════════════════════════════════════

SIDEBAR_W = 240
RIGHT_W = 260
BAR_HEIGHT = 28


# ═══════════════════════════════════════════════════════════════════════════
#  FONTS (Tkinter family, size, weight)
# ═══════════════════════════════════════════════════════════════════════════

FONT_FAMILY = "Helvetica"
FONT_BRAND = (FONT_FAMILY, 14, "bold")
FONT_BRAND_SUB = (FONT_FAMILY, 8)
FONT_NAV = (FONT_FAMILY, 11)
FONT_NAV_BOLD = (FONT_FAMILY, 11, "bold")
FONT_GREETING = (FONT_FAMILY, 24, "bold")
FONT_SUB = (FONT_FAMILY, 13)
FONT_INPUT = (FONT_FAMILY, 16)
FONT_SECTION = (FONT_FAMILY, 11, "bold")
FONT_CARD_ICON = (FONT_FAMILY, 20)
FONT_CARD_TITLE = (FONT_FAMILY, 11, "bold")
FONT_CARD_DESC = (FONT_FAMILY, 9)
FONT_STEP = (FONT_FAMILY, 12)
FONT_RESULT_TITLE = (FONT_FAMILY, 16, "bold")
FONT_RESULT_BODY = (FONT_FAMILY, 12)
FONT_METRIC = (FONT_FAMILY, 10)
FONT_METRIC_BOLD = (FONT_FAMILY, 10, "bold")
FONT_SMALL = (FONT_FAMILY, 9)
FONT_PAGE_HEADER = (FONT_FAMILY, 20, "bold")
FONT_PAGE_SUB = (FONT_FAMILY, 11)
FONT_LIST_TITLE = (FONT_FAMILY, 11, "bold")
FONT_LIST_SUB = (FONT_FAMILY, 9)
FONT_BTN = (FONT_FAMILY, 10, "bold")
FONT_RING_SYMBOL = (FONT_FAMILY, 28)
FONT_HINT = (FONT_FAMILY, 11)


# ═══════════════════════════════════════════════════════════════════════════
#  USER CONTEXT
# ═══════════════════════════════════════════════════════════════════════════

USER = os.environ.get("USER", "user").capitalize()
HOUR = time.localtime().tm_hour
GREETING = "Bom dia" if HOUR < 12 else ("Boa tarde" if HOUR < 18 else "Boa noite")


# ═══════════════════════════════════════════════════════════════════════════
#  COLOR UTILITIES
# ═══════════════════════════════════════════════════════════════════════════


def hex2rgb(h: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb2hex(r: int, g: int, b: int) -> str:
    """Convert RGB tuple to hex color."""
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def lerp(c1: str, c2: str, t: float) -> str:
    """Linear interpolation between two hex colors."""
    r1, g1, b1 = hex2rgb(c1)
    r2, g2, b2 = hex2rgb(c2)
    return rgb2hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  CSS VARIABLES (kept for potential future use)
# ═══════════════════════════════════════════════════════════════════════════

CSS_VARS = f""":root{{
  --bg:{BG};
  --bg-panel:rgba(0,10,20,0.9);
  --bg-card:rgba(0,16,32,0.75);
  --bg-card-hover:rgba(0,26,48,0.85);
  --bg-input:rgba(0,18,37,0.9);
  --border:rgba(0,229,255,0.06);
  --border-focus:rgba(0,229,255,0.5);
  --fg:{FG};
  --fg-dim:{FG_DIM};
  --fg-muted:{FG_SEC};
  --accent:{ACCENT};
  --accent-lt:{ACCENT_LT};
  --accent-glow:{ACCENT_GLOW};
  --success:{SUCCESS};
  --warning:{WARNING};
  --error:{ERROR};
  --cyan:{CYAN};
  --radius:12px;
  --radius-lg:16px;
  --ring-idle:{RING_IDLE};
  --ring-processing:{RING_PROCESSING};
  --ring-success:{RING_SUCCESS};
  --ring-error:{RING_ERROR};
  --ring-cloud:{RING_CLOUD};
}}"""
