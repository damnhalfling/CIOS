"""App Launcher skill — open applications by name using natural language.

Scans .desktop files, builds a cache of installed apps, and launches them
via subprocess. The user never sees commands or paths.
"""

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AppInfo:
    name: str
    exec_command: str
    desktop_file: str
    keywords: list[str] = field(default_factory=list)
    icon: str = ""


# Cache global de apps — preenchido no primeiro uso
_app_cache: list[AppInfo] = []
_cache_loaded: bool = False


# Aliases comuns: o que o usuário diz → nome real do .desktop
_ALIASES: dict[str, list[str]] = {
    "chrome": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "google-chrome": ["google-chrome", "google-chrome-stable"],
    "google chrome": ["google-chrome", "google-chrome-stable"],
    "navegador": ["google-chrome", "firefox", "chromium"],
    "browser": ["google-chrome", "firefox", "chromium"],
    "firefox": ["firefox", "firefox-esr"],
    "code": ["code", "visual-studio-code"],
    "vscode": ["code", "visual-studio-code"],
    "terminal": [
        "foot",
        "gnome-terminal",
        "xterm",
        "konsole",
        "alacritty",
        "kitty",
        "xfce4-terminal",
    ],
    "bash": ["foot", "gnome-terminal", "xterm", "konsole", "alacritty", "kitty"],
    "shell": ["foot", "gnome-terminal", "xterm", "konsole", "alacritty", "kitty"],
    "console": ["foot", "gnome-terminal", "xterm", "konsole", "alacritty", "kitty"],
    "arquivos": ["nautilus", "thunar", "nemo", "pcmanfm", "dolphin", "caja"],
    "gerenciador de arquivos": ["nautilus", "thunar", "nemo", "pcmanfm", "dolphin", "caja"],
    "file manager": ["nautilus", "thunar", "nemo", "pcmanfm", "dolphin", "caja"],
    "files": ["nautilus", "thunar", "nemo", "pcmanfm", "dolphin", "caja"],
    "editor": ["gedit", "kate", "mousepad", "pluma", "xed"],
    "texto": ["gedit", "kate", "mousepad", "pluma", "xed"],
    "musica": ["spotify", "rhythmbox", "audacious", "clementine"],
    "music": ["spotify", "rhythmbox", "audacious", "clementine"],
    "spotify": ["spotify"],
    "calculadora": ["gnome-calculator", "kcalc", "galculator"],
    "calculator": ["gnome-calculator", "kcalc", "galculator"],
    "configuracoes": ["gnome-control-center", "xfce4-settings-manager"],
    "settings": ["gnome-control-center", "xfce4-settings-manager"],
    "telegram": ["telegram-desktop", "telegramdesktop"],
    "discord": ["discord"],
    "slack": ["slack"],
    "gimp": ["gimp"],
    "vlc": ["vlc"],
    "libreoffice": ["libreoffice-startcenter", "libreoffice"],
    "writer": ["libreoffice-writer"],
    "calc": ["libreoffice-calc"],
}


def _scan_desktop_files() -> list[AppInfo]:
    """Scan standard directories for .desktop files and build app list."""
    dirs = [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local" / "share" / "applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        Path.home() / ".local" / "share" / "flatpak" / "exports" / "share" / "applications",
        Path("/snap/applications"),
    ]

    apps: list[AppInfo] = []
    seen_names: set[str] = set()

    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.suffix != ".desktop" or not f.is_file():
                continue
            try:
                app = _parse_desktop_file(f)
                if app and app.name.lower() not in seen_names:
                    apps.append(app)
                    seen_names.add(app.name.lower())
            except Exception:
                continue

    logger.info(f"App launcher: found {len(apps)} applications")
    return apps


