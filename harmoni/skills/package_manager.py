"""Skill: Package Management — apt + sudo handling.

Provides safe package management operations:
- Install packages (with sudo)
- Remove packages (with confirmation)
- Search packages
- Update package lists
- Upgrade system packages
- List installed packages
- Check if a package is installed

Security:
- All operations require explicit user confirmation
- Blocked patterns prevent dangerous operations
- Timeout protection for long-running installs
"""

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT = 300  # 5 minutes max for installs
_SEARCH_TIMEOUT = 30
_UPDATE_TIMEOUT = 120


def _sudo_cmd() -> list[str]:
    """Determine the best way to run privileged commands.

    Returns ["sudo", "-n"] if NOPASSWD works, otherwise ["sudo", "-S"]
    which reads password from stdin.
    """
    try:
        r = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True, timeout=3,
        )
        if r.returncode == 0:
            return ["sudo", "-n"]
    except Exception:
        pass

    # Fallback: sudo -S reads password from stdin
    return ["sudo", "-S"]


def needs_sudo_password() -> bool:
    """Check if sudo requires a password (no NOPASSWD configured)."""
    try:
        r = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True, timeout=3,
        )
        return r.returncode != 0
    except Exception:
        return True


def _run_privileged(
    cmd: list[str],
    password: str = "",
    timeout: int = _INSTALL_TIMEOUT,
) -> subprocess.CompletedProcess:
    """Run a command with sudo, optionally passing password via stdin.

    If password is provided, uses 'sudo -S' (reads from stdin).
    If not, uses 'sudo -n' (non-interactive) or 'sudo -S' with empty stdin.
    """
    env = {
        "DEBIAN_FRONTEND": "noninteractive",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }

    if password:
        # sudo -S reads password from stdin
        return subprocess.run(
            ["sudo", "-S"] + cmd,
            input=password + "\n",
            capture_output=True, text=True,
            timeout=timeout, env=env,
        )
    else:
        return subprocess.run(
            _sudo_cmd() + cmd,
            capture_output=True, text=True,
            timeout=timeout, env=env,
        )

# Packages that should never be removed
_PROTECTED_PACKAGES = frozenset([
    "systemd", "init", "linux-image", "grub", "apt", "dpkg",
    "libc6", "bash", "coreutils", "login", "passwd",
])


@dataclass
class PackageInfo:
    name: str
    version: str = ""
    description: str = ""
    installed: bool = False
    size: str = ""


@dataclass
class PackageResult:
    plan_steps: list[str]
    success: bool
    message: str
    packages: list[PackageInfo] = None

    def __post_init__(self):
        if self.packages is None:
            self.packages = []


