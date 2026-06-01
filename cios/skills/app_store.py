"""App store skill — install apps via Flatpak/Snap.

Provides a unified interface for discovering and installing apps
from Flatpak (Flathub) and Snap stores.

#525 — App store integration (Flatpak/Snap via intent)
"""

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AppResult:
    """An app search result."""
    name: str
    app_id: str
    description: str
    source: str  # "flatpak" | "snap"


def search_apps(query: str) -> list[AppResult]:
    """Search for apps in Flatpak and Snap stores."""
    results = []

    # Search Flatpak
    results.extend(_search_flatpak(query))

    # Search Snap
    results.extend(_search_snap(query))

    return results


def install_app(app_id: str, source: str = "flatpak") -> tuple[list[str], bool, str]:
    """Install an app from Flatpak or Snap.

    Args:
        app_id: App identifier (e.g. "com.spotify.Client" or "spotify")
        source: "flatpak" or "snap"

    Returns:
        (steps, success, message)
    """
    steps = [f"Instalando {app_id} via {source}"]

    if source == "flatpak":
        try:
            result = subprocess.run(
                ["flatpak", "install", "-y", "flathub", app_id],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return steps, True, f"{app_id} instalado via Flatpak."
            return steps, False, f"Falha: {result.stderr.strip()[:100]}"
        except FileNotFoundError:
            return steps, False, "Flatpak não instalado. Instale com: sudo apt install flatpak"
    elif source == "snap":
        try:
            result = subprocess.run(
                ["sudo", "snap", "install", app_id],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return steps, True, f"{app_id} instalado via Snap."
            return steps, False, f"Falha: {result.stderr.strip()[:100]}"
        except FileNotFoundError:
            return steps, False, "Snap não instalado. Instale com: sudo apt install snapd"

    return steps, False, f"Fonte desconhecida: {source}"


def remove_app(app_id: str, source: str = "flatpak") -> tuple[list[str], bool, str]:
    """Remove an installed app."""
    steps = [f"Removendo {app_id}"]

    if source == "flatpak":
        try:
            result = subprocess.run(
                ["flatpak", "uninstall", "-y", app_id],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return steps, True, f"{app_id} removido."
            return steps, False, f"Falha: {result.stderr.strip()[:100]}"
        except Exception as e:
            return steps, False, f"Erro: {e}"
    elif source == "snap":
        try:
            result = subprocess.run(
                ["sudo", "snap", "remove", app_id],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return steps, True, f"{app_id} removido."
            return steps, False, f"Falha: {result.stderr.strip()[:100]}"
        except Exception as e:
            return steps, False, f"Erro: {e}"

    return steps, False, f"Fonte desconhecida: {source}"


def list_installed() -> list[AppResult]:
    """List installed Flatpak and Snap apps."""
    results = []

    # Flatpak
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application,name"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = line.split("\t")
                if len(parts) >= 2:
                    results.append(AppResult(
                        name=parts[1], app_id=parts[0],
                        description="", source="flatpak",
                    ))
    except Exception:
        pass

    # Snap
    try:
        result = subprocess.run(
            ["snap", "list"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n")[1:]:  # Skip header
                parts = line.split()
                if parts:
                    results.append(AppResult(
                        name=parts[0], app_id=parts[0],
                        description="", source="snap",
                    ))
    except Exception:
        pass

    return results


def _search_flatpak(query: str) -> list[AppResult]:
    """Search Flatpak/Flathub."""
    try:
        result = subprocess.run(
            ["flatpak", "search", query],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            results = []
            for line in result.stdout.strip().split("\n")[:10]:
                parts = line.split("\t")
                if len(parts) >= 3:
                    results.append(AppResult(
                        name=parts[0],
                        description=parts[1] if len(parts) > 1 else "",
                        app_id=parts[2] if len(parts) > 2 else parts[0],
                        source="flatpak",
                    ))
            return results
    except Exception:
        pass
    return []


def _search_snap(query: str) -> list[AppResult]:
    """Search Snap store."""
    try:
        result = subprocess.run(
            ["snap", "find", query],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            results = []
            for line in result.stdout.strip().split("\n")[1:10]:  # Skip header
                parts = line.split()
                if len(parts) >= 2:
                    results.append(AppResult(
                        name=parts[0],
                        description=" ".join(parts[4:]) if len(parts) > 4 else "",
                        app_id=parts[0],
                        source="snap",
                    ))
            return results
    except Exception:
        pass
    return []
