"""Audio/volume patterns."""

from __future__ import annotations

import re
from collections.abc import Callable

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, Callable | None, float]] = [
    # --- audio / volume (PT + EN) ---
    (
        re.compile(
            r"(?:aumentar?|subir?|raise|(?<!\w)up(?!\w)|louder|mais\s+alto)\s*(?:o\s+)?(?:volume|som|[aá]udio)?",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "up", "delta": 10},
        0.95,
    ),
    (
        re.compile(
            r"(?:diminuir?|abaixar?|baixar?|lower|\bdown\b|mais\s+baixo)\s*(?:o\s+)?(?:volume|som|[aá]udio)?",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "down", "delta": 10},
        0.95,
    ),
    (
        re.compile(
            r"(?:desmutar?|unmute|(?:tirar?|retir[ae]r?|remover?)\s+(?:o\s+)?mute|ativar?\s+(?:o\s+)?som)",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "unmute"},
        0.95,
    ),
    (
        re.compile(
            r"(?:silenciar?|mutar?|(?<!\w)mute(?!\w)|calar?|silêncio)\s*(?:o\s+)?(?:volume|som|[aá]udio|tudo)?",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "mute"},
        0.95,
    ),
    (
        re.compile(
            r"(?:volume|som)\s+(?:em\s+|a\s+|at\s+|to\s+)?(\d+)\s*%?",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "set", "level": int(m.group(1))},
        0.95,
    ),
    (
        re.compile(
            r"(?:qual|quanto|what|how)\s+(?:\w+\s+){0,3}(?:volume|som)",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "status"},
        0.90,
    ),
    (
        re.compile(
            r"^(?:volume|som|áudio|audio)$",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "status"},
        0.85,
    ),
]
