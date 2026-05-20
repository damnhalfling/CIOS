"""Runtime dependency checker — ensures required system tools are present.

Runs once on boot. CIOS requires:
- Wayland compositor (cios-shell) — session won't start without it
- Ollama + Mistral model — intent classification won't work without it
- Wayland tools (foot, wl-clipboard) — core UX depends on them
- Network tools (nmcli) — device control depends on it

If critical tools are missing, attempts to install them automatically.
If install fails for critical deps → system cannot operate normally.
Non-critical deps (grim, mpv, ffmpeg) degrade specific features only.
"""

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  DEPENDENCY REGISTRY
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DepInfo:
    """Metadata for a system dependency."""

    binary: str  # Binary name to check via shutil.which
    apt_package: str  # Package to install via apt-get
    feature: str  # Human-readable feature name (PT-BR)
    degraded_msg: str  # Message shown when feature is unavailable
    critical: bool  # If True, core features break without it


# ═══════════════════════════════════════════════════════════════════════════
#  CORE DEPENDENCIES (system does NOT work without these)
# ═══════════════════════════════════════════════════════════════════════════

WAYLAND_REGISTRY: list[DepInfo] = [
    DepInfo(
        binary="foot",
        apt_package="foot",
        feature="Terminal",
        degraded_msg="Terminal indisponível (instale foot)",
        critical=True,
    ),
    DepInfo(
        binary="wl-copy",
        apt_package="wl-clipboard",
        feature="Clipboard",
        degraded_msg="Clipboard indisponível",
        critical=True,
    ),
    DepInfo(
        binary="wl-paste",
        apt_package="wl-clipboard",
        feature="Clipboard",
        degraded_msg="Clipboard indisponível",
        critical=True,
    ),
    DepInfo(
        binary="ollama",
        apt_package="ollama",
        feature="IA local (Ollama + Mistral)",
        degraded_msg="IA indisponível — intent classification não funciona",
        critical=True,
    ),
    DepInfo(
        binary="nmcli",
        apt_package="network-manager",
        feature="Rede",
        degraded_msg="Controle de rede indisponível",
        critical=True,
    ),
]

# ═══════════════════════════════════════════════════════════════════════════
#  FEATURE DEPENDENCIES (specific features degrade without these)
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_REGISTRY: list[DepInfo] = [
    DepInfo(
        binary="pactl",
        apt_package="pulseaudio-utils",
        feature="Áudio (PulseAudio)",
        degraded_msg="Áudio indisponível",
        critical=False,
    ),
    DepInfo(
        binary="wpctl",
        apt_package="wireplumber",
        feature="Áudio (PipeWire)",
        degraded_msg="Áudio indisponível",
        critical=False,
    ),
    DepInfo(
        binary="bluetoothctl",
        apt_package="bluez",
        feature="Bluetooth",
        degraded_msg="Bluetooth indisponível",
        critical=False,
    ),
    DepInfo(
        binary="mpv",
        apt_package="mpv",
        feature="Media Player",
        degraded_msg="Reprodução de mídia indisponível",
        critical=False,
    ),
    DepInfo(
        binary="ffmpeg",
        apt_package="ffmpeg",
        feature="Processamento de vídeo",
        degraded_msg="Thumbnails de vídeo e gravação indisponíveis",
        critical=False,
    ),
    DepInfo(
        binary="grim",
        apt_package="grim",
        feature="Screenshot",
        degraded_msg="Screenshot indisponível",
        critical=False,
    ),
    DepInfo(
        binary="slurp",
        apt_package="slurp",
        feature="Seleção de região",
        degraded_msg="Seleção de região indisponível",
        critical=False,
    ),
]


def _build_registry() -> list[DepInfo]:
    """Build the full dependency registry. Core + feature deps."""
    registry: list[DepInfo] = []
    registry.extend(WAYLAND_REGISTRY)  # critical — system won't work without
    registry.extend(SYSTEM_REGISTRY)  # features — degrade individually
    return registry


# Combined registry (built at check time)
DEPENDENCY_REGISTRY: list[DepInfo] = []

# Module-level state: tracks which tools are missing after check
_missing_tools: set[str] = set()
_degraded_features: dict[str, str] = {}  # binary → degraded_msg


