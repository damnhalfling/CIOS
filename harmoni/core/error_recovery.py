"""Error Recovery — every error gets a human suggestion for next action.

Rules:
1. NEVER show a raw error without a suggestion
2. Suggestions must be actionable ("Tente X" / "Quer que eu Y?")
3. Classify errors by type for targeted recovery
4. Support retry hints for transient failures

Usage:
    from harmoni.core.error_recovery import enrich_error, suggest_recovery
    
    msg = enrich_error("Connection refused", context={"intent": "network"})
    # → "Não consegui conectar. Quer ver as redes disponíveis?"
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  ERROR CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class ErrorType:
    NETWORK_CONNECT = "network_connect"
    NETWORK_NO_NETWORKS = "network_no_networks"
    NETWORK_WRONG_PASSWORD = "network_wrong_password"
    NETWORK_TIMEOUT = "network_timeout"
    PACKAGE_NOT_FOUND = "package_not_found"
    PACKAGE_INSTALL_FAILED = "package_install_failed"
    PACKAGE_DEPS = "package_deps"
    APP_NOT_FOUND = "app_not_found"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    DISK_FULL = "disk_full"
    PORT_BUSY = "port_busy"
    COMMAND_FAILED = "command_failed"
    AUDIO_UNAVAILABLE = "audio_unavailable"
    BRIGHTNESS_UNAVAILABLE = "brightness_unavailable"
    WINDOW_NOT_FOUND = "window_not_found"
    BLUETOOTH_UNAVAILABLE = "bluetooth_unavailable"
    BLUETOOTH_PAIR_FAILED = "bluetooth_pair_failed"
    GENERIC = "generic"


# Patterns → error type classification
_CLASSIFIERS: list[tuple[re.Pattern, str]] = [
    # Network
    (re.compile(r"no.*(network|wifi|wi-fi).*found", re.I), ErrorType.NETWORK_NO_NETWORKS),
    (re.compile(r"(wrong|incorrect|invalid).*(password|key|secret)", re.I), ErrorType.NETWORK_WRONG_PASSWORD),
    (re.compile(r"(connection|connect).*(refused|failed|error)", re.I), ErrorType.NETWORK_CONNECT),
    (re.compile(r"(network|wifi).*(timeout|timed out)", re.I), ErrorType.NETWORK_TIMEOUT),
    # Packages
    (re.compile(r"(unable to locate|no.*(package|candidate))", re.I), ErrorType.PACKAGE_NOT_FOUND),
    (re.compile(r"(dpkg|apt).*(error|failed|broken)", re.I), ErrorType.PACKAGE_INSTALL_FAILED),
    (re.compile(r"(unmet|dependency|depends)", re.I), ErrorType.PACKAGE_DEPS),
    # Apps
    (re.compile(r"(app|application|program).*(not found|not installed)", re.I), ErrorType.APP_NOT_FOUND),
    (re.compile(r"could not find.*(app|application)", re.I), ErrorType.APP_NOT_FOUND),
    # System
    (re.compile(r"(permission|access).*(denied|refused)", re.I), ErrorType.PERMISSION_DENIED),
    (re.compile(r"(timed? out|timeout|too long)", re.I), ErrorType.TIMEOUT),
    (re.compile(r"(no space|disk full|enospc)", re.I), ErrorType.DISK_FULL),
    (re.compile(r"(port|address).*(in use|busy|eaddrinuse)", re.I), ErrorType.PORT_BUSY),
    # Audio/Brightness
    (re.compile(r"(audio|pulse|sink).*(not|unavail|fail)", re.I), ErrorType.AUDIO_UNAVAILABLE),
    (re.compile(r"brightness.*(not|unavail|fail)", re.I), ErrorType.BRIGHTNESS_UNAVAILABLE),
    # Window
    (re.compile(r"window.*(not found|no.*window)", re.I), ErrorType.WINDOW_NOT_FOUND),
    # Bluetooth
    (re.compile(r"bluetooth.*(not available|no.*controller|not found)", re.I), ErrorType.BLUETOOTH_UNAVAILABLE),
    (re.compile(r"(pair|pairing).*(fail|reject|timeout)", re.I), ErrorType.BLUETOOTH_PAIR_FAILED),
]


def classify_error(error: str) -> str:
    """Classify an error string into an ErrorType."""
    if not error:
        return ErrorType.GENERIC
    for pattern, error_type in _CLASSIFIERS:
        if pattern.search(error):
            return error_type
    return ErrorType.GENERIC


# ═══════════════════════════════════════════════════════════════════════════
#  SUGGESTIONS (always actionable)
# ═══════════════════════════════════════════════════════════════════════════

# PT-BR suggestions (primary)
_SUGGESTIONS_PT: dict[str, list[str]] = {
    ErrorType.NETWORK_CONNECT: [
        "Quer ver as redes disponíveis?",
        "Tente: \"listar redes\"",
    ],
    ErrorType.NETWORK_NO_NETWORKS: [
        "O Wi-Fi pode estar desativado. Verifique o hardware.",
        "Tente se aproximar do roteador.",
    ],
    ErrorType.NETWORK_WRONG_PASSWORD: [
        "A senha parece incorreta. Quer tentar novamente?",
    ],
    ErrorType.NETWORK_TIMEOUT: [
        "A conexão demorou demais. Quer tentar de novo?",
    ],
    ErrorType.PACKAGE_NOT_FOUND: [
        "Pacote não encontrado. Quer que eu busque nomes parecidos?",
    ],
    ErrorType.PACKAGE_INSTALL_FAILED: [
        "Quer que eu atualize as listas primeiro? (\"atualizar pacotes\")",
    ],
    ErrorType.PACKAGE_DEPS: [
        "Há dependências quebradas. Tente: \"atualizar pacotes\" primeiro.",
    ],
    ErrorType.APP_NOT_FOUND: [
        "Não encontrei esse app. Quer que eu procure nomes parecidos?",
    ],
    ErrorType.PERMISSION_DENIED: [
        "Essa ação precisa de permissão de administrador.",
    ],
    ErrorType.TIMEOUT: [
        "Demorou demais. Quer tentar de novo?",
    ],
    ErrorType.DISK_FULL: [
        "Disco cheio. Quer que eu analise o que está ocupando espaço? (\"libera espaço\")",
    ],
    ErrorType.PORT_BUSY: [
        "A porta está ocupada. Quer que eu encerre o processo que está usando?",
    ],
    ErrorType.COMMAND_FAILED: [
        "O comando falhou. Quer ver os logs para mais detalhes?",
    ],
    ErrorType.AUDIO_UNAVAILABLE: [
        "Sistema de áudio indisponível. Verifique se o PulseAudio/PipeWire está rodando.",
    ],
    ErrorType.BRIGHTNESS_UNAVAILABLE: [
        "Controle de brilho não disponível neste hardware.",
    ],
    ErrorType.WINDOW_NOT_FOUND: [
        "Não encontrei essa janela. Quer ver as janelas abertas? (\"janelas abertas\")",
    ],
    ErrorType.BLUETOOTH_UNAVAILABLE: [
        "Bluetooth não disponível. Verifique se o adaptador está conectado.",
    ],
    ErrorType.BLUETOOTH_PAIR_FAILED: [
        "Pareamento falhou. Coloque o dispositivo em modo de pareamento e tente novamente.",
    ],
    ErrorType.GENERIC: [
        "Quer que eu tente de outra forma?",
    ],
}

# EN suggestions
_SUGGESTIONS_EN: dict[str, list[str]] = {
    ErrorType.NETWORK_CONNECT: [
        "Want to see available networks?",
    ],
    ErrorType.NETWORK_NO_NETWORKS: [
        "Wi-Fi might be disabled. Check your hardware switch.",
    ],
    ErrorType.NETWORK_WRONG_PASSWORD: [
        "Password seems incorrect. Want to try again?",
    ],
    ErrorType.NETWORK_TIMEOUT: [
        "Connection timed out. Want to retry?",
    ],
    ErrorType.PACKAGE_NOT_FOUND: [
        "Package not found. Want me to search for similar names?",
    ],
    ErrorType.PACKAGE_INSTALL_FAILED: [
        "Want me to update package lists first?",
    ],
    ErrorType.PACKAGE_DEPS: [
        "Broken dependencies. Try updating packages first.",
    ],
    ErrorType.APP_NOT_FOUND: [
        "App not found. Want me to search for similar names?",
    ],
    ErrorType.PERMISSION_DENIED: [
        "This action requires administrator permission.",
    ],
    ErrorType.TIMEOUT: [
        "Took too long. Want to try again?",
    ],
    ErrorType.DISK_FULL: [
        "Disk is full. Want me to analyze what's using space?",
    ],
    ErrorType.PORT_BUSY: [
        "Port is busy. Want me to kill the process using it?",
    ],
    ErrorType.COMMAND_FAILED: [
        "Command failed. Want to see the logs?",
    ],
    ErrorType.AUDIO_UNAVAILABLE: [
        "Audio system unavailable. Check if PulseAudio/PipeWire is running.",
    ],
    ErrorType.BRIGHTNESS_UNAVAILABLE: [
        "Brightness control not available on this hardware.",
    ],
    ErrorType.WINDOW_NOT_FOUND: [
        "Window not found. Want to see open windows?",
    ],
    ErrorType.BLUETOOTH_UNAVAILABLE: [
        "Bluetooth not available. Check if the adapter is connected.",
    ],
    ErrorType.BLUETOOTH_PAIR_FAILED: [
        "Pairing failed. Put the device in pairing mode and try again.",
    ],
    ErrorType.GENERIC: [
        "Want me to try a different approach?",
    ],
}


def _get_lang() -> str:
    """Get current language."""
    import os
    for var in ("LANG", "LC_MESSAGES", "LC_ALL"):
        val = os.environ.get(var, "")
        if val.lower().startswith("pt"):
            return "pt"
    return "en"


def suggest_recovery(error_type: str) -> str:
    """Get a recovery suggestion for an error type."""
    lang = _get_lang()
    suggestions = (_SUGGESTIONS_PT if lang == "pt" else _SUGGESTIONS_EN)
    options = suggestions.get(error_type, suggestions[ErrorType.GENERIC])
    return options[0]


def enrich_error(error: str, context: Optional[dict] = None) -> str:
    """Enrich an error message with a recovery suggestion.

    Takes a raw/humanized error and appends an actionable suggestion.
    Never returns an error without a next step.
    """
    if not error:
        return suggest_recovery(ErrorType.GENERIC)

    error_type = classify_error(error)

    # Use context to refine classification
    if context:
        intent = context.get("intent", "")
        if intent == "network" and error_type == ErrorType.GENERIC:
            error_type = ErrorType.NETWORK_CONNECT
        elif intent == "package" and error_type == ErrorType.GENERIC:
            error_type = ErrorType.PACKAGE_INSTALL_FAILED
        elif intent == "app_launch" and error_type == ErrorType.GENERIC:
            error_type = ErrorType.APP_NOT_FOUND

    suggestion = suggest_recovery(error_type)
    return f"{error}\n{suggestion}"


# ═══════════════════════════════════════════════════════════════════════════
#  RETRY HINTS
# ═══════════════════════════════════════════════════════════════════════════

_RETRYABLE_PATTERNS = [
    re.compile(r"(timeout|timed out)", re.I),
    re.compile(r"(busy|temporarily unavailable)", re.I),
    re.compile(r"(try again|retry)", re.I),
    re.compile(r"(connection reset|broken pipe)", re.I),
    re.compile(r"(resource.*(busy|unavailable))", re.I),
]


def is_retryable(error: str) -> bool:
    """Check if an error is worth retrying automatically."""
    if not error:
        return False
    return any(p.search(error) for p in _RETRYABLE_PATTERNS)
