"""Network/WiFi patterns."""

from __future__ import annotations

import re

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, callable | None, float]] = [
    # --- network / wifi (PT + EN) ---
    (
        re.compile(
            r"(?:conectar?|connect)\s+(?:no\s+|na\s+|ao\s+|to\s+|(?:na\s+)?rede\s+)?"
            r"(?:wifi|wi-fi|rede|network)\s*(?:(.+?)(?:\s+(?:com\s+)?senha\s+(.+))?)?$",
            re.IGNORECASE,
        ),
        IntentType.NETWORK,
        lambda m: {
            "action": "connect",
            "ssid": (m.group(1) or "").strip(),
            "password": (m.group(2) or "").strip(),
        },
        0.95,
    ),
    (
        re.compile(
            r"(?:conectar?|connect)\s+(?:no|na|ao|to)\s+(.+?)(?:\s+(?:com\s+)?senha\s+(.+))?$",
            re.IGNORECASE,
        ),
        IntentType.NETWORK,
        lambda m: {
            "action": "connect",
            "ssid": m.group(1).strip(),
            "password": (m.group(2) or "").strip(),
        },
        0.85,
    ),
    (
        re.compile(
            r"(?:desconectar|disconnect|desligar)\s+(?:do\s+|from\s+)?(?:wifi|wi-fi|rede|network)",
            re.IGNORECASE,
        ),
        IntentType.NETWORK,
        lambda m: {"action": "disconnect"},
        0.95,
    ),
    (
        re.compile(
            r"(?:listar?|mostrar?|show|list|ver|quais)\s+(?:as\s+)?(?:redes|networks?|wifi|wi-fi)",
            re.IGNORECASE,
        ),
        IntentType.NETWORK,
        lambda m: {"action": "list"},
        0.95,
    ),
    (
        re.compile(
            r"(?:qual|which|what)\s+(?:é\s+)?(?:minha\s+|my\s+)?(?:rede|network|wifi|wi-fi|internet)",
            re.IGNORECASE,
        ),
        IntentType.NETWORK,
        lambda m: {"action": "status"},
        0.90,
    ),
    (
        re.compile(
            r"(?:t[oô]|estou|est[aá])\s+(?:sem\s+)?(?:internet|wifi|wi-fi|rede|conectado)",
            re.IGNORECASE,
        ),
        IntentType.NETWORK,
        lambda m: {"action": "status"},
        0.85,
    ),
    (
        re.compile(
            r"(?:(?:qual|meu|ver|mostrar?|show)\s+)?(?:ip|endere[cç]o\s+ip|ip\s+(?:da\s+)?(?:m[aá]quina|rede|local))",
            re.IGNORECASE,
        ),
        IntentType.NETWORK,
        lambda m: {"action": "status"},
        0.90,
    ),
]
