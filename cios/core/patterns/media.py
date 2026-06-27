"""Media patterns — intent_media, media_play, media_control."""

from __future__ import annotations

import re
from collections.abc import Callable

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, Callable | None, float]] = [
    # --- intent media (PT + EN) — MUST be before app_launch ---
    # Gallery / inline media (photos, videos, music)
    (
        re.compile(
            r"(?:mostr[ae]|show|abr[aie]r?|open)\s+(?:as\s+|my\s+|minhas?\s+)?(?:fotos?|imagens?|photos?|pictures?|images?)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "image", "action": "gallery"},
        0.95,
    ),
    (
        re.compile(
            r"(?:mostr[ae]|show|abr[aie]r?|open)\s+(?:os\s+|my\s+|meus?\s+)?(?:v[ií]deos?|videos?)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "video", "action": "gallery"},
        0.95,
    ),
    (
        re.compile(
            r"(?:mostr[ae]|show|abr[aie]r?|open)\s+(?:as\s+|my\s+|minhas?\s+)?(?:m[uú]sicas?|music)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "audio", "action": "gallery"},
        0.95,
    ),
    (
        re.compile(
            r"(?:tocar?|play|reproduzir?)\s+(?:uma?\s+|a\s+)?(?:m[uú]sica|music|song)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "audio", "action": "play"},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?)\s+(?:do\s+|from\s+)?(?:pendrive|usb|cartão|card|sd)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "image", "action": "gallery", "source": "usb"},
        0.95,
    ),
    (
        re.compile(
            r"(?:parar?|stop)\s+(?:a\s+)?(?:m[uú]sica|reprodu[cç][aã]o|music|playback)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "audio", "action": "stop"},
        0.95,
    ),
    # Watch/listen intents (open player)
    (
        re.compile(
            r"(?:quero|vou|preciso)\s+(?:assistir|ver|watch)\s+(?:um?\s+)?(?:v[ií]deo|filme|s[eé]rie|video|movie|show)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "video"},
        0.95,
    ),
    (
        re.compile(
            r"(?:quero|vou|preciso)\s+(?:ouvir|escutar|listen\s+to)\s+(?:uma?\s+)?(?:m[uú]sica|music|song|podcast)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "audio"},
        0.95,
    ),
    (
        re.compile(
            r"(?:I\s+want\s+to|let\s*(?:'s|me))\s+(?:watch|see)\s+(?:a\s+)?(?:video|movie|show|film|series)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "video"},
        0.95,
    ),
    (
        re.compile(
            r"(?:I\s+want\s+to|let\s*(?:'s|me))\s+(?:listen\s+to|hear)\s+(?:some\s+)?(?:music|a\s+song|a\s+podcast)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_MEDIA,
        lambda m: {"media_type": "audio"},
        0.95,
    ),
    # --- Media Play (PT + EN) — tocar música/vídeo ---
    (
        re.compile(
            r"(?:toc(?:ar?|a|e)|play|reproduz(?:ir?|a))\s+(?:um(?:a)?\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_PLAY,
        lambda m: {"query": m.group(1).strip()},
        0.93,
    ),
    (
        re.compile(
            r"(?:quero|estou\s+(?:a\s*fim|afim)|vou|bora)\s+(?:de\s+)?(?:ouvir|escutar|curtir)\s+(?:um(?:a)?\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_PLAY,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:bot[ae]r?|coloc(?:ar?|a)|p[oõ]e)\s+(?:um(?:a)?\s+)?(.+?)(?:\s+(?:pra|para|enquanto).*)?$",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_PLAY,
        lambda m: {"query": m.group(1).strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:ouvir|escutar|listen(?:\s+to)?)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_PLAY,
        lambda m: {"query": m.group(1).strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:i\s+wanna|i\s+want\s+to|i(?:'d|\s+would)\s+like\s+to)\s+"
            r"(?:hear|listen\s+to|play)\s+(?:some\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_PLAY,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:coloca|bota|põe)\s+(?:uma?\s+)?(?:m[uú]sica|song|music)(?:\s+(.+))?",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_PLAY,
        lambda m: {"query": (m.group(1) or "music").strip()},
        0.92,
    ),
    # --- Media Control (PT + EN) — controles de reprodução ---
    (
        re.compile(
            r"^(?:para(?:r|u)?|stop|pare)(?:\s+(?:a\s+)?(?:m[uú]sica|music|reprodu[cç][aã]o|playback|v[ií]deo))?$",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_CONTROL,
        lambda m: {"action": "stop"},
        0.95,
    ),
    (
        re.compile(
            r"^(?:paus[ae]r?|pause)(?:\s+(?:a\s+)?(?:m[uú]sica|music|reprodu[cç][aã]o))?$",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_CONTROL,
        lambda m: {"action": "toggle"},
        0.95,
    ),
    (
        re.compile(
            r"^(?:continu(?:ar?|e)|resume|despausa|unpause|volta(?:r)?)$",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_CONTROL,
        lambda m: {"action": "toggle"},
        0.93,
    ),
    (
        re.compile(
            r"^(?:pr[oó]xim[ao]|next|skip|pula|avan[cç]a)(?:\s+(?:m[uú]sica|track|faixa))?$",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_CONTROL,
        lambda m: {"action": "next"},
        0.95,
    ),
    (
        re.compile(
            r"^(?:anterior|prev(?:ious)?|volta(?:r)?(?:\s+(?:a\s+)?(?:m[uú]sica|track|faixa)))$",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_CONTROL,
        lambda m: {"action": "prev"},
        0.93,
    ),
    (
        re.compile(
            r"(?:tela\s+cheia|fullscreen|expande?|maximiz[ae]r?)\s*(?:(?:o\s+)?(?:v[ií]deo|player|media))?",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_CONTROL,
        lambda m: {"action": "fullscreen"},
        0.90,
    ),
    (
        re.compile(
            r"(?:volume|vol)\s+(\d+)",
            re.IGNORECASE,
        ),
        IntentType.MEDIA_CONTROL,
        lambda m: {"action": "volume", "volume": int(m.group(1))},
        0.93,
    ),
]
