"""Runtime dependency checker — ensures required system tools are present.

Runs once on boot. If critical tools are missing, attempts to install them
automatically (Harmoni is installed as root, so the venv has access).

For tools that need apt, uses the package_manager skill with passwordless
sudo if available, or logs a clear warning.

This is a safety net — the .deb Depends field should handle most cases,
but upgrades from older versions or manual installs may miss new deps.
"""

import logging
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Tools required for full functionality
# (binary_name, apt_package, critical)
# critical=True means core features break without it
_REQUIRED_TOOLS = [
    ("wmctrl",   "wmctrl",               True),
    ("xdotool",  "xdotool",              True),
    ("xrandr",   "x11-xserver-utils",    True),
    ("xprop",    "x11-utils",            False),
    ("xset",     "x11-xserver-utils",    False),
    ("i3lock",   "i3lock",               False),
]


def check_and_install_deps() -> list[str]:
    """Check for missing system tools and attempt to install them.

    Returns list of tools that are still missing after attempted install.
    Called once during boot (from bridge or session script).
    """
    missing: list[tuple[str, str, bool]] = []

    for binary, package, critical in _REQUIRED_TOOLS:
        if not shutil.which(binary):
            missing.append((binary, package, critical))

    if not missing:
        return []

    # Deduplicate packages
    packages_to_install = list(dict.fromkeys(pkg for _, pkg, _ in missing))
    missing_names = [b for b, _, _ in missing]

    logger.warning(
        "Missing system tools: %s (packages: %s)",
        ", ".join(missing_names),
        ", ".join(packages_to_install),
    )

    # Attempt silent install
    installed = _try_install(packages_to_install)

    if installed:
        logger.info("Auto-installed missing packages: %s", ", ".join(packages_to_install))
        # Re-check what's still missing
        still_missing = [b for b, _, _ in missing if not shutil.which(b)]
        if still_missing:
            logger.warning("Still missing after install: %s", ", ".join(still_missing))
        return still_missing

    # Install failed — log clearly
    critical_missing = [b for b, _, c in missing if c]
    if critical_missing:
        logger.error(
            "Critical tools missing and could not auto-install: %s. "
            "Some features will be limited. "
            "Fix with: sudo apt install %s",
            ", ".join(critical_missing),
            " ".join(packages_to_install),
        )

    return missing_names


def _try_install(packages: list[str]) -> bool:
    """Attempt to install packages via apt.

    Tries multiple strategies:
    1. Direct apt (works if running as root or in postinst)
    2. Passwordless sudo (works if NOPASSWD configured)
    3. pkexec (works in graphical session with polkit)
    """
    pkg_str = " ".join(packages)

    # Strategy 1: direct apt (if we're root)
    import os
    if os.geteuid() == 0:
        return _run_apt(f"apt-get install -y -qq {pkg_str}")

    # Strategy 2: passwordless sudo
    if _has_passwordless_sudo():
        return _run_apt(f"sudo apt-get install -y -qq {pkg_str}")

    # Strategy 3: pkexec (graphical sudo prompt)
    if shutil.which("pkexec"):
        try:
            result = subprocess.run(
                ["pkexec", "apt-get", "install", "-y", "-qq"] + packages,
                capture_output=True, text=True, timeout=120,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug("pkexec install failed: %s", e)

    logger.info("Cannot auto-install packages (no root access)")
    return False


def _run_apt(command: str) -> bool:
    """Run an apt command."""
    try:
        result = subprocess.run(
            command, shell=True,
            capture_output=True, text=True, timeout=120,
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
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False