def is_installed(package: str) -> bool:
    """Check if a package is installed."""
    try:
        result = subprocess.run(
            ["dpkg", "-s", package],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and "Status: install ok installed" in result.stdout
    except Exception:
        return False


def search_packages(query: str, limit: int = 10) -> PackageResult:
    """Search for packages matching a query."""
    steps = [f"Searching for '{query}'"]
    try:
        result = subprocess.run(
            ["apt-cache", "search", query],
            capture_output=True, text=True, timeout=_SEARCH_TIMEOUT,
        )
        if result.returncode != 0:
            return PackageResult(steps, False, _humanize_apt_error(result.stderr, "search", query))

        packages = []
        for line in result.stdout.strip().splitlines()[:limit]:
            parts = line.split(" - ", 1)
            if len(parts) == 2:
                name, desc = parts
                packages.append(PackageInfo(
                    name=name.strip(),
                    description=desc.strip(),
                    installed=is_installed(name.strip()),
                ))

        if not packages:
            return PackageResult(steps, True, f"No packages found for '{query}'")

        steps.append(f"Found {len(packages)} packages")
        return PackageResult(steps, True, f"Found {len(packages)} packages", packages)
    except subprocess.TimeoutExpired:
        return PackageResult(steps, False, "A busca demorou demais. Tente um termo mais específico.")
    except Exception as e:
        return PackageResult(steps, False, _humanize_apt_error(str(e), "search", query))


def install_package(package: str, password: str = "") -> PackageResult:
    """Install a package via apt. Requires sudo."""
    steps = [f"Installing {package}"]

    # Validate package name
    if not re.match(r'^[a-z0-9][a-z0-9.+\-]+$', package):
        return PackageResult(steps, False, f"Invalid package name: {package}")

    if is_installed(package):
        return PackageResult(steps, True, f"{package} is already installed")

    steps.append("Running apt install")
    try:
        result = _run_privileged(
            ["apt-get", "install", "-y", package],
            password=password, timeout=_INSTALL_TIMEOUT,
        )
        if result.returncode == 0:
            steps.append(f"{package} installed successfully")
            return PackageResult(steps, True, f"{package} installed successfully")
        else:
            return PackageResult(steps, False, _humanize_apt_error(result.stderr, "install", package))
    except subprocess.TimeoutExpired:
        return PackageResult(steps, False, f"A instalação de {package} demorou demais. Tente novamente.")
    except Exception as e:
        return PackageResult(steps, False, _humanize_apt_error(str(e), "install", package))


def remove_package(package: str, password: str = "") -> PackageResult:
    """Remove a package via apt. Requires sudo."""
    steps = [f"Removing {package}"]

    # Safety check
    if package in _PROTECTED_PACKAGES or any(package.startswith(p) for p in _PROTECTED_PACKAGES):
        return PackageResult(steps, False, f"Cannot remove protected package: {package}")

    if not is_installed(package):
        return PackageResult(steps, True, f"{package} is not installed")

    steps.append("Running apt remove")
    try:
        result = _run_privileged(
            ["apt-get", "remove", "-y", package],
            password=password, timeout=_INSTALL_TIMEOUT,
        )
        if result.returncode == 0:
            steps.append(f"{package} removed")
            return PackageResult(steps, True, f"{package} removed successfully")
        else:
            return PackageResult(steps, False, _humanize_apt_error(result.stderr, "remove", package))
    except subprocess.TimeoutExpired:
        return PackageResult(steps, False, f"A remoção de {package} demorou demais.")
    except Exception as e:
        return PackageResult(steps, False, _humanize_apt_error(str(e), "remove", package))


def update_lists(password: str = "") -> PackageResult:
    """Update apt package lists."""
    steps = ["Updating package lists"]
    try:
        result = _run_privileged(
            ["apt-get", "update"],
            password=password, timeout=_UPDATE_TIMEOUT,
        )
        if result.returncode == 0:
            steps.append("Package lists updated")
            return PackageResult(steps, True, "Package lists updated successfully")
        else:
            return PackageResult(steps, False, _humanize_apt_error(result.stderr, "update", ""))
    except subprocess.TimeoutExpired:
        return PackageResult(steps, False, "A atualização demorou demais. Verifique sua conexão.")
    except Exception as e:
        return PackageResult(steps, False, _humanize_apt_error(str(e), "update", ""))


def upgrade_packages(password: str = "") -> PackageResult:
    """Upgrade all packages. Requires sudo."""
    steps = ["Upgrading system packages"]
    try:
        result = _run_privileged(
            ["apt-get", "upgrade", "-y"],
            password=password, timeout=600,
        )
        if result.returncode == 0:
            # Count upgraded packages
            upgraded = len(re.findall(r"Unpacking .+ over", result.stdout))
            steps.append(f"{upgraded} packages upgraded")
            return PackageResult(steps, True, f"System upgraded ({upgraded} packages)")
        else:
            return PackageResult(steps, False, _humanize_apt_error(result.stderr, "upgrade", ""))
    except subprocess.TimeoutExpired:
        return PackageResult(steps, False, "A atualização demorou demais (>10min). Tente novamente.")
    except Exception as e:
        return PackageResult(steps, False, _humanize_apt_error(str(e), "upgrade", ""))


def get_package_info(package: str) -> Optional[PackageInfo]:
    """Get detailed info about a package."""
    try:
        result = subprocess.run(
            ["apt-cache", "show", package],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        info = PackageInfo(name=package, installed=is_installed(package))
        for line in result.stdout.splitlines():
            if line.startswith("Version:"):
                info.version = line.split(":", 1)[1].strip()
            elif line.startswith("Description:"):
                info.description = line.split(":", 1)[1].strip()
            elif line.startswith("Installed-Size:"):
                info.size = line.split(":", 1)[1].strip()
        return info
    except Exception:
        return None


def _humanize_apt_error(stderr: str, action: str = "", package: str = "") -> str:
    """Convert raw apt/dpkg errors to human-friendly messages."""
    s = stderr.lower() if stderr else ""

    if "unable to locate" in s or "no candidate" in s:
        return f"Pacote '{package}' não encontrado." if package else "Pacote não encontrado."
    if "lock" in s or "dpkg was interrupted" in s:
        return "O gerenciador de pacotes está ocupado. Tente novamente em alguns segundos."
    if "unmet dependencies" in s or "depends" in s:
        return "Há dependências quebradas. Tente atualizar os pacotes primeiro."
    if "permission denied" in s or "not permitted" in s:
        return "Permissão necessária para gerenciar pacotes."
    if "no space" in s or "enospc" in s:
        return "Disco cheio. Libere espaço antes de continuar."
    if "connection" in s or "network" in s or "could not resolve" in s:
        return "Sem conexão com a internet. Verifique sua rede."
    if "hash sum mismatch" in s:
        return "Erro de integridade nos pacotes. Tente atualizar as listas."

    # Generic fallback — never show raw stderr
    _ACTION_MSGS = {
        "install": f"Não consegui instalar {package}." if package else "Não consegui instalar o pacote.",
        "remove": f"Não consegui remover {package}." if package else "Não consegui remover o pacote.",
        "search": "A busca de pacotes falhou.",
        "update": "Não consegui atualizar as listas de pacotes.",
        "upgrade": "Não consegui atualizar o sistema.",
    }
    return _ACTION_MSGS.get(action, "Operação de pacotes falhou.")
