"""Intent parser — converts natural language to structured intents.

Uses pattern matching first (fast, no LLM needed), falls back to LLM for
ambiguous inputs.
"""

from __future__ import annotations

import re

# Re-export for backward compatibility — all external code imports from here.
from cios.core.intent_types import Intent, IntentType, _normalize_position  # noqa: F401

# ═══════════════════════════════════════════════════════════════════════════
#  CONTEXT VALIDATION — prevents false positives from regex matches
# ═══════════════════════════════════════════════════════════════════════════

# For each intent type prone to false positives, define context words that
# MUST appear as whole words in the input to confirm the intent.
# At least ONE context word must be present for the match to be accepted.
# Intents NOT in this dict are always trusted (their patterns are specific enough).
_CONTEXT_WORDS: dict[IntentType, set[str]] = {
    IntentType.AUDIO: {
        "volume",
        "som",
        "áudio",
        "audio",
        "música",
        "musica",
        "music",
        "alto",
        "baixo",
        "mudo",
        "mute",
        "speaker",
        "caixa",
        "fone",
        "headphone",
        "sound",
        "alto-falante",
        "silenciar",
    },
    IntentType.APP_LAUNCH: {
        "abra",
        "abre",
        "abrir",
        "open",
        "launch",
        "inicia",
        "iniciar",
        "inicializar",
        "roda",
        "rodar",
        "executa",
        "executar",
        "start",
        "abrindo",
        "programa",
        "aplicativo",
        "app",
    },
    IntentType.SESSION: {
        "desligar",
        "desliga",
        "reiniciar",
        "reinicia",
        "reboot",
        "shutdown",
        "logout",
        "sair",
        "logoff",
        "power",
        "bloquear",
        "bloqueia",
        "lock",
        "suspender",
        "suspend",
        "hibernate",
        "hibernar",
        "restart",
        "computador",
        "máquina",
        "maquina",
        "sistema",
        "pc",
        "off",
    },
    IntentType.NETWORK: {
        "wifi",
        "wi-fi",
        "rede",
        "redes",
        "network",
        "networks",
        "internet",
        "conectar",
        "conecta",
        "conectado",
        "ip",
        "dns",
        "vpn",
        "ethernet",
        "conexão",
        "conexao",
        "ssid",
        "roteador",
        "router",
        "ping",
        "listar",
        "show",
        "scan",
        "disponíveis",
        "disponiveis",
    },
    IntentType.MEDIA_PLAY: {
        "toca",
        "tocar",
        "play",
        "reproduzir",
        "reproduza",
        "música",
        "musica",
        "music",
        "song",
        "playlist",
        "ouvir",
        "escutar",
        "coloca",
        "bota",
    },
    IntentType.MEDIA_CONTROL: {
        "próxima",
        "proxima",
        "next",
        "anterior",
        "previous",
        "prev",
        "pausa",
        "pause",
        "para",
        "stop",
        "player",
        "reprodução",
        "reproduzindo",
        "tocando",
        "playing",
        "faixa",
        "track",
    },
    IntentType.PACKAGE: {
        "instalar",
        "instala",
        "install",
        "desinstalar",
        "remover",
        "remove",
        "pacote",
        "package",
        "apt",
        "programa",
        "software",
        "deb",
        "dpkg",
        "snap",
        "flatpak",
    },
    IntentType.PROCESS_CONTROL: {
        "processo",
        "process",
        "pid",
        "kill",
        "matar",
        "mata",
        "travado",
        "travou",
        "engasgado",
        "consumindo",
        "cpu",
        "memória",
        "memoria",
        "ram",
        "porta",
        "port",
    },
    IntentType.POWER: {
        "bateria",
        "battery",
        "energia",
        "power",
        "suspender",
        "suspend",
        "hibernar",
        "brilho",
        "brightness",
        "carregar",
        "carregando",
        "desligar",
        "computador",
        "economia",
        "saving",
        "modo",
    },
    IntentType.DISK_ANALYSIS: {
        "disco",
        "disk",
        "espaço",
        "space",
        "storage",
        "armazenamento",
        "hd",
        "ssd",
        "partição",
        "partition",
        "livre",
        "free",
        "ocupado",
        "used",
        "gb",
        "tb",
        "limpar",
        "clean",
        "cache",
        "lixo",
        "tmp",
    },
    IntentType.WINDOW: {
        "janela",
        "window",
        "minimizar",
        "minimize",
        "maximizar",
        "maximize",
        "fechar",
        "close",
        "tela",
        "mover",
        "redimensionar",
        "resize",
        "lado",
        "esquerda",
        "direita",
    },
    IntentType.FILE_ORGANIZE: {
        "organizar",
        "organize",
        "mover",
        "move",
        "arquivo",
        "file",
        "pasta",
        "folder",
        "downloads",
        "documentos",
        "documents",
        "ordenar",
        "sort",
        "limpar",
        "clean",
        "arrumar",
        "área",
        "area",
        "trabalho",
        "desktop",
        "bagunça",
    },
    IntentType.CLIPBOARD: {
        "copiar",
        "colar",
        "copy",
        "paste",
        "clipboard",
        "área de transferência",
        "ctrl+c",
        "ctrl+v",
        "histórico",
    },
    IntentType.INTENT_MEDIA: {
        "foto",
        "fotos",
        "photo",
        "photos",
        "imagem",
        "imagens",
        "image",
        "vídeo",
        "video",
        "galeria",
        "gallery",
        "mídia",
        "media",
        "álbum",
        "album",
    },
    IntentType.BLUETOOTH: {
        "bluetooth",
        "bt",
        "pareamento",
        "parear",
        "pair",
        "paired",
        "pareados",
        "pareado",
        "fone",
        "headset",
        "caixa",
        "dispositivo",
        "dispositivos",
        "device",
        "devices",
        "listar",
        "mostrar",
        "show",
    },
}


