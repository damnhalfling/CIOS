"""Central configuration for the CIOS system.

Settings are persisted in ~/.cios/settings.json.
Environment variables override saved settings.
API keys are stored locally and never leave the machine.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# --- Paths ---
CIOS_HOME = Path(os.environ.get("CIOS_HOME", Path.home() / ".cios"))
DB_PATH = CIOS_HOME / "memory.db"
LOG_DIR = CIOS_HOME / "logs"
SETTINGS_PATH = CIOS_HOME / "settings.json"

# --- Logo ---
_LOGO_SEARCH_PATHS = [
    Path("/usr/share/pixmaps/cios-logo.png"),  # installed via .deb
    Path(__file__).parent.parent.parent / "assets" / "cios_logo.png",  # dev
]


def get_logo_path() -> Path | None:
    """Find the CIOS logo PNG. Returns None if not found."""
    for p in _LOGO_SEARCH_PATHS:
        if p.is_file():
            return p
    return None


# --- Execution ---
MAX_PLAN_STEPS = 5
COMMAND_TIMEOUT_SECONDS = 120
MAX_RETRIES = 1

# --- UI ---
HOTKEY = os.environ.get("CIOS_HOTKEY", "ctrl+space")

# --- Default settings ---
_DEFAULTS: dict[str, Any] = {
    # Provider: "ollama" (local, always first), external only when needed
    "llm_provider": "ollama",
    # Preferred external provider: "openai" | "anthropic" | "cios_api" | ""
    # When user has multiple keys, this determines which is used first.
    # Empty = auto (first configured in order: openai → anthropic → cios_api)
    "preferred_external_provider": "",
    # Ollama (local LLM — primary, required)
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2:1.5b",  # Safe default; cios-setup-ai selects optimal model
    # OpenAI (client's own key — external)
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    # Anthropic (client's own key — external)
    "anthropic_api_key": "",
    "anthropic_model": "claude-3-haiku-20240307",
    # CIOS Intelligence API (Maestro/Bedrock — always available as final fallback)
    "cios_api_key": "",
    "cios_api_url": "https://api.cios-ai.com",
}

# In-memory settings cache
_settings: dict[str, Any] = {}


def ensure_dirs() -> None:
    """Create required directories."""
    CIOS_HOME.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure standard XDG user directories exist
    _ensure_xdg_dirs()


def _ensure_xdg_dirs() -> None:
    """Create standard XDG user directories if missing."""
    home = Path.home()
    dirs = [
        home / "Desktop",
        home / "Documents",
        home / "Downloads",
        home / "Music",
        home / "Pictures",
        home / "Pictures" / "Screenshots",
        home / "Videos",
        home / "Videos" / "Recordings",
        home / "Templates",
        home / "Public",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def _load_settings() -> dict[str, Any]:
    """Load settings from disk, merging with defaults."""
    settings = dict(_DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH) as f:
                saved = json.load(f)
            settings.update(saved)
        except Exception as e:
            logger.warning("Could not load settings: %s", e)

    # Environment variables override saved settings
    env_map = {
        "OLLAMA_URL": "ollama_url",
        "OLLAMA_MODEL": "ollama_model",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_MODEL": "openai_model",
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "ANTHROPIC_MODEL": "anthropic_model",
        "CIOS_API_KEY": "cios_api_key",
        "CIOS_API_URL": "cios_api_url",
        "CIOS_LLM_PROVIDER": "llm_provider",
        "CIOS_PREFERRED_PROVIDER": "preferred_external_provider",
    }
    for env_key, setting_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            settings[setting_key] = val

    return settings


def get(key: str) -> Any:
    """Get a setting value. Loads from disk on first access."""
    global _settings
    if not _settings:
        _settings = _load_settings()
    return _settings.get(key, _DEFAULTS.get(key, ""))


def get_all() -> dict[str, Any]:
    """Get all settings as a dict."""
    global _settings
    if not _settings:
        _settings = _load_settings()
    return dict(_settings)


def set(key: str, value: Any) -> None:
    """Set a setting value in memory."""
    global _settings
    if not _settings:
        _settings = _load_settings()
    _settings[key] = value


def save() -> None:
    """Persist current settings to disk.

    Only saves non-default values and non-empty API keys.
    Settings file has restricted permissions (600).
    """
    global _settings
    if not _settings:
        return

    ensure_dirs()

    # Only save values that differ from defaults or are API keys
    to_save = {}
    for key, value in _settings.items():
        if value != _DEFAULTS.get(key) or key.endswith("_key"):
            if value:  # Don't save empty strings
                to_save[key] = value

    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(to_save, f, indent=2)
        # Restrict permissions — only owner can read
        SETTINGS_PATH.chmod(0o600)
        logger.info("Settings saved to %s", SETTINGS_PATH)
    except Exception as e:
        logger.error("Could not save settings: %s", e)


def mask_key(key: str) -> str:
    """Mask an API key for display: show first 4 and last 4 chars."""
    if not key or len(key) < 12:
        return "••••••••" if key else ""
    return f"{key[:4]}{'•' * (len(key) - 8)}{key[-4:]}"


# --- Legacy compatibility ---
# These module-level vars are used by existing code.
# They now read from the settings system.


def _get_legacy(key: str) -> str:
    return str(get(key))


# Expose as module attributes for backward compat
OLLAMA_URL = property(lambda _: _get_legacy("ollama_url"))
OLLAMA_MODEL = property(lambda _: _get_legacy("ollama_model"))
