"""Dev patterns — dev_start, continue_project, close_project, workflow_start."""

from __future__ import annotations

import re
from collections.abc import Callable

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, Callable | None, float]] = [
    # --- dev_start (EN) ---
    (
        re.compile(
            r"(?:start|run|launch|boot)\s+(?:my\s+)?(?:the\s+)?"
            r"(backend|frontend|server|app|project|service|api|dev)",
            re.IGNORECASE,
        ),
        IntentType.DEV_START,
        lambda m: {"target": m.group(1).lower()},
        0.95,
    ),
    (
        re.compile(r"(?:npm|yarn|pnpm)\s+(?:run\s+)?(start|dev)", re.IGNORECASE),
        IntentType.DEV_START,
        lambda m: {"target": m.group(1).lower()},
        0.90,
    ),
    # --- dev_start (PT) ---
    (
        re.compile(
            r"(?:iniciar|rodar|subir|levantar|startar)\s+(?:o\s+|meu\s+)?"
            r"(backend|frontend|servidor|app|projeto|servi[cç]o|api)",
            re.IGNORECASE,
        ),
        IntentType.DEV_START,
        lambda m: {"target": m.group(1).lower()},
        0.95,
    ),
    # --- continue project (PT + EN) — MUST be before workflow_start and app_launch ---
    (
        re.compile(
            r"(?:continuar?)\s+(?:o\s+)?projeto\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.CONTINUE_PROJECT,
        lambda m: {"project": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:continuar?)\s+(?:no|na)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.CONTINUE_PROJECT,
        lambda m: {"project": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:voltar?)\s+(?:pro?|para?\s+o?)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.CONTINUE_PROJECT,
        lambda m: {"project": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:continue)\s+project\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.CONTINUE_PROJECT,
        lambda m: {"project": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:resume)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.CONTINUE_PROJECT,
        lambda m: {"project": m.group(1).strip()},
        0.90,
    ),
    # Bare "continuar" / "continue" — no project param
    (
        re.compile(
            r"^continuar?$",
            re.IGNORECASE,
        ),
        IntentType.CONTINUE_PROJECT,
        lambda m: {},
        0.90,
    ),
    (
        re.compile(
            r"^continue$",
            re.IGNORECASE,
        ),
        IntentType.CONTINUE_PROJECT,
        lambda m: {},
        0.90,
    ),
    # --- close project (PT + EN) — stop server, close windows ---
    (
        re.compile(
            r"(?:fecha[r]?|encerra[r]?|para[r]?|finaliza[r]?)\s+(?:o\s+)?(?:projeto|project)\s*(.+)?",
            re.IGNORECASE,
        ),
        IntentType.CLOSE_PROJECT,
        lambda m: {"project": (m.group(1) or "").strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:close|stop|shut\s*down|end)\s+(?:the\s+)?(?:project|workspace)\s*(.+)?",
            re.IGNORECASE,
        ),
        IntentType.CLOSE_PROJECT,
        lambda m: {"project": (m.group(1) or "").strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:fecha|encerra|para)\s+tudo",
            re.IGNORECASE,
        ),
        IntentType.CLOSE_PROJECT,
        lambda m: {},
        0.90,
    ),
    (
        re.compile(
            r"(?:close|stop|shut\s*down)\s+everything",
            re.IGNORECASE,
        ),
        IntentType.CLOSE_PROJECT,
        lambda m: {},
        0.90,
    ),
    (
        re.compile(
            r"(?:chega\s+por\s+hoje|encerra\s+(?:o\s+)?(?:dia|trabalho)|(?:that'?s?\s+)?enough\s+for\s+today)",
            re.IGNORECASE,
        ),
        IntentType.CLOSE_PROJECT,
        lambda m: {},
        0.85,
    ),
    # --- workflow start (PT + EN) — MUST be before app_launch and dev_start ---
    (
        re.compile(
            r"(?:quero|vou|preciso)\s+(?:trabalhar|codar|programar|desenvolver)\s+"
            r"(?:no|na|em|com)\s+(?:o?\s+)?(?:projeto\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.WORKFLOW_START,
        lambda m: {"project": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:i\s+wanna|i\s+want\s+to|let\s*(?:'s|me)|gonna|i(?:'ll|\s+will))\s+"
            r"(?:work\s+on|code|develop|hack\s+on)\s+(?:the\s+)?(?:project\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.WORKFLOW_START,
        lambda m: {"project": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:abr[aei]r?|open|start|iniciar)\s+(?:o\s+)?(?:meu\s+)?(?:workspace|ambiente)\s+"
            r"(?:do?\s+|de\s+|for\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.WORKFLOW_START,
        lambda m: {"project": m.group(1).strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:I\s+want\s+to|let\s*(?:'s|me)|gonna)\s+(?:work\s+on|code|develop)\s+(?:the\s+)?(?:project\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.WORKFLOW_START,
        lambda m: {"project": m.group(1).strip()},
        0.95,
    ),
]
