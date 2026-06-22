"""System patterns — fix_last_error, process_control, log_analysis, system_health, power, status."""

from __future__ import annotations

import re

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, callable | None, float]] = [
    # --- fix / recover (EN) ---
    (
        re.compile(
            r"(?:it\s+)?(?:failed|crashed|broke|errored|didn'?t work)"
            r".*(?:fix|resolve|retry|again|yesterday|last time|earlier)",
            re.IGNORECASE,
        ),
        IntentType.FIX_LAST_ERROR,
        None,
        0.90,
    ),
    (
        re.compile(r"fix\s+(?:it|that|the\s+error|the\s+issue|last)", re.IGNORECASE),
        IntentType.FIX_LAST_ERROR,
        None,
        0.90,
    ),
    # --- fix / recover (PT) ---
    (
        re.compile(
            r"(?:corrigir?|consertar?|arrumar?|resolver?)\s+(?:isso|o\s+erro|o\s+problema|o\s+[uú]ltimo)",
            re.IGNORECASE,
        ),
        IntentType.FIX_LAST_ERROR,
        None,
        0.90,
    ),
    (
        re.compile(
            r"(?:falhou|quebrou|deu\s+erro|n[aã]o\s+funcionou|travou)",
            re.IGNORECASE,
        ),
        IntentType.FIX_LAST_ERROR,
        None,
        0.85,
    ),
    # --- process control (EN) ---
    (
        re.compile(
            r"(?:kill|stop|terminate|end)\s+(?:the\s+)?(?:process|server|service)"
            r"(?:\s+(?:on|at|using)\s+(?:port\s+)?(\d+))?",
            re.IGNORECASE,
        ),
        IntentType.PROCESS_CONTROL,
        lambda m: {"action": "kill", "port": int(m.group(1)) if m.group(1) else None},
        0.95,
    ),
    (
        re.compile(
            r"(?:what(?:'s| is)\s+(?:using|on|running on))\s+port\s+(\d+)",
            re.IGNORECASE,
        ),
        IntentType.PROCESS_CONTROL,
        lambda m: {"action": "query", "port": int(m.group(1))},
        0.90,
    ),
    # --- process control (PT) ---
    (
        re.compile(
            r"(?:matar?|parar?|encerrar?|finalizar?|derrubar?)\s+(?:o\s+)?(?:processo|servidor|servi[cç]o)"
            r"(?:\s+(?:na|da|em)\s+(?:porta\s+)?(\d+))?",
            re.IGNORECASE,
        ),
        IntentType.PROCESS_CONTROL,
        lambda m: {"action": "kill", "port": int(m.group(1)) if m.group(1) else None},
        0.95,
    ),
    (
        re.compile(
            r"(?:o\s+que|quem)\s+(?:t[aá]|est[aá])\s+(?:usando|na|rodando\s+na)\s+(?:a\s+)?porta\s+(\d+)",
            re.IGNORECASE,
        ),
        IntentType.PROCESS_CONTROL,
        lambda m: {"action": "query", "port": int(m.group(1))},
        0.90,
    ),
    # --- log analysis (EN) ---
    (
        re.compile(
            r"(?:show|read|check|analyze|what happened in)\s+(?:the\s+)?(?:logs?|errors?|output)",
            re.IGNORECASE,
        ),
        IntentType.LOG_ANALYSIS,
        None,
        0.85,
    ),
    # --- log analysis (PT) ---
    (
        re.compile(
            r"(?:mostrar?|ver|checar?|analisar?|ler)\s+(?:os\s+)?(?:logs?|erros?|sa[ií]da)",
            re.IGNORECASE,
        ),
        IntentType.LOG_ANALYSIS,
        None,
        0.85,
    ),
    (
        re.compile(
            r"(?:o\s+que\s+aconteceu|o\s+que\s+deu\s+errado|quais?\s+erros?)",
            re.IGNORECASE,
        ),
        IntentType.LOG_ANALYSIS,
        None,
        0.85,
    ),
    # --- system health (EN) ---
    (
        re.compile(
            r"(?:my\s+)?(?:computer|system|machine|pc|laptop)\s+(?:is\s+)?"
            r"(?:slow|laggy|lagging|freezing|hot|overheating|unresponsive)",
            re.IGNORECASE,
        ),
        IntentType.SYSTEM_HEALTH,
        None,
        0.95,
    ),
    (
        re.compile(
            r"(?:check|show|how is)\s+(?:my\s+)?(?:system|computer|machine|pc)\s*(?:health|performance|resources)?",
            re.IGNORECASE,
        ),
        IntentType.SYSTEM_HEALTH,
        None,
        0.90,
    ),
    (
        re.compile(
            r"(?:why is (?:my |everything |it )?(?:so )?slow|what(?:'s| is) (?:using|eating) (?:my )?(?:memory|cpu|ram|resources))",
            re.IGNORECASE,
        ),
        IntentType.SYSTEM_HEALTH,
        None,
        0.90,
    ),
    # --- system health (PT) ---
    (
        re.compile(
            r"(?:meu\s+)?(?:computador|sistema|pc|notebook|note)\s+(?:t[aá]\s+|est[aá]\s+)?"
            r"(?:lento|travando|travado|quente|esquentando|pesado|lerdo|devagar)",
            re.IGNORECASE,
        ),
        IntentType.SYSTEM_HEALTH,
        None,
        0.95,
    ),
    (
        re.compile(
            r"(?:verificar?|checar?|como\s+(?:t[aá]|est[aá]))\s+(?:o\s+|meu\s+)?(?:sistema|computador|pc|desempenho|performance)",
            re.IGNORECASE,
        ),
        IntentType.SYSTEM_HEALTH,
        None,
        0.90,
    ),
    (
        re.compile(
            r"(?:por\s*que|porque)\s+(?:t[aá]|est[aá])\s+(?:t[aã]o\s+)?(?:lento|travando|pesado)",
            re.IGNORECASE,
        ),
        IntentType.SYSTEM_HEALTH,
        None,
        0.90,
    ),
    (
        re.compile(
            r"(?:t[aá]\s+lento|t[aá]\s+travando|t[aá]\s+pesado)",
            re.IGNORECASE,
        ),
        IntentType.SYSTEM_HEALTH,
        None,
        0.85,
    ),
    # --- power / battery / brightness (EN + PT) ---
    (
        re.compile(
            r"(?:quanta?|how\s+much|quanto)\s+(?:de\s+)?(?:bateria|battery|carga|charge)",
            re.IGNORECASE,
        ),
        IntentType.POWER,
        lambda m: {"action": "battery_status"},
        0.95,
    ),
    (
        re.compile(
            r"(?:status|estado)\s+(?:da\s+)?(?:bateria|battery)",
            re.IGNORECASE,
        ),
        IntentType.POWER,
        lambda m: {"action": "battery_status"},
        0.90,
    ),
    (
        re.compile(
            r"(?:aumentar?|subir?|raise|mais)\s+(?:o\s+)?(?:brilho|brightness)",
            re.IGNORECASE,
        ),
        IntentType.POWER,
        lambda m: {"action": "brightness_up", "delta": 10},
        0.95,
    ),
    (
        re.compile(
            r"(?:diminuir?|abaixar?|baixar?|lower|menos)\s+(?:o\s+)?(?:brilho|brightness)",
            re.IGNORECASE,
        ),
        IntentType.POWER,
        lambda m: {"action": "brightness_down", "delta": 10},
        0.95,
    ),
    (
        re.compile(
            r"(?:brilho|brightness)\s+(?:em\s+|a\s+|at\s+|to\s+)?(\d+)\s*%?",
            re.IGNORECASE,
        ),
        IntentType.POWER,
        lambda m: {"action": "brightness_set", "level": int(m.group(1))},
        0.95,
    ),
    (
        re.compile(
            r"(?:qual|quanto|what)\s+(?:é\s+)?(?:o\s+)?(?:brilho|brightness)",
            re.IGNORECASE,
        ),
        IntentType.POWER,
        lambda m: {"action": "brightness_status"},
        0.90,
    ),
    (
        re.compile(
            r"(?:modo\s+)?(?:economia|power\s*sav|economizar|poupar)\s*(?:de\s+)?(?:energia|battery|bateria)?",
            re.IGNORECASE,
        ),
        IntentType.POWER,
        lambda m: {"action": "power_saving"},
        0.90,
    ),
    # --- status (EN + PT) ---
    (
        re.compile(r"(?:status|what(?:'s| is) running|health)", re.IGNORECASE),
        IntentType.STATUS,
        None,
        0.90,
    ),
    (
        re.compile(
            r"(?:o\s+que\s+(?:t[aá]|est[aá])\s+rodando|servi[cç]os?\s+ativos?|quais?\s+servi[cç]os?)",
            re.IGNORECASE,
        ),
        IntentType.STATUS,
        None,
        0.90,
    ),
]
