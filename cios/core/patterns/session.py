"""Session patterns — shutdown, reboot, suspend, hibernate, logout, lock."""

from __future__ import annotations

import re

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, callable | None, float]] = [
    # --- session control (PT + EN) ---
    (
        re.compile(
            r"(?:desligar|shutdown|power\s*off|desligue|desliga)"
            r"(?:\s+(?:o\s+)?(?:computador|pc|notebook|sistema|computer))?",
            re.IGNORECASE,
        ),
        IntentType.SESSION,
        lambda m: {"action": "shutdown"},
        0.95,
    ),
    (
        re.compile(
            r"(?:reiniciar|restart|reboot|reinicie|reinicia)"
            r"(?:\s+(?:o\s+)?(?:computador|pc|notebook|sistema|computer))?",
            re.IGNORECASE,
        ),
        IntentType.SESSION,
        lambda m: {"action": "reboot"},
        0.95,
    ),
    (
        re.compile(
            r"(?:suspender|suspend|dormir|sleep|modo\s+dormir)",
            re.IGNORECASE,
        ),
        IntentType.SESSION,
        lambda m: {"action": "suspend"},
        0.90,
    ),
    (
        re.compile(
            r"(?:hibernar|hibernate)",
            re.IGNORECASE,
        ),
        IntentType.SESSION,
        lambda m: {"action": "hibernate"},
        0.90,
    ),
    (
        re.compile(
            r"(?:sair|deslogar?|logout|log\s*out|encerrar\s+sess[aã]o|fechar\s+sess[aã]o)",
            re.IGNORECASE,
        ),
        IntentType.SESSION,
        lambda m: {"action": "logout"},
        0.90,
    ),
    (
        re.compile(
            r"(?:bloquear|lock|travar|bloqueia|trava)" r"(?:\s+(?:a\s+)?(?:tela|screen))?",
            re.IGNORECASE,
        ),
        IntentType.SESSION,
        lambda m: {"action": "lock"},
        0.90,
    ),
]
