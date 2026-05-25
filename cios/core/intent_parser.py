"""Intent parser — converts natural language to structured intents.

Uses pattern matching first (fast, no LLM needed), falls back to LLM for
ambiguous inputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class IntentType(Enum):
    DEV_START = "dev_start"
    PROCESS_CONTROL = "process_control"
    LOG_ANALYSIS = "log_analysis"
    FIX_LAST_ERROR = "fix_last_error"
    COMMAND_EXEC = "command_exec"
    STATUS = "status"
    FILE_ORGANIZE = "file_organize"
    SYSTEM_HEALTH = "system_health"
    APP_LAUNCH = "app_launch"
    SESSION = "session"
    NETWORK = "network"
    AUDIO = "audio"
    DISK_ANALYSIS = "disk_analysis"
    POWER = "power"
    PACKAGE = "package"
    CLIPBOARD = "clipboard"
    WINDOW = "window"
    BLUETOOTH = "bluetooth"
    SELF_UPDATE = "self_update"
    EXPLORE_SYSTEM = "explore_system"
    LIST_APPS = "list_apps"
    CONTINUE_PROJECT = "continue_project"
    CLOSE_PROJECT = "close_project"
    WORKFLOW_START = "workflow_start"
    INTENT_MEDIA = "intent_media"
    INTENT_BROWSE = "intent_browse"
    INTENT_WRITE = "intent_write"
    FILES_SEARCH = "files_search"
    FILES_OPEN = "files_open"
    INTELLIGENCE = "intelligence"
    GALLERY_MANAGE = "gallery_manage"
    SCREEN_CAPTURE = "screen_capture"
    HISTORY_SEARCH = "history_search"
    SPREADSHEET = "spreadsheet"
    MONITOR = "monitor"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    type: IntentType
    confidence: float  # 0.0 – 1.0
    params: dict = field(default_factory=dict)
    raw_input: str = ""
    requires_complex_reasoning: bool = False


# Pattern rules: (compiled regex, IntentType, param extractor, confidence)
_RULES: list[tuple[re.Pattern, IntentType, callable | None, float]] = [
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
    # --- bluetooth (PT + EN) — MUST be before network, session, status, package ---
    (
        re.compile(
            r"(?:conectar?|connect|parear?|pair)\s+(?:no\s+|ao\s+|com\s+|o\s+|to\s+|with\s+)?"
            r"(?:bluetooth|bt)\s*(.+)?",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "connect", "device": (m.group(1) or "").strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:conectar?|connect|parear?|pair)\s+(?:no\s+|ao\s+|com\s+|o\s+|to\s+|with\s+)?"
            r"(?:fone|headphone|headset|caixa|speaker|teclado|keyboard|mouse|controle|gamepad)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "connect", "device": m.group(0).split()[-1].strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:desconectar?|disconnect)\s+(?:do?\s+|from\s+)?(?:bluetooth|bt|fone|headphone|headset|caixa|speaker)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "disconnect", "device": ""},
        0.95,
    ),
    (
        re.compile(
            r"(?:listar?|mostrar?|show|list|ver|quais)\s+(?:os?\s+)?(?:dispositivos?|devices?)\s*"
            r"(?:bluetooth|bt|pareados?|paired|conectados?|connected)?",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "list"},
        0.90,
    ),
    (
        re.compile(
            r"(?:buscar?|scan|procurar?|search|escanear?)\s+(?:dispositivos?\s+)?(?:bluetooth|bt)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "scan"},
        0.95,
    ),
    (
        re.compile(
            r"(?:bluetooth|bt)\s+(?:scan|busca|procura)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "scan"},
        0.90,
    ),
    (
        re.compile(
            r"(?:desligar?|desativar?|turn\s*off|disable)\s+(?:o\s+)?(?:bluetooth|bt)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "power_off"},
        0.95,
    ),
    (
        re.compile(
            r"(?:ligar?|ativar?|turn\s*on|enable)\s+(?:o\s+)?(?:bluetooth|bt)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "power_on"},
        0.95,
    ),
    (
        re.compile(
            r"(?:bluetooth|bt)\s+(?:on|ligado|ativado)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "power_on"},
        0.85,
    ),
    (
        re.compile(
            r"(?:bluetooth|bt)\s+(?:off|desligado|desativado)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "power_off"},
        0.85,
    ),
    (
        re.compile(
            r"(?:remover?|remove|esquecer?|forget|desparear?|unpair)\s+(?:o?\s+)?(?:dispositivo\s+)?(?:bluetooth\s+)(.+)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "remove", "device": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:status|estado)\s+(?:do\s+)?(?:bluetooth|bt)",
            re.IGNORECASE,
        ),
        IntentType.BLUETOOTH,
        lambda m: {"action": "status"},
        0.95,
    ),
    # --- monitor configuration (PT + EN) ---
    (
        re.compile(
            r"(?:configurar?|config|ajustar?|configure|setup)\s+(?:o?\s+)?(?:monitor(?:es)?|tela(?:s)?|display(?:s)?)",
            re.IGNORECASE,
        ),
        IntentType.MONITOR,
        lambda m: {"action": "list"},
        0.95,
    ),
    (
        re.compile(
            r"(?:monitor|tela|display)\s+(?:acima|em\s*cima|above|over)",
            re.IGNORECASE,
        ),
        IntentType.MONITOR,
        lambda m: {"action": "position", "position": "above"},
        0.95,
    ),
    (
        re.compile(
            r"(?:monitor|tela|display)\s+(?:abaixo|embaixo|below|under)",
            re.IGNORECASE,
        ),
        IntentType.MONITOR,
        lambda m: {"action": "position", "position": "below"},
        0.95,
    ),
    (
        re.compile(
            r"(?:monitor|tela|display)\s+(?:(?:[àa]\s*)?(?:esquerda|left))",
            re.IGNORECASE,
        ),
        IntentType.MONITOR,
        lambda m: {"action": "position", "position": "left"},
        0.95,
    ),
    (
        re.compile(
            r"(?:monitor|tela|display)\s+(?:(?:[àa]\s*)?(?:direita|right)|ao\s*lado)",
            re.IGNORECASE,
        ),
        IntentType.MONITOR,
        lambda m: {"action": "position", "position": "right"},
        0.95,
    ),
    (
        re.compile(
            r"(?:espelhar?|mirror|duplicar?|mesma\s+imagem|clone)\s+(?:a?\s+)?(?:tela|monitor|display|screen)?",
            re.IGNORECASE,
        ),
        IntentType.MONITOR,
        lambda m: {"action": "mirror"},
        0.95,
    ),
    (
        re.compile(
            r"(?:quais?|quantos?|listar?|list)\s+(?:os?\s+)?(?:monitor(?:es)?|tela(?:s)?|display(?:s)?)",
            re.IGNORECASE,
        ),
        IntentType.MONITOR,
        lambda m: {"action": "list"},
        0.90,
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
    # --- gallery manage: face/people (PT + EN) — MUST be before intent_media ---
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver)\s+(?:as\s+|my\s+)?(?:(?:fotos?|photos?|imagens?|images?)\s+)?(?:por\s+pessoa|by\s+person|por\s+rosto|by\s+face)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "list_people"},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:do|da|de|of|with)\s+([A-Z\u00C0-\u024F][a-z\u00C0-\u024F]+(?:\s+[A-Z\u00C0-\u024F][a-z\u00C0-\u024F]+)?)",
            re.UNICODE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_person", "person_name": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:quem\s+(?:é|são)|who\s+(?:is|are))\s+(?:essa?|this|na\s+foto|in\s+the\s+photo)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "identify_face"},
        0.90,
    ),
    (
        re.compile(
            r"(?:escanear?|scan|detectar?|detect)\s+(?:os?\s+)?(?:rostos?|faces?|pessoas?|people)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "scan_faces"},
        0.95,
    ),
    (
        re.compile(
            r"(?:nomear?|name|chamar?|call)\s+(?:essa?\s+|this\s+)?(?:pessoa|person|rosto|face)\s+(?:de\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "name_person", "person_name": m.group(1).strip()},
        0.95,
    ),
    # --- gallery search: by date (PT + EN) — MUST be before intent_media ---
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:de|da|do|from|desta|deste|dessa|desse)\s+(ontem|hoje|yesterday|today|esta\s+semana|this\s+week|este\s+m[eê]s|this\s+month)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:desta|dessa)\s+(semana)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": "esta semana"},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:deste|desse)\s+(m[eê]s)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": "este mês"},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:de|from|do|da)\s+(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(?:de\s+)?(\d{4}))?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {
            "action": "search_date",
            "date_query": (m.group(1) + (" " + m.group(2) if m.group(2) else "")).strip(),
        },
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:de|from|do|da)\s+(\d{4})",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": m.group(1)},
        0.90,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:dos?|das?|from\s+the)\s+[uú]ltimos?\s+(\d+)\s+(?:dias?|days?)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": f"últimos {m.group(1)} dias"},
        0.95,
    ),
    (
        re.compile(
            r"(?:photos?|images?)\s+from\s+(?:the\s+)?last\s+(\d+)\s+days?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_date", "date_query": f"last {m.group(1)} days"},
        0.95,
    ),
    # --- gallery search: by content/text (PT + EN) — MUST be before intent_media ---
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:com|with|de|do|da|que\s+(?:tem|t[eê]m|have))\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_text", "text_query": m.group(1).strip()},
        0.90,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:na|no|in|at|em)\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "search_text", "text_query": m.group(1).strip()},
        0.88,
    ),
    # --- gallery manage: duplicates (PT + EN) — MUST be before intent_media ---
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver|encontrar?|find|buscar?)\s+(?:as\s+|my\s+)?(?:fotos?\s+)?(?:repetid[ao]s?|duplicad[ao]s?|duplicates?|iguais)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "find_duplicates"},
        0.95,
    ),
    (
        re.compile(
            r"(?:limpar?|clean|remover?|remove)\s+(?:as\s+)?(?:fotos?\s+)?(?:repetid[ao]s?|duplicad[ao]s?|duplicates?|iguais)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "find_duplicates"},
        0.95,
    ),
    (
        re.compile(
            r"(?:fotos?|imagens?|photos?|images?)\s+(?:repetid[ao]s?|duplicad[ao]s?|duplicates?|iguais)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "find_duplicates"},
        0.90,
    ),
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
    # --- history search (PT + EN) — MUST be before intent_browse ---
    (
        re.compile(
            r"(?:busca|procura|pesquisa)\s+(?:no\s+|em\s+|nas?\s+)?(?:histórico|historico|conversas?)\s+(?:sobre\s+|por\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:o\s+que|quando)\s+(?:eu\s+)?(?:falei|disse|pedi|fiz)\s+(?:sobre\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:search|find)\s+(?:in\s+)?(?:history|conversations?)\s+(?:about\s+|for\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:what|when)\s+did\s+I\s+(?:say|ask|do)\s+(?:about\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:meu\s+)?histórico\s+(?:de\s+|sobre\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.HISTORY_SEARCH,
        lambda m: {"query": m.group(1).strip()},
        0.90,
    ),
    # --- intent browse (PT + EN) — MUST be before app_launch ---
    # With search query (excludes "pacote/package/arquivo/file" which are other intents)
    (
        re.compile(
            r"(?:pesquis[ae]r?|googl[ae]r?)\s+(?:sobre\s+|por\s+|a?\s*)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    (
        re.compile(
            r"(?:buscar?|procurar?)\s+(?:sobre\s+|por\s+|na\s+(?:internet|web|net)\s+)?(?!pacote\b|package\b|arquivo\b|file\b|hist[oó]rico\b|conversas?\b)(.+)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        lambda m: {"query": m.group(1).strip()},
        0.88,
    ),
    (
        re.compile(
            r"(?:search|google|look\s+up)\s+(?:for\s+|about\s+)?(?!package\b|file\b|history\b|conversations?\b)(.+)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        lambda m: {"query": m.group(1).strip()},
        0.92,
    ),
    # Generic (no query)
    (
        re.compile(
            r"(?:quero|vou|preciso)\s+(?:pesquisar|buscar|procurar|navegar|search|browse)\s+(?:algo|na\s+internet|online|something)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        None,
        0.95,
    ),
    (
        re.compile(
            r"(?:I\s+want\s+to|let\s*(?:'s|me))\s+(?:search|browse|look\s+up|google)\s+(?:something|the\s+web|online)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_BROWSE,
        None,
        0.95,
    ),
    # --- intent write (PT + EN) — MUST be before app_launch ---
    (
        re.compile(
            r"(?:quero|vou|preciso)\s+(?:escrever|redigir|criar|write)\s+(?:um?\s+)?(?:documento|texto|carta|relat[oó]rio|document|text|letter|report)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_WRITE,
        lambda m: {"doc_type": "document"},
        0.95,
    ),
    (
        re.compile(
            r"(?:I\s+want\s+to|let\s*(?:'s|me))\s+(?:write|create|draft)\s+(?:a\s+)?(?:document|text|letter|report|essay)",
            re.IGNORECASE,
        ),
        IntentType.INTENT_WRITE,
        lambda m: {"doc_type": "document"},
        0.95,
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
            r"(?:verificar?|checar?|como\s+(?:t[aá]|est[aá]))\s+(?:o\s+)?(?:sistema|computador|pc|desempenho|performance)",
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
            r"(?:diminuir?|abaixar?|baixar?|lower|down|mais\s+baixo)\s*(?:o\s+)?(?:volume|som|[aá]udio)?",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "down", "delta": 10},
        0.95,
    ),
    (
        re.compile(
            r"(?:desmutar?|unmute|tirar?\s+(?:o\s+)?mute|ativar?\s+(?:o\s+)?som)",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "unmute"},
        0.95,
    ),
    (
        re.compile(
            r"(?:silenciar?|mutar?|mute|calar?|silêncio)\s*(?:o\s+)?(?:volume|som|[aá]udio|tudo)?",
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
            r"(?:qual|quanto|what|how)\s+(?:é\s+)?(?:o\s+)?(?:volume|som)",
            re.IGNORECASE,
        ),
        IntentType.AUDIO,
        lambda m: {"action": "status"},
        0.90,
    ),
    # --- screen capture (PT + EN) — MUST be before session control ---
    (
        re.compile(
            r"(?:print\s*screen|screenshot|captur[ae]r?\s+(?:a\s+)?tela|tirar?\s+(?:um?\s+)?(?:print|screenshot|foto\s+da\s+tela))",
            re.IGNORECASE,
        ),
        IntentType.SCREEN_CAPTURE,
        lambda m: {"action": "screenshot", "mode": "full"},
        0.95,
    ),
    (
        re.compile(
            r"(?:captur[ae]r?|screenshot|print)\s+(?:da?\s+)?(?:janela|window)(?:\s+ativa?)?",
            re.IGNORECASE,
        ),
        IntentType.SCREEN_CAPTURE,
        lambda m: {"action": "screenshot", "mode": "window"},
        0.95,
    ),
    (
        re.compile(
            r"(?:captur[ae]r?|screenshot|print)\s+(?:uma?\s+)?(?:[aá]rea|region|regi[aã]o|parte)",
            re.IGNORECASE,
        ),
        IntentType.SCREEN_CAPTURE,
        lambda m: {"action": "screenshot", "mode": "region"},
        0.95,
    ),
    (
        re.compile(
            r"(?:parar?|stop|finalizar?|encerrar?)\s+(?:a\s+)?(?:grava[cç][aã]o|recording|captura)",
            re.IGNORECASE,
        ),
        IntentType.SCREEN_CAPTURE,
        lambda m: {"action": "stop_recording"},
        0.95,
    ),
    (
        re.compile(
            r"(?:gravar?|record|iniciar?\s+grava[cç][aã]o|start\s+recording)\s*(?:a\s+)?(?:tela|screen|v[ií]deo)?",
            re.IGNORECASE,
        ),
        IntentType.SCREEN_CAPTURE,
        lambda m: {"action": "start_recording"},
        0.95,
    ),
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
            r"(?:sair|logout|log\s*out|encerrar\s+sess[aã]o|fechar\s+sess[aã]o)",
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
    # --- app launcher (PT + EN) ---
    (
        re.compile(
            r"(?:abr[aei]r?|open|launch|iniciar|rodar|executar|abre)\s+"
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
    # --- package management (PT + EN) ---
    (
        re.compile(
            r"(?:instalar?|install)\s+(?:o\s+)?(?:pacote\s+|package\s+)?(.+)",
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
    # --- clipboard (PT + EN) ---
    (
        re.compile(
            r"(?:hist[oó]rico|history)\s+(?:do\s+)?(?:clipboard|[aá]rea\s+de\s+transfer[eê]ncia|ctrl\+?[cv]|copiar?)",
            re.IGNORECASE,
        ),
        IntentType.CLIPBOARD,
        lambda m: {"action": "history"},
        0.90,
    ),
    (
        re.compile(
            r"(?:o\s+que|what)\s+(?:eu\s+)?(?:copiei|copied|tenho\s+copiado)",
            re.IGNORECASE,
        ),
        IntentType.CLIPBOARD,
        lambda m: {"action": "current"},
        0.90,
    ),
    (
        re.compile(
            r"(?:colar?|paste|usar?)\s+(?:o\s+)?(?:anterior|previous|[uú]ltimo|last)",
            re.IGNORECASE,
        ),
        IntentType.CLIPBOARD,
        lambda m: {"action": "paste_previous"},
        0.90,
    ),
    (
        re.compile(
            r"(?:limpar?|clear)\s+(?:o\s+)?(?:clipboard|[aá]rea\s+de\s+transfer[eê]ncia)",
            re.IGNORECASE,
        ),
        IntentType.CLIPBOARD,
        lambda m: {"action": "clear"},
        0.90,
    ),
    # --- window control (PT + EN) ---
    (
        re.compile(
            r"(?:janelas?|windows?)\s+(?:abertas?|open)",
            re.IGNORECASE,
        ),
        IntentType.WINDOW,
        lambda m: {"action": "list"},
        0.90,
    ),
    (
        re.compile(
            r"(?:focar?|focus|mudar?\s+para|switch\s+to)\s+(?:a?\s+)?(?:janela\s+(?:do?\s+)?|window\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.WINDOW,
        lambda m: {"action": "focus", "target": m.group(1).strip()},
        0.85,
    ),
    (
        re.compile(
            r"(?:fechar?|close)\s+(?:a?\s+)?(?:janela\s+(?:do?\s+)?|window\s+)?(.+)",
            re.IGNORECASE,
        ),
        IntentType.WINDOW,
        lambda m: {"action": "close", "target": m.group(1).strip()},
        0.85,
    ),
    (
        re.compile(
            r"(?:maximizar?|maximize)\s*(?:a?\s+)?(?:janela|window)?",
            re.IGNORECASE,
        ),
        IntentType.WINDOW,
        lambda m: {"action": "tile", "position": "maximize"},
        0.90,
    ),
    (
        re.compile(
            r"(?:minimizar?|minimize)\s*(?:a?\s+)?(?:janela|window)?",
            re.IGNORECASE,
        ),
        IntentType.WINDOW,
        lambda m: {"action": "tile", "position": "minimize"},
        0.90,
    ),
    (
        re.compile(
            r"(?:janela|window|tile|tela)\s+(?:para?\s+)?(?:a?\s+)?(esquerda|direita|left|right|cima|baixo|top|bottom)",
            re.IGNORECASE,
        ),
        IntentType.WINDOW,
        lambda m: {"action": "tile", "position": _normalize_position(m.group(1))},
        0.90,
    ),
    (
        re.compile(
            r"(?:trocar?|switch|mudar?)\s+(?:de\s+)?(?:desktop|[aá]rea\s+de\s+trabalho|workspace)\s*(\d+)?",
            re.IGNORECASE,
        ),
        IntentType.WINDOW,
        lambda m: {"action": "switch_desktop", "desktop": int(m.group(1)) if m.group(1) else 1},
        0.90,
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
    # --- direct command (EN + PT) ---
    (
        re.compile(r"^(?:run|exec(?:ute)?|rodar?|executar?)\s+(.+)$", re.IGNORECASE),
        IntentType.COMMAND_EXEC,
        lambda m: {"command": m.group(1).strip()},
        0.85,
    ),
    # --- gallery manage: edit actions (PT + EN) ---
    (
        re.compile(
            r"(?:girar?|rotacionar?|rotate|turn)\s+(?:a\s+)?(?:foto|imagem|image|photo)(?:\s+(?:90|180))?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "edit_rotate", "degrees": 90},
        0.95,
    ),
    (
        re.compile(
            r"(?:espelhar?|flip|inverter?)\s+(?:a\s+)?(?:foto|imagem|image|photo)(?:\s+(?:horizontal|vertical))?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "edit_flip", "direction": "horizontal"},
        0.95,
    ),
    (
        re.compile(
            r"(?:compartilhar?|share|enviar?|send)\s+(?:a?\s+)?(?:essa?\s+|this\s+)?(?:foto|imagem|image|photo|arquivo|file)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "share"},
        0.95,
    ),
    (
        re.compile(
            r"(?:info|informa[cç][oõ]es?|metadata|exif|detalhes?|details?)\s+(?:da?\s+)?(?:foto|imagem|image|photo)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "show_info"},
        0.95,
    ),
    # --- gallery manage: list favorites (PT + EN) — MUST be before toggle ---
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver|list)\s+(?:as\s+|my\s+|minhas?\s+)?(?:favorit[ao]s|favorites|starred)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "list_favorites"},
        0.95,
    ),
    # --- gallery manage: toggle favorite (PT + EN) ---
    (
        re.compile(
            r"(?:favorit[ae]r?|favorite|★)\s*(?:essa?|this|a\s+foto|the\s+photo|a\s+imagem|the\s+image)?",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "toggle_favorite"},
        0.95,
    ),
    # --- gallery manage: select mode (PT + EN) ---
    (
        re.compile(
            r"(?:selecionar?|select)\s+(?:fotos?|photos?|imagens?|images?|arquivos?|files?|tudo|all)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "select_mode"},
        0.95,
    ),
    (
        re.compile(
            r"(?:delet[ae]r?|delete|apagar?|remover?|remove|excluir?)\s+(?:essa?|this|a\s+foto|the\s+photo|a\s+imagem|the\s+image)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "delete"},
        0.95,
    ),
    (
        re.compile(
            r"(?:delet[ae]r?|delete|apagar?|remover?|remove|excluir?)\s+(?:as\s+)?(?:selecionad[ao]s?|selected)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "delete_selected"},
        0.95,
    ),
    # --- gallery manage: undo delete (PT + EN) ---
    (
        re.compile(
            r"(?:desfazer?|undo|restaurar?|restore)\s+(?:a?\s+)?(?:exclus[aã]o|dele[cç][aã]o|delete|last)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "undo_delete"},
        0.95,
    ),
    # --- gallery manage: albums (PT + EN) ---
    (
        re.compile(
            r"(?:criar?|create|novo)\s+(?:um?\s+)?[aá]lbum\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "create_album", "album_name": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver|abr[aie]r?|open)\s+(?:o\s+)?[aá]lbum\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "show_album", "album_name": m.group(1).strip()},
        0.95,
    ),
    (
        re.compile(
            r"(?:mostr[ae]r?|show|ver|list[ae]r?)\s+(?:os?\s+|meus?\s+)?[aá]lbuns",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "list_albums"},
        0.95,
    ),
    (
        re.compile(
            r"(?:adicionar?|add|colocar?|put)\s+(?:no|in|ao)\s+[aá]lbum\s+(.+)",
            re.IGNORECASE,
        ),
        IntentType.GALLERY_MANAGE,
        lambda m: {"action": "add_to_album", "album_name": m.group(1).strip()},
        0.95,
    ),
    # --- intelligence: news (PT + EN) ---
    (
        re.compile(
            r"(?:not[ií]cias|news|o\s+que\s+(?:est[aá]\s+acontecendo|aconteceu\s+(?:hoje|no\s+mundo))|"
            r"resum[ao]\s+(?:as\s+)?not[ií]cias|what(?:'s|\s+is)\s+happening|"
            r"headlines|manchetes|briefing|novidades\s+(?:do\s+dia|de\s+hoje))",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "news"},
        0.90,
    ),
    # --- intelligence: explain (PT + EN) ---
    (
        re.compile(
            r"(?:expli(?:que|ca)|explain|o\s+que\s+[eé]|what\s+is|"
            r"como\s+funciona|how\s+does|me\s+(?:explica|fala\s+sobre)|"
            r"tell\s+me\s+about|define|defina)",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "explain", "query": m.group(0)},
        0.85,
    ),
    # --- intelligence: write (PT + EN) ---
    (
        re.compile(
            r"(?:escrev[ea]|write|redigi[ra]|gera?r?|cri[ae]|create|compose|"
            r"fa[cç]a?\s+(?:um|uma)\s+(?:texto|email|mensagem|carta|post)|"
            r"draft\s+(?:a|an)\s+(?:email|message|text|letter|post))",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "write", "query": m.group(0)},
        0.85,
    ),
    # --- intelligence: summarize (PT + EN) ---
    (
        re.compile(
            r"(?:resum[aeiou]|summarize|summary|sintetiz[ae]|"
            r"fa[cç]a?\s+(?:um\s+)?resumo|give\s+me\s+a\s+summary)",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "summarize", "query": m.group(0)},
        0.88,
    ),
    # --- intelligence: translate (PT + EN) ---
    (
        re.compile(
            r"(?:traduz[aie]?|translate|tradu[cç][aã]o|"
            r"como\s+(?:se\s+)?(?:diz|fala)\s+.+\s+em\s+|"
            r"how\s+(?:do\s+you\s+)?say\s+.+\s+in\s+)",
            re.IGNORECASE,
        ),
        IntentType.INTELLIGENCE,
        lambda m: {"intent": "translate", "query": m.group(0)},
        0.88,
    ),
]


def parse_intent(user_input: str) -> Intent:
    """Parse user input into a structured Intent using pattern matching."""
    text = user_input.strip()
    if not text:
        return Intent(type=IntentType.UNKNOWN, confidence=0.0, raw_input=text)

    for pattern, intent_type, extractor, confidence in _RULES:
        match = pattern.search(text)
        if match:
            params = extractor(match) if extractor else {}
            return Intent(
                type=intent_type,
                confidence=confidence,
                params=params,
                raw_input=text,
            )

    # No pattern matched — flag for LLM routing
    return Intent(
        type=IntentType.UNKNOWN,
        confidence=0.0,
        raw_input=text,
        requires_complex_reasoning=True,
    )


def _normalize_position(pos: str) -> str:
    """Normalize position names from PT/EN to internal format."""
    mapping = {
        "esquerda": "left",
        "direita": "right",
        "cima": "top",
        "baixo": "bottom",
        "left": "left",
        "right": "right",
        "top": "top",
        "bottom": "bottom",
    }
    return mapping.get(pos.lower(), pos.lower())
