"""Shared utilities for intent handlers.

Contains:
- PlanResult dataclass
- _resilient_call() for retry + error sanitization
- _sanitize_error() for human-friendly error messages
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cios.core.executor import ExecResult

logger = logging.getLogger(__name__)


@dataclass
class PlanResult:
    plan_steps: list[str]
    results: list[ExecResult]
    outcome: str  # "success" | "failure" | "recovered"
    summary: str = ""
    error: str | None = None
    voice_mode: str = "full"  # "full" = speak summary, "brief" = "pronto, tá na tela"
    data: dict | None = None  # extra structured data (e.g., gallery signal)


# ═══════════════════════════════════════════════════════════════════════════
#  ERROR SANITIZER — never leak technical details to the user
# ═══════════════════════════════════════════════════════════════════════════

_SKILL_FALLBACKS = {
    "network": "Não consegui completar a operação de rede.",
    "audio": "Não consegui ajustar o áudio.",
    "power": "Não consegui acessar as configurações de energia.",
    "package": "Não consegui completar a operação de pacotes.",
    "window": "Não consegui controlar a janela.",
    "app_launch": "Não consegui abrir o aplicativo.",
    "clipboard": "Não consegui acessar a área de transferência.",
    "disk": "Não consegui analisar o disco.",
    "session": "Não consegui executar a ação de sessão.",
}


def sanitize_error(error: str, skill: str = "") -> str:
    """Strip technical noise from error messages. Never show raw stderr.

    Rules:
    - No file paths (/usr/lib/python3/...)
    - No tracebacks (File "...", line N)
    - No error codes (errno, E2BIG, ENOENT)
    - No process/PID references
    - No raw command output
    - Always return something human-readable
    """
    if not error:
        return ""

    # Strip raw stderr prefix
    cleaned = re.sub(r"\bstderr:\s*", "", error)
    # Strip file paths
    cleaned = re.sub(r"/[\w/.\-]+", "", cleaned)
    # Strip tracebacks
    cleaned = re.sub(r'File ".*?", line \d+.*', "", cleaned)
    # Strip error codes
    cleaned = re.sub(r"\b(errno|E[A-Z]{2,}|error\s*\d+)\b", "", cleaned, flags=re.I)
    # Strip PID references
    cleaned = re.sub(r"\(PID \d+\)", "", cleaned)
    cleaned = re.sub(r"PID \d+", "", cleaned)
    # Strip subprocess noise
    cleaned = re.sub(r"(subprocess|Popen|CalledProcessError).*", "", cleaned, flags=re.I)
    # Strip Python exception class names
    cleaned = re.sub(r"\b\w*(Error|Exception|Warning)\b:\s*", "", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # If nothing useful remains, return a generic message
    if not cleaned or len(cleaned) < 5:
        return _SKILL_FALLBACKS.get(skill, "Algo deu errado.")

    # Truncate to reasonable length
    return cleaned[:150]


def _is_transient(error: str) -> bool:
    """Check if an error is likely transient (worth retrying)."""
    if not error:
        return False
    lower = error.lower()
    return any(
        kw in lower
        for kw in (
            "timeout",
            "timed out",
            "busy",
            "temporarily",
            "try again",
            "connection reset",
            "resource",
            "lock",
            "unavailable",
        )
    )


def resilient_call(
    fn: Callable[..., tuple],
    *args: Any,
    skill: str = "",
    retryable: bool = True,
    retry_delay: float = 0.5,
) -> tuple:
    """Call a skill function with retry and error sanitization.

    Wraps any skill call (fn that returns (steps, ok, msg) or similar)
    with:
    1. Try/except for unexpected crashes
    2. One retry on transient failures
    3. Error message sanitization

    Returns the same tuple the skill would return.
    """
    try:
        result = fn(*args)
    except FileNotFoundError as e:
        tool = str(e).split("'")[-2] if "'" in str(e) else "ferramenta"
        msg = f"{tool} não está instalado neste sistema."
        logger.warning("Skill %s: tool not found: %s", skill, e)
        return (["Verificando disponibilidade"], False, msg)
    except Exception as e:
        logger.exception("Skill %s: unexpected error", skill)
        msg = sanitize_error(str(e), skill)
        return (["Executando"], False, msg)

    # If the result is a tuple with (steps, ok, msg) pattern
    if isinstance(result, tuple) and len(result) >= 2:
        # Check if second element is a bool (success flag)
        if isinstance(result[1], bool) and not result[1] and retryable:
            # Failed — retry once
            error_msg = result[2] if len(result) > 2 else ""
            if _is_transient(error_msg):
                logger.info("Skill %s: transient failure, retrying: %s", skill, error_msg[:80])
                time.sleep(retry_delay)
                try:
                    result = fn(*args)
                except Exception:
                    pass  # keep original result

        # Sanitize error message in the result
        if (
            isinstance(result, tuple)
            and len(result) >= 3
            and isinstance(result[1], bool)
            and not result[1]
        ):
            sanitized = sanitize_error(str(result[2]), skill)
            result = (result[0], result[1], sanitized)

    return result
