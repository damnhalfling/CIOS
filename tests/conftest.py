"""Shared fixtures for CIOS tests."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

# Commands that must NEVER run during tests
_BLOCKED_COMMANDS = {
    "systemctl",
    "loginctl",
    "shutdown",
    "reboot",
    "poweroff",
    "nmcli monitor",
    "pactl subscribe",
    "brightnessctl",
    "xdotool",
    "wmctrl",
    "xbindkeys",
    "sudo apt",
    "apt-get",
    "apt install",
}


def _safe_subprocess_run(original_run):
    """Wrapper that blocks dangerous commands during tests."""

    def safe_run(args, *a, **kw):
        cmd = args if isinstance(args, str) else " ".join(str(x) for x in args)
        for blocked in _BLOCKED_COMMANDS:
            if blocked in cmd:
                # Return a fake "command not found" result instead of running
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=1,
                    stdout="",
                    stderr=f"BLOCKED IN TEST: {cmd}",
                )
        return original_run(args, *a, **kw)

    return safe_run


def _safe_subprocess_popen(original_popen):
    """Wrapper that blocks dangerous Popen calls during tests."""

    def safe_popen(args, *a, **kw):
        cmd = args if isinstance(args, str) else " ".join(str(x) for x in args)
        for blocked in _BLOCKED_COMMANDS:
            if blocked in cmd:
                # Return a mock process that does nothing
                mock = MagicMock()
                mock.stdout = iter([])
                mock.stderr = MagicMock()
                mock.returncode = 1
                mock.pid = 0
                mock.wait = MagicMock(return_value=1)
                mock.terminate = MagicMock()
                mock.kill = MagicMock()
                mock.communicate = MagicMock(return_value=("", f"BLOCKED IN TEST: {cmd}"))
                return mock
        return original_popen(args, *a, **kw)

    return safe_popen


@pytest.fixture(autouse=True)
def isolate_home(tmp_path):
    """Ensure tests never touch the real home directory or run dangerous commands."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    cios_home = fake_home / ".cios"
    cios_home.mkdir()

    original_run = subprocess.run
    original_popen = subprocess.Popen

    with patch.dict(
        os.environ,
        {
            "HOME": str(fake_home),
            "CIOS_HOME": str(cios_home),
        },
    ):
        # Create required subdirectories
        (cios_home / "logs").mkdir(exist_ok=True)

        with (
            patch("cios.core.config.CIOS_HOME", cios_home),
            patch("cios.core.config.DB_PATH", cios_home / "memory.db"),
            patch("cios.core.config.LOG_DIR", cios_home / "logs"),
            patch("cios.core.config.SETTINGS_PATH", cios_home / "settings.json"),
            patch("subprocess.run", _safe_subprocess_run(original_run)),
            patch("subprocess.Popen", _safe_subprocess_popen(original_popen)),
            patch("cios.infra.deps.check_and_install_deps", return_value=[]),
            patch("cios.infra.deps._try_install", return_value=True),
            patch("cios.infra.deps._run_apt", return_value=True),
        ):
            yield fake_home


@pytest.fixture
def executor():
    """Provide a real Executor instance (safe — blocked commands are intercepted)."""
    from cios.core.executor import Executor

    return Executor()
