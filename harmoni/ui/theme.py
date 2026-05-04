"""Harmoni OS — Unified Design Tokens.

Single source of truth for all visual properties across every surface:
GUI, CLI, topbar, splash, onboarding, hotkey overlay.

Every color, spacing, timing, and font decision lives here.
Import from here — never hardcode values in UI modules.
"""

import os
import time

# ═══════════════════════════════════════════════════════════════════════════
#  COLORS
# ═══════════════════════════════════════════════════════════════════════════

# Backgrounds (darkest → lightest)
BG = "#0b0f14"
BG_PANEL = "#0f1319"
BG_CARD = "#111827"
BG_INPUT = "#161b24"
BG_HOVER = "#1e2738"
BG_PRESS = "#252e3f"

# Borders
BORDER = "#1f2937"
BORDER_LT = "#2d3748"

# Foreground
FG = "#e5e7eb"
FG_SEC = "#9ca3af"
FG_DIM = "#6b7280"

# Accent (purple)
ACCENT = "#7c3aed"
ACCENT_LT = "#a78bfa"
ACCENT_DK = "#6d28d9"
ACCENT_GLOW = "rgba(124,111,247,0.25)"  # CSS only

# Semantic
SUCCESS = "#22c55e"
SUCCESS_BG = "#0a1a0f"
WARNING = "#eab308"
ERROR = "#ef4444"
CYAN = "#06b6d4"

# State ring colors
RING_IDLE = ACCENT_LT
RING_PROCESSING = ACCENT
RING_SUCCESS = SUCCESS
RING_ERROR = ERROR


# ═══════════════════════════════════════════════════════════════════════════
#  SPACING (px)
# ═══════════════════════════════════════════════════════════════════════════

SP_MICRO = 4
SP_TIGHT = 8
SP_COMPACT = 12
SP_DEFAULT = 16
SP_SECTION = 24
SP_BLOCK = 32
SP_PAGE = 40


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
RIGHT_W = 280
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
  --bg-panel:rgba(16,16,24,0.75);
  --bg-card:rgba(26,28,38,0.65);
  --bg-card-hover:rgba(42,47,58,0.75);
  --bg-input:rgba(22,22,32,0.8);
  --border:rgba(255,255,255,0.06);
  --border-focus:rgba(124,111,247,0.5);
  --fg:{FG};
  --fg-dim:#6b6b7b;
  --fg-muted:#8a8a9a;
  --accent:{ACCENT};
  --accent-lt:{ACCENT_LT};
  --accent-glow:{ACCENT_GLOW};
  --success:{SUCCESS};
  --warning:{WARNING};
  --error:{ERROR};
  --purple-soft:{ACCENT_LT};
  --radius:12px;
  --radius-lg:16px;
  --ring-idle:{RING_IDLE};
  --ring-processing:{RING_PROCESSING};
  --ring-success:{RING_SUCCESS};
  --ring-error:{RING_ERROR};
}}"""
