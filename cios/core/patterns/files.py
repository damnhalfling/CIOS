"""File patterns — files_search, files_open, disk_analysis, file_organize, file_ops."""

from __future__ import annotations

import re

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, callable | None, float]] = [
    # --- files search (PT + EN) — MUST be before app_launch ---
    (
        re.compile(
            r"(?:onde|where)\s+(?:est[aá]|t[aá]|is|are)\s+(?:o\s+|a\s+|os\s+|as\s+|my\s+|the\s+)?(?:arquivo|file|documento|document)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.FILES_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:encontrar?|achar?|find|locate|buscar?|procurar?)\s+(?:o\s+|a\s+|os\s+|as\s+|my\s+|the\s+)?"
            r"(?:arquivo|file|documento|document)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.FILES_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:onde|where)\s+(?:est[aá]|t[aá]|is)\s+(?:o\s+|a\s+|my\s+|the\s+)?(.+?\.\w{2,5})\b",
            re.IGNORECASE,
        ),
        IntentType.FILES_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.85,
    ),
    (
        re.compile(
            r"(?:onde|where)\s+(?:est[aá]|t[aá]|is)\s+(?:o\s+|a\s+|my\s+|the\s+)?(.+?)(?:\?|$)",
            re.IGNORECASE,
        ),
        IntentType.FILES_SEARCH,
        lambda m: {"query": m.group(1).strip().rstrip("?")},
        0.80,
    ),
    # --- files open (PT + EN) — MUST be before generic app_launch ---
    (
        re.compile(
            r"(?:abr[aei]r?|open)\s+(?:o\s+|a\s+|the\s+|my\s+)?(?:arquivo|file|documento|document)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.FILES_OPEN,
        lambda m: {"query": m.group(1).strip()},
        0.90,
    ),
    # --- disk analysis (EN + PT) — must be before file_organize ---
    (
        re.compile(
            r"(?:free|liberar?|limpar?)\s+(?:up\s+)?(?:disk\s+)?(?:espa[cç]o|space|disco|storage)",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "analyze"},
        0.95,
    ),
    (
        re.compile(
            r"(?:disco|disk|storage|armazenamento)\s+(?:cheio|full|lotado)",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "analyze"},
        0.95,
    ),
    (
        re.compile(
            r"(?:quanto|how\s+much)\s+(?:de\s+)?(?:espa[cç]o|space|disco)",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "analyze"},
        0.90,
    ),
    (
        re.compile(
            r"(?:o\s+que|what)\s+(?:t[aá]|is)\s+(?:ocupando|eating|using)\s+(?:meu\s+)?(?:disco|disk|espa[cç]o|space)",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "analyze"},
        0.90,
    ),
    (
        re.compile(
            r"(?:limpar?|clean|esvaziar?)\s+(?:o\s+|a\s+)?(?:cache|lixeira|trash|tempor[aá]rios|temp\s*files?)",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "clean"},
        0.95,
    ),
    (
        re.compile(
            r"(?:meu\s+)?(?:disco|disk|ssd|hd)\s+(?:est[aá]|t[aá]|is)\s+(?:com\s+)?\d+\s*%?\s*(?:de\s+)?(?:uso)?",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "analyze"},
        0.95,
    ),
    (
        re.compile(
            r"(?:analis[ae]r?|avaliar?|verificar?|checar?|check)\s+(?:o\s+)?(?:disco|disk|ssd|hd|armazenamento|storage|uso\s+d[eo]\s+disco)",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "analyze"},
        0.95,
    ),
    (
        re.compile(
            r"(?:uso|utiliza[cç][aã]o|consumo)\s+(?:do?\s+)?(?:disco|disk|ssd|hd|armazenamento|storage)",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "analyze"},
        0.90,
    ),
    (
        re.compile(
            r"(?:disco|disk|ssd|hd)\s+(?:com\s+)?\d+\s*%?\s*(?:de\s+)?(?:uso|ocupa[cç][aã]o|cheio|full)",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "analyze"},
        0.95,
    ),
    (
        re.compile(
            r"(?:meu\s+)?(?:disco|disk|ssd|hd)\s+.{0,20}(?:avali[ae]|analis[ae]|verifi(?:que|car))",
            re.IGNORECASE,
        ),
        IntentType.DISK_ANALYSIS,
        lambda m: {"action": "analyze"},
        0.90,
    ),
    # --- file organize (EN) ---
    (
        re.compile(
            r"(?:organize|clean|sort|tidy)\s+(?:my\s+)?(?:the\s+)?"
            r"(downloads?|desktop|documents?|files?|folder|home|pictures?)",
            re.IGNORECASE,
        ),
        IntentType.FILE_ORGANIZE,
        lambda m: {"target": m.group(1).lower()},
        0.95,
    ),
    (
        re.compile(
            r"(?:organize|clean|sort|tidy)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.FILE_ORGANIZE,
        lambda m: {"target": m.group(1).strip()},
        0.80,
    ),
    # --- file organize (PT) ---
    (
        re.compile(
            r"(?:organizar?|limpar?|arrumar?|ordenar?)\s+(?:os?\s+|meus?\s+|minhas?\s+|a\s+|as\s+)?"
            r"(downloads?|[aá]rea\s+de\s+trabalho|desktop|documentos?|arquivos?|pasta|fotos?|imagens?)",
            re.IGNORECASE,
        ),
        IntentType.FILE_ORGANIZE,
        lambda m: {"target": m.group(1).lower()},
        0.95,
    ),
    # --- file operations (PT + EN) — MUST be before app_launch ---
    (
        re.compile(
            r"(?:cri(?:ar?|e)|criar?|create|mkdir)\s+(?:uma?\s+)?(?:pasta|diret[oó]rio|folder|directory)\s+(.+?)(?:\s+(?:para|pra|por favor).*)?$",
            re.IGNORECASE,
        ),
        IntentType.FILE_OPS,
        lambda m: {"action": "mkdir", "path": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:cri(?:ar?|e)|criar?)\s+(?:uma?\s+)?(?:pasta|folder)\s+(?:para|pro|do|chamad[ao])\s+(.+?)$",
            re.IGNORECASE,
        ),
        IntentType.FILE_OPS,
        lambda m: {"action": "mkdir", "path": m.group(1).strip()},
        0.95,
    ),
]
