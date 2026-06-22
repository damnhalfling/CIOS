"""Google Workspace patterns — email, drive, calendar, gchat."""

from __future__ import annotations

import re

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, callable | None, float]] = [
    # --- Google Workspace: Email (PT + EN) ---
    (
        re.compile(
            r"(?:meus?\s+)?(?:email|e-mail|emails|e-mails|correio)",
            re.IGNORECASE,
        ),
        IntentType.EMAIL,
        lambda m: {"action": "search", "query": ""},
        0.90,
    ),
    (
        re.compile(
            r"(?:buscar?|procurar?|search|find)\s+(?:nos?\s+)?(?:email|e-mail|emails|e-mails)",
            re.IGNORECASE,
        ),
        IntentType.EMAIL,
        lambda m: {"action": "search", "query": ""},
        0.92,
    ),
    (
        re.compile(
            r"(?:email|e-mail|emails)\s+(?:de|do|da|from)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.EMAIL,
        lambda m: {"action": "search", "query": f"from:{m.group(1).strip()}"},
        0.93,
    ),
    (
        re.compile(
            r"(?:email|e-mail|emails)\s+(?:sobre|about)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.EMAIL,
        lambda m: {"action": "search", "query": m.group(1).strip()},
        0.93,
    ),
    (
        re.compile(
            r"(?:escrever?|redigir?|criar?|draft|write|compose)\s+(?:um?\s+)?(?:email|e-mail)",
            re.IGNORECASE,
        ),
        IntentType.EMAIL,
        lambda m: {"action": "draft"},
        0.92,
    ),
    (
        re.compile(
            r"(?:emails?\s+)?(?:não\s+lidos?|unread|novos?|new)",
            re.IGNORECASE,
        ),
        IntentType.EMAIL,
        lambda m: {"action": "search", "query": "is:unread"},
        0.88,
    ),
    # --- Google Workspace: Drive (PT + EN) ---
    (
        re.compile(
            r"(?:meus?\s+)?(?:arquivos?|files?)\s+(?:no\s+)?(?:drive|google\s*drive)",
            re.IGNORECASE,
        ),
        IntentType.DRIVE,
        lambda m: {"action": "search", "query": ""},
        0.90,
    ),
    (
        re.compile(
            r"(?:buscar?|procurar?|search|find)\s+(?:no\s+)?(?:drive|google\s*drive)\s*(.+)?",
            re.IGNORECASE,
        ),
        IntentType.DRIVE,
        lambda m: {"action": "search", "query": (m.group(1) or "").strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:abrir?|open|ver|see)\s+(?:o?\s+)?(?:documento|doc|arquivo|file)\s+(.+?)(?:\s+no\s+drive)?$",
            re.IGNORECASE,
        ),
        IntentType.DRIVE,
        lambda m: {"action": "search", "query": m.group(1).strip()},
        0.90,
    ),
    # --- Google Workspace: Calendar (PT + EN) ---
    (
        re.compile(
            r"(?:minha\s+)?(?:agenda|calendar|calendário|compromissos?|eventos?)",
            re.IGNORECASE,
        ),
        IntentType.CALENDAR,
        lambda m: {"action": "list"},
        0.90,
    ),
    (
        re.compile(
            r"(?:agenda|eventos?|compromissos?)\s+(?:de\s+)?(?:hoje|today|amanhã|tomorrow|semana|week)",
            re.IGNORECASE,
        ),
        IntentType.CALENDAR,
        lambda m: {
            "action": "list",
            "days": 1 if "hoje" in m.group(0).lower() or "today" in m.group(0).lower() else 7,
        },
        0.93,
    ),
    (
        re.compile(
            r"(?:criar?|create|agendar?|schedule|marcar?)\s+(?:um?\s+)?(?:evento|reunião|meeting|compromisso)",
            re.IGNORECASE,
        ),
        IntentType.CALENDAR,
        lambda m: {"action": "create"},
        0.92,
    ),
    # --- Google Workspace: Chat (PT + EN) ---
    (
        re.compile(
            r"(?:mensagens?|messages?)\s+(?:no\s+)?(?:chat|google\s*chat)",
            re.IGNORECASE,
        ),
        IntentType.GCHAT,
        lambda m: {"action": "search", "query": ""},
        0.90,
    ),
    (
        re.compile(
            r"(?:buscar?|procurar?|search)\s+(?:no\s+)?(?:chat|google\s*chat)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GCHAT,
        lambda m: {"action": "search", "query": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:enviar?|send|mandar?)\s+(?:mensagem|message)\s+(?:no\s+)?(?:chat|google\s*chat)",
            re.IGNORECASE,
        ),
        IntentType.GCHAT,
        lambda m: {"action": "send"},
        0.92,
    ),
]
