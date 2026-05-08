"""Skill: log_analysis — read logs, identify errors, suggest fixes."""

import re
from dataclasses import dataclass

from cios.core.executor import Executor
from cios.core.model_router import route_to_llm


@dataclass
class LogInsight:
    source: str
    error_lines: list[str]
    root_cause: str
    suggestion: str


# Common error patterns and their known fixes
_KNOWN_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"EADDRINUSE.*:(\d+)", re.IGNORECASE),
        "Port {port} already in use",
        "Kill the process using port {port} and retry",
    ),
    (
        re.compile(r"EACCES.*permission denied", re.IGNORECASE),
        "Permission denied",
        "Run with elevated permissions or fix file ownership",
    ),
    (
        re.compile(r"MODULE_NOT_FOUND|Cannot find module", re.IGNORECASE),
        "Missing module",
        "Run npm install to restore dependencies",
    ),
    (
        re.compile(r"ENOSPC", re.IGNORECASE),
        "No space left on device",
        "Free disk space and retry",
    ),
    (
        re.compile(r"ECONNREFUSED", re.IGNORECASE),
        "Connection refused",
        "Check if the target service is running",
    ),
    (
        re.compile(r"SyntaxError|Unexpected token", re.IGNORECASE),
        "Syntax error in code",
        "Check recent code changes for syntax issues",
    ),
]


def analyze_text(text: str, source: str = "output") -> LogInsight:
    """Analyze a block of text for errors and return an insight."""
    error_lines = []
    for line in text.splitlines():
        lower = line.lower()
        if any(kw in lower for kw in ("error", "fatal", "failed", "exception", "eaddrinuse")):
            error_lines.append(line.strip())

    # Try known patterns first
    for pattern, cause_tpl, suggestion_tpl in _KNOWN_PATTERNS:
        match = pattern.search(text)
        if match:
            groups = match.groups()
            port = groups[0] if groups else ""
            cause = cause_tpl.replace("{port}", port)
            suggestion = suggestion_tpl.replace("{port}", port)
            return LogInsight(
                source=source,
                error_lines=error_lines[:10],
                root_cause=cause,
                suggestion=suggestion,
            )

    # Fallback: use LLM for unknown errors
    if error_lines:
        llm_result = route_to_llm(
            "Analyze these error lines and give a one-line root cause and fix:\n"
            + "\n".join(error_lines[:10]),
            complex=False,
        )
        if llm_result:
            return LogInsight(
                source=source,
                error_lines=error_lines[:10],
                root_cause=llm_result.get("root_cause", "Unknown error"),
                suggestion=llm_result.get("suggestion", "Review the error output"),
            )

    if error_lines:
        return LogInsight(
            source=source,
            error_lines=error_lines[:10],
            root_cause="Unrecognized error",
            suggestion="Review the full log output",
        )

    return LogInsight(
        source=source,
        error_lines=[],
        root_cause="No errors detected",
        suggestion="System appears healthy",
    )


def read_system_logs(executor: Executor, lines: int = 50) -> str:
    """Read recent system journal entries."""
    result = executor.run(
        f"journalctl --user --no-pager -n {lines} 2>/dev/null || tail -n {lines} /var/log/syslog 2>/dev/null || echo 'No logs available'"
    )
    return result.stdout or result.stderr
