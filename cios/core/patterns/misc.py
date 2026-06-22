"""Misc patterns — greetings, explore_system, list_apps, app_launch, command_exec, theming, scheduler, vpn, firewall, trash, spreadsheet."""

from __future__ import annotations

import re
from collections.abc import Callable

from cios.core.intent_types import IntentType

RULES: list[tuple[re.Pattern, IntentType, Callable | None, float]] = [
    # --- greetings (PT + EN) — instant response, no LLM needed ---
    (
        re.compile(
            r"^(?:ol[aá]|oi|hey|hi|hello|e\s*a[ií]?|fala|salve|bom\s+dia|boa\s+(?:tarde|noite)|good\s+(?:morning|afternoon|evening))"
            r"(?:\s+(?:cios|cio|sistema|system|ai|ia|tudo\s+bem|como\s+vai))?[!?.,]*$",
            re.IGNORECASE,
        ),
        IntentType.EXPLORE_SYSTEM,
        None,
        0.95,
    ),
    # --- explore system (PT + EN) — MUST be before app_launch ---
    (
        re.compile(
            r"(?:o\s+que\s+(?:voc[eê]|tu|vc)\s+(?:faz|pode|sabe|consegue)|"
            r"(?:quais?|que)\s+(?:s[aã]o\s+)?(?:suas?\s+)?(?:capacidades?|habilidades?|fun[cç][oõ]es?|comandos?)|"
            r"me\s+ajud[ae]|ajuda|help(?:\s+me)?|"
            r"o\s+que\s+(?:eu\s+)?posso\s+(?:fazer|pedir)|"
            r"(?:como|what)\s+(?:voc[eê]|you)\s+(?:funciona|work)|"
            r"o\s+que\s+(?:d[aá]\s+pra|posso)\s+fazer\s+(?:aqui|com\s+voc[eê]))",
            re.IGNORECASE,
        ),
        IntentType.EXPLORE_SYSTEM,
        lambda m: {"action": "list"},
        0.95,
    ),
    (
        re.compile(
            r"(?:what\s+can\s+you\s+do|show\s+(?:me\s+)?(?:your\s+)?(?:capabilities|features|skills|commands)|"
            r"how\s+do\s+(?:you|I)\s+use\s+(?:this|cios)|"
            r"what\s+(?:are\s+)?(?:your\s+)?(?:capabilities|features|skills))",
            re.IGNORECASE,
        ),
        IntentType.EXPLORE_SYSTEM,
        lambda m: {"action": "list"},
        0.95,
    ),
    # --- list apps (PT + EN) — MUST be before app_launch ---
    (
        re.compile(
            r"(?:quais?|que)\s+(?:apps?|aplicativos?|programas?)\s+(?:eu\s+)?(?:tenho|t[aá]\s+instalad|est[aã]o\s+instalad)",
            re.IGNORECASE,
        ),
        IntentType.LIST_APPS,
        None,
        0.95,
    ),
    (
        re.compile(
            r"(?:listar?|mostrar?|ver)\s+(?:os?\s+|meus?\s+)?(?:apps?|aplicativos?|programas?)\s*(?:instalados?)?",
            re.IGNORECASE,
        ),
        IntentType.LIST_APPS,
        None,
        0.90,
    ),
    (
        re.compile(
            r"(?:list|show|what)\s+(?:my\s+)?(?:installed\s+)?(?:apps?|applications?|programs?)",
            re.IGNORECASE,
        ),
        IntentType.LIST_APPS,
        None,
        0.90,
    ),
    # --- spreadsheet (PT + EN) — read, search, update spreadsheets ---
    (
        re.compile(
            r"(?:busque?|procure?|abr[ae]|leia|veja|mostre?|cheque?)\s+(?:a\s+|na\s+)?(?:planilha|spreadsheet|tabela)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.SPREADSHEET,
        lambda m: {"query": m.group(1).strip(), "action": "read"},
        0.95,
    ),
    (
        re.compile(
            r"(?:atualize?|altere?|mude?|corrija|edite?|troque?)\s+(?:o\s+|a\s+|na\s+)?(?:planilha|spreadsheet|tabela|valor)\s*(?:d[aeo]\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.SPREADSHEET,
        lambda m: {"query": m.group(1).strip(), "action": "update"},
        0.95,
    ),
    (
        re.compile(
            r"(?:quanto|qual|quais)\s+.*(?:planilha|spreadsheet|tabela)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.SPREADSHEET,
        lambda m: {"query": m.group(1).strip(), "action": "query"},
        0.90,
    ),
    (
        re.compile(
            r"(?:na\s+)?planilha\s+(.+?)(?:,|\s+)(?:quanto|qual|tem|has|what|how)",
            re.IGNORECASE,
        ),
        IntentType.SPREADSHEET,
        lambda m: {"query": m.group(1).strip(), "action": "query"},
        0.90,
    ),
    (
        re.compile(
            r"(?:find|search|open|read|check|look\s+at)\s+(?:the\s+)?(?:spreadsheet|sheet)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.SPREADSHEET,
        lambda m: {"query": m.group(1).strip(), "action": "read"},
        0.95,
    ),
    (
        re.compile(
            r"(?:update|change|modify|correct|edit|fix)\s+(?:the\s+)?(?:spreadsheet|sheet|value\s+in)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.SPREADSHEET,
        lambda m: {"query": m.group(1).strip(), "action": "update"},
        0.95,
    ),
    # --- app launcher (PT + EN) ---
    (
        re.compile(
            r"(?:abr[aei]r?|open|launch|iniciar?|inici[ea]|rodar?|rod[ea]|executar?|execut[ea]|abre|start)\s+"
            r"(?:o\s+|a\s+|the\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.APP_LAUNCH,
        lambda m: {"app": m.group(1).strip()},
        0.85,
    ),
    # --- bare app name (common apps without verb) ---
    (
        re.compile(
            r"^(firefox|chrome|google-chrome|chromium|code|vscode|terminal|nautilus|"
            r"files|spotify|vlc|gimp|inkscape|libreoffice|thunderbird|"
            r"telegram|discord|slack|steam|obs|blender|audacity|"
            r"calculator|calculadora|gedit|kate|vim|emacs|htop|"
            r"brave|edge|opera|vivaldi|filezilla|postman|insomnia)$",
            re.IGNORECASE,
        ),
        IntentType.APP_LAUNCH,
        lambda m: {"app": m.group(1).strip()},
        0.75,
    ),
    # --- direct command (EN + PT) ---
    (
        re.compile(r"^(?:run|exec(?:ute)?|rodar?|executar?)\s+(.+)$", re.IGNORECASE),
        IntentType.COMMAND_EXEC,
        lambda m: {"command": m.group(1).strip()},
        0.85,
    ),
    # --- Theming (PT + EN) ---
    (
        re.compile(
            r"(?:modo\s+)?(?:escuro|dark)\s*(?:mode)?",
            re.IGNORECASE,
        ),
        IntentType.THEMING,
        lambda m: {"action": "set", "theme": "dark"},
        0.92,
    ),
    (
        re.compile(
            r"(?:modo\s+)?(?:claro|light)\s*(?:mode)?",
            re.IGNORECASE,
        ),
        IntentType.THEMING,
        lambda m: {"action": "set", "theme": "light"},
        0.92,
    ),
    (
        re.compile(
            r"(?:trocar?|mudar?|alternar?|toggle|switch)\s+(?:o?\s+)?(?:tema|theme|modo|mode)",
            re.IGNORECASE,
        ),
        IntentType.THEMING,
        lambda m: {"action": "toggle"},
        0.90,
    ),
    # --- Scheduler / Reminders (PT + EN) ---
    (
        re.compile(
            r"(?:lembr[ae](?:-me)?|remind\s*(?:me)?|avisa(?:-me)?)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.SCHEDULER,
        lambda m: {"action": "remind", "text": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:daqui\s+a|in|em)\s+(\d+)\s*(?:min|minuto|minute|hora|hour|h)\s*(.+)?",
            re.IGNORECASE,
        ),
        IntentType.SCHEDULER,
        lambda m: {"action": "timer", "time_expr": m.group(0), "text": (m.group(2) or "").strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:às|as|at)\s+(\d{1,2}(?::\d{2})?)\s*h?\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.SCHEDULER,
        lambda m: {"action": "remind", "time_expr": m.group(0), "text": m.group(2).strip()},
        0.90,
    ),
    # --- VPN (PT + EN) ---
    (
        re.compile(
            r"(?:conect(?:ar?|e)|connect|ligar?|ativar?|enable)\s+(?:a?\s+)?(?:vpn|wireguard|openvpn)",
            re.IGNORECASE,
        ),
        IntentType.VPN,
        lambda m: {"action": "connect"},
        0.92,
    ),
    (
        re.compile(
            r"(?:desconect(?:ar?|e)|disconnect|desligar?|desativar?|disable)\s+(?:a?\s+)?(?:vpn|wireguard|openvpn)",
            re.IGNORECASE,
        ),
        IntentType.VPN,
        lambda m: {"action": "disconnect"},
        0.92,
    ),
    (
        re.compile(
            r"(?:status|estado)\s+(?:da?\s+)?(?:vpn)",
            re.IGNORECASE,
        ),
        IntentType.VPN,
        lambda m: {"action": "status"},
        0.90,
    ),
    # --- Firewall (PT + EN) ---
    (
        re.compile(
            r"(?:bloque(?:ar?|ia)|block|deny)\s+(?:a?\s+)?(?:porta|port)\s+(\d+)",
            re.IGNORECASE,
        ),
        IntentType.FIREWALL,
        lambda m: {"action": "deny", "port": int(m.group(1))},
        0.93,
    ),
    (
        re.compile(
            r"(?:liber(?:ar?|e)|allow|open)\s+(?:a?\s+)?(?:porta|port)\s+(\d+)",
            re.IGNORECASE,
        ),
        IntentType.FIREWALL,
        lambda m: {"action": "allow", "port": int(m.group(1))},
        0.93,
    ),
    (
        re.compile(
            r"(?:ativar?|enable|habilitar?)\s+(?:o?\s+)?(?:firewall|ufw)",
            re.IGNORECASE,
        ),
        IntentType.FIREWALL,
        lambda m: {"action": "enable"},
        0.92,
    ),
    (
        re.compile(
            r"(?:desativar?|disable|desabilitar?)\s+(?:o?\s+)?(?:firewall|ufw)",
            re.IGNORECASE,
        ),
        IntentType.FIREWALL,
        lambda m: {"action": "disable"},
        0.92,
    ),
    # --- Trash (PT + EN) ---
    (
        re.compile(
            r"(?:lixeira|trash|recycle\s*bin)",
            re.IGNORECASE,
        ),
        IntentType.TRASH,
        lambda m: {"action": "list"},
        0.88,
    ),
    (
        re.compile(
            r"(?:esvaziar?|empty|limpar?)\s+(?:a?\s+)?(?:lixeira|trash)",
            re.IGNORECASE,
        ),
        IntentType.TRASH,
        lambda m: {"action": "empty"},
        0.92,
    ),
    (
        re.compile(
            r"(?:restaurar?|restore|recuperar?)\s+(.+?)(?:\s+da\s+lixeira|\s+from\s+trash)?$",
            re.IGNORECASE,
        ),
        IntentType.TRASH,
        lambda m: {"action": "restore", "name": m.group(1).strip()},
        0.90,
    ),
]
