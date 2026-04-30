"""Central configuration for the Harmoni system.

Settings are persisted in ~/.harmoni/settings.json.
Environment variables override saved settings.
API keys are stored locally and never leave the machine.
"""

import json
import os
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# --- Paths ---
HARMONI_HOME = Path(os.environ.get("HARMONI_HOME", Path.home() / ".harmoni"))
DB_PATH = HARMONI_HOME / "memory.db"
LOG_DIR = HARMONI_HOME / "logs"
SETTINGS_PATH = HARMONI_HOME / "settings.json"

# --- Logo ---
_LOGO_SEARCH_PATHS = [
    Path("/usr/share/pixmaps/harmoni-logo.png"),          # installed via .deb
    Path(__file__).parent.parent.parent / "assets" / "harmoni_logo.png",  # dev
]


def get_logo_path() -> Optional[Path]:
    """Find the Harmoni logo PNG. Returns None if not found."""
    for p in _LOGO_SEARCH_PATHS:
        if p.is_file():
            return p
    return None

# --- Execution ---
MAX_PLAN_STEPS = 5
COMMAND_TIMEOUT_SECONDS = 120
MAX_RETRIES = 1

# --- UI ---
HOTKEY = os.environ.get("HARMONI_HOTKEY", "ctrl+space")

# --- Default settings ---
_DEFAULTS: dict[str, Any] = {
    # Provider: "ollama", "openai", "anthropic", "bedrock"
    "llm_provider": "ollama",

    # Ollama
    "ollama_url": "http://localhost:11434",
    "ollama_model": "mistral",

    # OpenAI
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",

    # Anthropic (direct API)
    "anthropic_api_key": "",
    "anthropic_model": "claude-3-haiku-20240307",

    # AWS Bedrock
    "bedrock_region": "us-east-1",
    "bedrock_model_id": "anthropic.claude-3-haiku-20240307-v1:0",
    "aws_access_key_id": "",
    "aws_secret_access_key": "",
}

# In-memory settings cache
_settings: dict[str, Any] = {}


def ensure_dirs() -> None:
    """Create required directories."""
    HARMONI_HOME.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _load_settings() -> dict[str, Any]:
    """Load settings from disk, merging with defaults."""
    settings = dict(_DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r") as f:
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
        "BEDROCK_REGION": "bedrock_region",
        "BEDROCK_MODEL_ID": "bedrock_model_id",
        "AWS_ACCESS_KEY_ID": "aws_access_key_id",
        "AWS_SECRET_ACCESS_KEY": "aws_secret_access_key",
        "HARMONI_LLM_PROVIDER": "llm_provider",
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
        if value != _DEFAULTS.get(key, None) or key.endswith("_key"):
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
BEDROCK_REGION = property(lambda _: _get_legacy("bedrock_region"))
BEDROCK_MODEL_ID = property(lambda _: _get_legacy("bedrock_model_id"))
