"""Skill: Self-Update — check for new versions and update Harmoni.

Checks GitHub releases for newer versions, downloads the .deb,
and installs it. Requires sudo for dpkg.

Features:
- Check latest version without installing
- Download + install in one step (with confirmation)
- Boot check: notify user if update available (non-blocking)
- Never auto-installs without confirmation

Security:
- Downloads only from official GitHub releases
- Verifies .deb filename pattern before installing
- Requires explicit user confirmation for install
"""

import json
import logging
import os
import re
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from harmoni.core.config import HARMONI_HOME

logger = logging.getLogger(__name__)

_GITHUB_REPO = "damnhalfling/harmoni"
_GITHUB_API = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
_CHECK_TIMEOUT = 10
_DOWNLOAD_TIMEOUT = 120
_CACHE_FILE = HARMONI_HOME / ".update_cache.json"
_CACHE_TTL = 3600  # 1 hour


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    download_url: str
    release_notes: str
    has_update: bool


def get_current_version() -> str:
    """Get the currently installed version."""
    try:
        from harmoni import __version__
        return __version__
    except ImportError:
        return "unknown"


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse version string to comparable tuple. '0.10.3' → (0, 10, 3)."""
    clean = v.lstrip("v").strip()
    parts = []
    for p in clean.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _is_newer(latest: str, current: str) -> bool:
    """Check if latest version is newer than current."""
    return _parse_version(latest) > _parse_version(current)


def _read_cache() -> Optional[dict]:
    """Read cached update check result."""
    try:
        if _CACHE_FILE.exists():
            import time
            data = json.loads(_CACHE_FILE.read_text())
            if time.time() - data.get("timestamp", 0) < _CACHE_TTL:
                return data
    except Exception:
        pass
    return None


def _write_cache(data: dict) -> None:
    """Cache update check result."""
    try:
        import time
        data["timestamp"] = time.time()
        HARMONI_HOME.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(data))
    except Exception:
        pass


def check_update(use_cache: bool = True) -> UpdateInfo:
    """Check if a newer version is available on GitHub.

    Args:
        use_cache: Use cached result if available (default True).

    Returns:
        UpdateInfo with current/latest versions and download URL.
    """
    current = get_current_version()

    # Try cache first
    if use_cache:
        cached = _read_cache()
        if cached:
            return UpdateInfo(
                current_version=current,
                latest_version=cached.get("latest_version", current),
                download_url=cached.get("download_url", ""),
                release_notes=cached.get("release_notes", ""),
                has_update=_is_newer(cached.get("latest_version", current), current),
            )

    # Fetch from GitHub API
    try:
        req = urllib.request.Request(
            _GITHUB_API,
            headers={"Accept": "application/vnd.github.v3+json",
                     "User-Agent": f"Harmoni/{current}"},
        )
        with urllib.request.urlopen(req, timeout=_CHECK_TIMEOUT) as resp:
            data = json.loads(resp.read())

        tag = data.get("tag_name", "")
        latest = tag.lstrip("v")
        body = data.get("body", "")

        # Find .deb asset
        download_url = ""
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith("_amd64.deb") and "harmoni" in name:
                download_url = asset.get("browser_download_url", "")
                break

        # Cache result
        _write_cache({
            "latest_version": latest,
            "download_url": download_url,
            "release_notes": body[:500],
        })

        return UpdateInfo(
            current_version=current,
            latest_version=latest,
            download_url=download_url,
            release_notes=body[:500],
            has_update=_is_newer(latest, current),
        )

    except urllib.error.URLError as e:
        logger.warning("Update check failed (network): %s", e)
        return UpdateInfo(
            current_version=current,
            latest_version=current,
            download_url="",
            release_notes="",
            has_update=False,
        )
    except Exception as e:
        logger.warning("Update check failed: %s", e)
        return UpdateInfo(
            current_version=current,
            latest_version=current,
            download_url="",
            release_notes="",
            has_update=False,
        )


def download_and_install(info: UpdateInfo) -> tuple[list[str], bool, str]:
    """Download the latest .deb and install it.

    Returns: (plan_steps, success, message)
    """
    steps = []

    if not info.has_update:
        return (["Checking version"],
                True,
                f"Já está na versão mais recente ({info.current_version})")

    if not info.download_url:
        return (["Checking release"],
                False,
                "Não encontrei o pacote .deb na release. Baixe manualmente em:\n"
                f"https://github.com/{_GITHUB_REPO}/releases")

    # Download
    deb_path = Path(f"/tmp/harmoni_{info.latest_version}_amd64.deb")
    steps.append(f"Baixando v{info.latest_version}…")

    try:
        urllib.request.urlretrieve(info.download_url, str(deb_path))
    except Exception as e:
        logger.error("Download failed: %s", e)
        return (steps, False,
                "Falha no download. Verifique sua conexão.")

    # Validate filename
    if not re.match(r"^harmoni_[\d.]+_amd64\.deb$", deb_path.name):
        return (steps, False, "Arquivo baixado não parece válido.")

    if not deb_path.exists() or deb_path.stat().st_size < 10000:
        return (steps, False, "Download incompleto. Tente novamente.")

    # Install with sudo
    steps.append("Instalando…")
    try:
        # Stop running harmoni processes (except this one)
        my_pid = os.getpid()
        subprocess.run(
            f"pgrep -f 'python.*harmoni\\.main' | grep -v {my_pid} | xargs -r kill 2>/dev/null || true",
            shell=True, timeout=5,
        )

        result = subprocess.run(
            ["sudo", "-n", "dpkg", "-i", str(deb_path)],
            capture_output=True, text=True, timeout=_DOWNLOAD_TIMEOUT,
        )

        if result.returncode != 0:
            # Try with apt-get fix
            subprocess.run(
                ["sudo", "-n", "apt-get", "install", "-f", "-y"],
                capture_output=True, timeout=60,
            )
            # Retry
            result = subprocess.run(
                ["sudo", "-n", "dpkg", "-i", str(deb_path)],
                capture_output=True, text=True, timeout=_DOWNLOAD_TIMEOUT,
            )

        if result.returncode == 0:
            steps.append(f"v{info.latest_version} instalada")
            # Clean up
            try:
                deb_path.unlink()
            except OSError:
                pass
            # Clear cache
            try:
                _CACHE_FILE.unlink()
            except OSError:
                pass
            return (steps, True,
                    f"Atualizado para v{info.latest_version}.\n"
                    "Reinicie o Harmoni para usar a nova versão.")
        else:
            stderr = result.stderr[:200] if result.stderr else ""
            if "permission" in stderr.lower() or "not permitted" in stderr.lower():
                return (steps, False,
                        "Precisa de permissão de administrador para atualizar.\n"
                        f"Execute: sudo dpkg -i {deb_path}")
            return (steps, False,
                    "Falha na instalação. Tente manualmente:\n"
                    f"sudo dpkg -i {deb_path}")

    except subprocess.TimeoutExpired:
        return (steps, False, "Instalação demorou demais. Tente novamente.")
    except Exception as e:
        logger.error("Install failed: %s", e)
        return (steps, False,
                f"Erro na instalação. O pacote está em {deb_path}")


def check_update_summary() -> tuple[list[str], str]:
    """Quick check for updates — returns human-friendly summary.

    Used by planner for "tem atualização?" queries.
    Returns: (plan_steps, summary)
    """
    steps = ["Verificando atualizações…"]
    info = check_update(use_cache=True)

    if info.has_update:
        summary = (f"Nova versão disponível: v{info.latest_version} "
                   f"(atual: v{info.current_version})\n"
                   "Quer atualizar agora?")
    else:
        summary = f"Harmoni v{info.current_version} — já está na versão mais recente."

    return steps, summary


def boot_update_check() -> Optional[str]:
    """Non-blocking update check for boot. Returns notification or None.

    Called during startup. Uses cache to avoid network delay.
    If cache is stale, does a quick check in background.
    """
    try:
        info = check_update(use_cache=True)
        if info.has_update:
            return (f"Nova versão disponível: v{info.latest_version}. "
                    "Diga \"atualizar harmoni\" para instalar.")
    except Exception:
        pass
    return None
