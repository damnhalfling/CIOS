"""Locale skill — timezone and locale configuration via intent.

Uses timedatectl for timezone and localectl for locale.

#521 — Timezone / locale config via intent
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


def get_timezone() -> str:
    """Get current timezone."""
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "Unknown"


def set_timezone(tz: str) -> tuple[list[str], bool, str]:
    """Set system timezone.

    Args:
        tz: Timezone string (e.g. "America/Sao_Paulo", "UTC")

    Returns:
        (steps, success, message)
    """
    steps = [f"Alterando timezone para {tz}"]
    try:
        result = subprocess.run(
            ["sudo", "timedatectl", "set-timezone", tz],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return steps, True, f"Timezone alterado para {tz}."
        return steps, False, f"Timezone inválido ou erro: {result.stderr.strip()}"
    except Exception as e:
        return steps, False, f"Erro: {e}"


def list_timezones(filter_text: str = "") -> list[str]:
    """List available timezones, optionally filtered."""
    try:
        result = subprocess.run(
            ["timedatectl", "list-timezones"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            zones = result.stdout.strip().split("\n")
            if filter_text:
                zones = [z for z in zones if filter_text.lower() in z.lower()]
            return zones
    except Exception:
        pass
    return []


def get_locale() -> str:
    """Get current system locale."""
    try:
        result = subprocess.run(
            ["localectl", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "LANG=" in line:
                    return line.split("LANG=")[-1].strip()
    except Exception:
        pass
    return "Unknown"


def set_locale(locale: str) -> tuple[list[str], bool, str]:
    """Set system locale.

    Args:
        locale: Locale string (e.g. "pt_BR.UTF-8", "en_US.UTF-8")

    Returns:
        (steps, success, message)
    """
    steps = [f"Alterando locale para {locale}"]
    try:
        result = subprocess.run(
            ["sudo", "localectl", "set-locale", f"LANG={locale}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return steps, True, f"Locale alterado para {locale}."
        return steps, False, f"Locale inválido: {result.stderr.strip()}"
    except Exception as e:
        return steps, False, f"Erro: {e}"
