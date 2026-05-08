"""Ollama Manager — ensures Ollama is running when needed.

Responsibilities:
- Check if Ollama is installed
- Start `ollama serve` if not already running
- Wait for readiness (up to 10s)
- Expose status for topbar indicator

This runs during bridge boot. If Ollama is not installed or fails to start,
the system degrades gracefully (regex patterns still work, LLM features disabled).
"""

import logging
import shutil
import subprocess
import time
import urllib.error
import urllib.request

from cios.core import config

logger = logging.getLogger(__name__)

# Module-level state
_ollama_status: dict = {
    "installed": False,
    "running": False,
    "model_available": False,
    "started_by_cios": False,
    "error": "",
}


def get_ollama_status() -> dict:
    """Return current Ollama status for topbar/diagnostics."""
    return dict(_ollama_status)


def is_ollama_healthy() -> bool:
    """Quick check: is Ollama running and has the configured model?"""
    return _ollama_status["running"] and _ollama_status["model_available"]


def _is_ollama_installed() -> bool:
    """Check if ollama binary exists."""
    return shutil.which("ollama") is not None


def _is_ollama_running() -> bool:
    """Check if Ollama API is responding."""
    url = config.get("ollama_url")
    try:
        req = urllib.request.Request(f"{url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=2):
            return True
    except Exception:
        return False


def _has_model(model_name: str) -> bool:
    """Check if the configured model is available in Ollama."""
    url = config.get("ollama_url")
    try:
        req = urllib.request.Request(f"{url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            import json

            data = json.loads(resp.read())
            models = [m.get("name", "") for m in data.get("models", [])]
            base = model_name.split(":")[0]
            return any(base in m for m in models)
    except Exception:
        return False


def _start_ollama_serve() -> bool:
    """Start `ollama serve` as a background process.

    Returns True if started successfully (API responds within timeout).
    """
    try:
        # Start ollama serve detached, redirect output to log
        log_path = config.CIOS_HOME / "logs" / "ollama.log"
        log_file = open(log_path, "a")

        subprocess.Popen(
            ["ollama", "serve"],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,  # detach from parent
        )
        logger.info("Started 'ollama serve' (log: %s)", log_path)
    except Exception as e:
        logger.error("Failed to start ollama serve: %s", e)
        return False

    # Wait for API to become ready (up to 10s)
    for i in range(20):
        time.sleep(0.5)
        if _is_ollama_running():
            logger.info("Ollama ready after %.1fs", (i + 1) * 0.5)
            return True

    logger.warning("Ollama started but not responding after 10s")
    return False


def ensure_ollama_running() -> bool:
    """Ensure Ollama is running if configured as the LLM provider.

    Called during bridge boot. Returns True if Ollama is healthy.
    Returns True immediately if provider is not ollama (not needed).
    """
    provider = config.get("llm_provider")

    # If not using Ollama, skip entirely
    if provider != "ollama":
        _ollama_status.update(
            installed=_is_ollama_installed(),
            running=False,
            model_available=False,
            started_by_cios=False,
            error="",
        )
        return True  # Not needed, so "healthy" from system perspective

    # Check if installed
    if not _is_ollama_installed():
        _ollama_status.update(
            installed=False,
            running=False,
            model_available=False,
            error="Ollama não instalado",
        )
        logger.warning(
            "Ollama is configured as provider but not installed. "
            "Install with: curl -fsSL https://ollama.com/install.sh | sh"
        )
        return False

    _ollama_status["installed"] = True

    # Check if already running
    if _is_ollama_running():
        _ollama_status["running"] = True
        _ollama_status["started_by_cios"] = False
        logger.info("Ollama already running")
    else:
        # Try to start it
        logger.info("Ollama not running, attempting to start...")
        if _start_ollama_serve():
            _ollama_status["running"] = True
            _ollama_status["started_by_cios"] = True
        else:
            _ollama_status.update(
                running=False,
                model_available=False,
                error="Falha ao iniciar Ollama",
            )
            return False

    # Check if model is available
    model = config.get("ollama_model")
    if _has_model(model):
        _ollama_status["model_available"] = True
        _ollama_status["error"] = ""
        logger.info("Ollama model '%s' available", model)
    else:
        _ollama_status["model_available"] = False
        _ollama_status["error"] = f"Modelo '{model}' não encontrado"
        logger.warning(
            "Ollama running but model '%s' not found. " "Pull with: ollama pull %s",
            model,
            model,
        )
        return False

    return True


def refresh_status() -> dict:
    """Re-check Ollama status (called periodically by topbar)."""
    provider = config.get("llm_provider")

    if provider != "ollama":
        _ollama_status.update(
            installed=_is_ollama_installed(),
            running=False,
            model_available=False,
            error="",
        )
        return _ollama_status

    _ollama_status["installed"] = _is_ollama_installed()
    _ollama_status["running"] = _is_ollama_running()

    if _ollama_status["running"]:
        model = config.get("ollama_model")
        _ollama_status["model_available"] = _has_model(model)
        _ollama_status["error"] = (
            "" if _ollama_status["model_available"] else f"Modelo '{model}' ausente"
        )
    else:
        _ollama_status["model_available"] = False
        _ollama_status["error"] = "Ollama offline"

    return _ollama_status
