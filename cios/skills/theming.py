"""Theming skill — switch between dark/light mode and apply theme preferences.

Manages GTK4 theme settings and compositor CSS.
Persists preference in ~/.cios/config.

#506 — Theming: dark/light mode
#507 — Theming: configuração via intent
"""

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CIOS_CONFIG_DIR = Path.home() / ".cios"
THEME_CONFIG_FILE = CIOS_CONFIG_DIR / "theme.json"

# Available themes
THEMES = {
    "dark": {
        "gtk_theme": "Adwaita-dark",
        "color_scheme": "prefer-dark",
        "description": "Modo escuro (padrão CIOS)",
    },
    "light": {
        "gtk_theme": "Adwaita",
        "color_scheme": "prefer-light",
        "description": "Modo claro",
    },
}

DEFAULT_THEME = "dark"


def get_current_theme() -> str:
    """Get the current theme name."""
    config = _load_config()
    return config.get("theme", DEFAULT_THEME)


def set_theme(theme_name: str) -> tuple[bool, str]:
    """Set the system theme.

    Args:
        theme_name: "dark" or "light"

    Returns:
        (success, message)
    """
    if theme_name not in THEMES:
        return False, f"Tema '{theme_name}' não existe. Opções: dark, light."

    theme = THEMES[theme_name]

    # Apply GTK4 color scheme via gsettings
    try:
        subprocess.run(
            [
                "gsettings",
                "set",
                "org.gnome.desktop.interface",
                "color-scheme",
                theme["color_scheme"],
            ],
            capture_output=True,
            timeout=5,
        )
    except Exception as e:
        logger.debug("gsettings color-scheme failed (expected on non-GNOME): %s", e)

    # Apply GTK theme
    try:
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.interface", "gtk-theme", theme["gtk_theme"]],
            capture_output=True,
            timeout=5,
        )
    except Exception as e:
        logger.debug("gsettings gtk-theme failed: %s", e)

    # Set GTK4 environment for new processes
    os.environ["GTK_THEME"] = theme["gtk_theme"]

    # Write GTK4 settings.ini
    gtk4_dir = Path.home() / ".config" / "gtk-4.0"
    gtk4_dir.mkdir(parents=True, exist_ok=True)
    settings_ini = gtk4_dir / "settings.ini"
    settings_ini.write_text(
        f"[Settings]\ngtk-application-prefer-dark-theme={'1' if theme_name == 'dark' else '0'}\n"
    )

    # Persist preference
    _save_config({"theme": theme_name})

    logger.info("Theme set to: %s", theme_name)
    return True, f"Tema alterado para {theme['description']}."


def toggle_theme() -> tuple[bool, str]:
    """Toggle between dark and light mode."""
    current = get_current_theme()
    new_theme = "light" if current == "dark" else "dark"
    return set_theme(new_theme)


def _load_config() -> dict:
    """Load theme config from disk."""
    try:
        if THEME_CONFIG_FILE.exists():
            return json.loads(THEME_CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_config(config: dict) -> None:
    """Save theme config to disk."""
    try:
        CIOS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        existing = _load_config()
        existing.update(config)
        THEME_CONFIG_FILE.write_text(json.dumps(existing, indent=2))
    except Exception as e:
        logger.warning("Failed to save theme config: %s", e)
