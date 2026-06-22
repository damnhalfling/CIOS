"""Peripheral patterns — bluetooth, monitor, clipboard, window, screen_capture."""

from __future__ import annotations

import re
from collections.abc import Callable

from cios.core.intent_types import IntentType, _normalize_position

RULES: list[tuple[re.Pattern, IntentType, Callable | None, float]] = [
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
            r"(?:configurar?|config|ajustar?|configure|setup|extender?|estender?)\s+(?:o?\s+)?(?:monitor(?:es)?|tela(?:s)?|display(?:s)?)",
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
    # --- screen capture (PT + EN) ---
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
]