def get_missing_tools() -> set[str]:
    """Return the set of tool binaries that are currently missing."""
    return set(_missing_tools)


def get_degraded_features() -> dict[str, str]:
    """Return mapping of missing binary → human degradation message."""
    return dict(_degraded_features)


def is_tool_available(binary: str) -> bool:
    """Check if a specific tool is available (not in missing set)."""
    return binary not in _missing_tools


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN CHECK
# ═══════════════════════════════════════════════════════════════════════════


def check_and_install_deps() -> list[str]:
    """Check for missing system tools and attempt to install them.

    Returns list of tool binaries that are still missing after attempted install.
    Called once during boot (from bridge or session script).

    Builds the registry dynamically based on session type (Wayland vs X11).

    For each missing tool:
    1. Log which feature is affected
    2. Attempt auto-install via apt-get (if sudo available)
    3. If install fails → log warning with humanized message, track as degraded
    """
    global _missing_tools, _degraded_features, DEPENDENCY_REGISTRY

    # Build registry based on current session type
    DEPENDENCY_REGISTRY = _build_registry()

    missing: list[DepInfo] = []

    for dep in DEPENDENCY_REGISTRY:
        if not shutil.which(dep.binary):
            missing.append(dep)

    if not missing:
        _missing_tools = set()
        _degraded_features = {}
        return []

    # Deduplicate packages to install
    packages_to_install = list(dict.fromkeys(dep.apt_package for dep in missing))
    missing_names = [dep.binary for dep in missing]

    logger.warning(
        "Missing system tools: %s (packages: %s)",
        ", ".join(missing_names),
        ", ".join(packages_to_install),
    )

    # Attempt silent install
    installed = _try_install(packages_to_install)

    if installed:
        logger.info("Auto-installed missing packages: %s", ", ".join(packages_to_install))

    # Re-check what's still missing after install attempt
    still_missing: list[DepInfo] = []
    for dep in missing:
        if not shutil.which(dep.binary):
            still_missing.append(dep)

    # Update module-level state for degraded features
    _missing_tools = {dep.binary for dep in still_missing}
    _degraded_features = {dep.binary: dep.degraded_msg for dep in still_missing}

    # Log humanized warnings for each degraded feature
    for dep in still_missing:
        if dep.critical:
            logger.error(
                "Recurso degradado: %s — %s (instale com: sudo apt install %s)",
                dep.feature,
                dep.degraded_msg,
                dep.apt_package,
            )
        else:
            logger.warning(
                "Recurso degradado: %s — %s (instale com: sudo apt install %s)",
                dep.feature,
                dep.degraded_msg,
                dep.apt_package,
            )

    still_missing_names = [dep.binary for dep in still_missing]

    if still_missing_names:
        critical_missing = [dep.binary for dep in still_missing if dep.critical]
        if critical_missing:
            logger.error(
                "Critical tools missing and could not auto-install: %s. "
                "Some features will be limited. "
                "Fix with: sudo apt install %s",
                ", ".join(critical_missing),
                " ".join(packages_to_install),
            )

    return still_missing_names


# ═══════════════════════════════════════════════════════════════════════════
#  INSTALL STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════


def _try_install(packages: list[str]) -> bool:
    """Attempt to install packages via apt.

    Tries multiple strategies:
    1. Direct apt (works if running as root)
    2. Passwordless sudo (works if NOPASSWD configured)
    Skips pkexec — it blocks the boot waiting for graphical auth.
    """
    pkg_str = " ".join(packages)

    # Strategy 1: direct apt (if we're root)
    if os.geteuid() == 0:
        return _run_apt(f"apt-get install -y -qq {pkg_str}")

    # Strategy 2: passwordless sudo
    if _has_passwordless_sudo():
        return _run_apt(f"sudo apt-get install -y -qq {pkg_str}")

    # Don't try pkexec during boot — it blocks waiting for graphical auth
    # and the session isn't fully up yet. User can install manually later.
    logger.info("Cannot auto-install packages (no root access, skipping pkexec during boot)")
    return False


def _run_apt(command: str) -> bool:
    """Run an apt command."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except Exception as e:
        logger.debug("apt install failed: %s", e)
        return False


def _has_passwordless_sudo() -> bool:
    """Check if current user can run sudo without a password."""
    if not shutil.which("sudo"):
        return False
    try:
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False