def _confirms_context(text: str, intent_type: IntentType) -> bool:
    """Check if the text contains context words that confirm the intent.

    Returns True if:
    - Intent has no context validation (specific-enough patterns)
    - Intent has context words AND at least one appears as whole word in text
    """
    context_words = _CONTEXT_WORDS.get(intent_type)

    # Intents without context validation are always trusted
    if context_words is None:
        return True

    # Tokenize into whole words and check intersection
    text_lower = text.lower()
    text_words = set(re.findall(r"\b\w+\b", text_lower))

    return bool(text_words & context_words)


# Pattern rules: (compiled regex, IntentType, param extractor, confidence)
# Rules are split into domain-specific modules under cios/core/patterns/
from cios.core.patterns import RULES as _RULES  # noqa: E402


def parse_intent(user_input: str) -> Intent:
    """Parse user input into a structured Intent using pattern matching.

    Strategy:
    - Long phrases (> 8 words): skip regex entirely → UNKNOWN → escalates to LLM.
      Natural language sentences with multiple intents, context, and ambiguity
      cannot be resolved by regex. LLM understands the full sentence.
    - Short phrases (≤ 8 words): regex with context validation.
      Even for short phrases, every match is validated against context words.

    This prevents:
    - "download" triggering audio:down
    - "instale para nos" being parsed as package name "para nos"
    - Any conversational sentence being butchered by substring matching
    """
    text = user_input.strip()
    if not text:
        return Intent(type=IntentType.UNKNOWN, confidence=0.0, raw_input=text)

    words = text.split()

    # Long phrases → always escalate to LLM (regex can't handle natural language)
    if len(words) > 8:
        return Intent(
            type=IntentType.UNKNOWN,
            confidence=0.0,
            raw_input=text,
            requires_complex_reasoning=True,
        )

    # Short phrases → regex with context validation
    for pattern, intent_type, extractor, confidence in _RULES:
        match = pattern.search(text)
        if match:
            if not _confirms_context(text, intent_type):
                continue

            params = extractor(match) if extractor else {}
            return Intent(
                type=intent_type,
                confidence=confidence,
                params=params,
                raw_input=text,
            )

    # No pattern matched or all rejected by context
    return Intent(
        type=IntentType.UNKNOWN,
        confidence=0.0,
        raw_input=text,
        requires_complex_reasoning=True,
    )
