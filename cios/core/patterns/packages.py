"""Package management and self-update patterns."""

from __future__ import annotations

import re

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, callable | None, float]] = [
    # --- package management (PT + EN) ---
    (
        re.compile(
            r"(?:instalar?|instal[ea]|install)\s+(?:o\s+|a\s+)?(?:pacote\s+|package\s+)?(.+?)(?:\s+(?:para|pra|por favor|please).*)?$",
            re.IGNORECASE,
        ),
        IntentType.PACKAGE,
        lambda m: {"action": "install", "package": m.group(1).strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:remover?|desinstalar?|remove|uninstall)\s+(?:o\s+)?(?:pacote\s+|package\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.PACKAGE,
        lambda m: {"action": "remove", "package": m.group(1).strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:buscar?|procurar?|search|find)\s+(?:o\s+)?(?:pacote|package)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.PACKAGE,
        lambda m: {"action": "search", "package": m.group(1).strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:atualizar?|update)\s+(?:os\s+)?(?:pacotes|packages|sistema|system|apt)",
            re.IGNORECASE,
        ),
        IntentType.PACKAGE,
        lambda m: {"action": "update"},
        0.90,
    ),
    (
        re.compile(
            r"(?:upgrade|upgradar?)\s*(?:os\s+)?(?:pacotes|packages|sistema|system|tudo|all)?",
            re.IGNORECASE,
        ),
        IntentType.PACKAGE,
        lambda m: {"action": "upgrade"},
        0.90,
    ),
    (
        re.compile(
            r"(?:apt\s+install|sudo\s+apt\s+install)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.PACKAGE,
        lambda m: {"action": "install", "package": m.group(1).strip()},
        0.95,
    ),
    # --- self update (PT + EN) ---
    (
        re.compile(
            r"(?:atualizar?|update|upgrade)\s+(?:o\s+)?(?:cios|sistema|system)",
            re.IGNORECASE,
        ),
        IntentType.SELF_UPDATE,
        lambda m: {"action": "update"},
        0.95,
    ),
    (
        re.compile(
            r"(?:tem|has|have|existe|there)\s+(?:alguma?\s+)?(?:atualiza[cç][aã]o|update|nova\s+vers[aã]o|new\s+version)",
            re.IGNORECASE,
        ),
        IntentType.SELF_UPDATE,
        lambda m: {"action": "check"},
        0.90,
    ),
    (
        re.compile(
            r"(?:verificar?|check|checar?)\s+(?:se\s+tem\s+)?(?:atualiza[cç][aãõ]|update|vers[aã]o\s+nova)",
            re.IGNORECASE,
        ),
        IntentType.SELF_UPDATE,
        lambda m: {"action": "check"},
        0.90,
    ),
    (
        re.compile(
            r"(?:check\s+for\s+updates?|any\s+updates?|new\s+version\s+available)",
            re.IGNORECASE,
        ),
        IntentType.SELF_UPDATE,
        lambda m: {"action": "check"},
        0.90,
    ),
    (
        re.compile(
            r"(?:qual|what)\s+(?:é\s+)?(?:a\s+)?(?:minha\s+|my\s+)?(?:vers[aã]o|version)",
            re.IGNORECASE,
        ),
        IntentType.SELF_UPDATE,
        lambda m: {"action": "version"},
        0.90,
    ),
]