def _parse_desktop_file(path: Path) -> AppInfo | None:
    """Parse a single .desktop file into AppInfo."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    # Só processar [Desktop Entry]
    if "[Desktop Entry]" not in content:
        return None

    # Ignorar apps NoDisplay ou Hidden
    if re.search(r"^NoDisplay\s*=\s*true", content, re.MULTILINE | re.IGNORECASE):
        return None
    if re.search(r"^Hidden\s*=\s*true", content, re.MULTILINE | re.IGNORECASE):
        return None

    # Só Application type
    type_match = re.search(r"^Type\s*=\s*(.+)$", content, re.MULTILINE)
    if type_match and type_match.group(1).strip() != "Application":
        return None

    name_match = re.search(r"^Name\s*=\s*(.+)$", content, re.MULTILINE)
    exec_match = re.search(r"^Exec\s*=\s*(.+)$", content, re.MULTILINE)

    if not name_match or not exec_match:
        return None

    name = name_match.group(1).strip()
    exec_cmd = exec_match.group(1).strip()

    # Remover field codes do Exec (%u, %U, %f, %F, etc.)
    exec_cmd = re.sub(r"\s+%[a-zA-Z]", "", exec_cmd).strip()

    # Keywords
    keywords: list[str] = []
    kw_match = re.search(r"^Keywords\s*=\s*(.+)$", content, re.MULTILINE)
    if kw_match:
        keywords = [k.strip().lower() for k in kw_match.group(1).split(";") if k.strip()]

    # GenericName como keyword extra
    gn_match = re.search(r"^GenericName\s*=\s*(.+)$", content, re.MULTILINE)
    if gn_match:
        keywords.append(gn_match.group(1).strip().lower())

    # Icon
    icon = ""
    icon_match = re.search(r"^Icon\s*=\s*(.+)$", content, re.MULTILINE)
    if icon_match:
        icon = icon_match.group(1).strip()

    return AppInfo(
        name=name,
        exec_command=exec_cmd,
        desktop_file=str(path),
        keywords=keywords,
        icon=icon,
    )


def _ensure_cache() -> list[AppInfo]:
    """Load app cache if not loaded yet."""
    global _app_cache, _cache_loaded
    if not _cache_loaded:
        _app_cache = _scan_desktop_files()
        _cache_loaded = True
    return _app_cache


def _normalize(text: str) -> str:
    """Normalize text for matching: lowercase, strip accents."""
    text = text.lower().strip()
    # Remover acentos comuns do português
    replacements = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ü": "u",
        "ç": "c",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def find_app(query: str) -> AppInfo | None:
    """Find the best matching app for a user query.

    Search order:
    1. Exact alias match
    2. Exact name match (case-insensitive)
    3. Name starts with query
    4. Name contains query
    5. Keywords contain query
    """
    apps = _ensure_cache()
    q = _normalize(query)

    if not q:
        return None

    # 1. Alias match
    if q in _ALIASES:
        for alias_target in _ALIASES[q]:
            for app in apps:
                app_name_norm = _normalize(app.name)
                exec_base = (
                    os.path.basename(app.exec_command.split()[0]).lower()
                    if app.exec_command
                    else ""
                )
                desktop_stem = Path(app.desktop_file).stem.lower()

                if alias_target in (exec_base, desktop_stem, app_name_norm):
                    return app

    # 2. Exact name match
    for app in apps:
        if _normalize(app.name) == q:
            return app

    # 3. Exec basename match
    for app in apps:
        exec_base = (
            os.path.basename(app.exec_command.split()[0]).lower() if app.exec_command else ""
        )
        if exec_base == q:
            return app

    # 3b. Desktop file stem match (e.g. "google-chrome" matches google-chrome.desktop)
    for app in apps:
        desktop_stem = Path(app.desktop_file).stem.lower()
        if desktop_stem == q:
            return app

    # 4. Name starts with query
    for app in apps:
        if _normalize(app.name).startswith(q):
            return app

    # 5. Name contains query
    for app in apps:
        if q in _normalize(app.name):
            return app

    # 6. Keywords contain query
    for app in apps:
        for kw in app.keywords:
            if q in _normalize(kw):
                return app

    return None


def launch_app(app: AppInfo) -> tuple[list[str], bool, str | None]:
    """Launch an application.

    Returns:
        (plan_steps, success, error)
    """
    plan_steps = [f"Opening {app.name}"]

    try:
        # Ensure Wayland env vars are set for child processes
        env = os.environ.copy()
        runtime_dir = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        if "WAYLAND_DISPLAY" not in env:
            # Auto-detect: check for wayland-0 socket
            wayland_sock = os.path.join(runtime_dir, "wayland-0")
            if os.path.exists(wayland_sock):
                env["WAYLAND_DISPLAY"] = "wayland-0"

        subprocess.Popen(
            app.exec_command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        plan_steps.append(f"{app.name} is running")
        return plan_steps, True, None

    except Exception as e:
        error = str(e)
        plan_steps.append(f"Failed to open {app.name}")
        return plan_steps, False, error


def list_installed_apps(limit: int = 20) -> list[str]:
    """Return names of installed apps (for suggestions)."""
    apps = _ensure_cache()
    return [app.name for app in apps[:limit]]


def get_installed_apps() -> list[AppInfo]:
    """Return all installed apps (full AppInfo objects)."""
    return _ensure_cache()
