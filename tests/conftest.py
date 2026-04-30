"""Shared fixtures for Harmoni tests."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# Commands that must NEVER run during tests
_BLOCKED_COMMANDS = {
    "systemctl", "loginctl", "shutdown", "reboot", "poweroff",
    "nmcli monitor", "pactl subscribe",
    "brightnessctl", "xdotool", "wmctrl", "xbindkeys",
}


def _safe_subprocess_run(original_run):
    """Wrapper that blocks dangerous commands during tests."""
    def safe_run(args, *a, **kw):
        cmd = args if isinstance(args, str) else " ".join(str(x) for x in args)
        for blocked in _BLOCKED_COMMANDS:
            if blocked in cmd:
                # Return a fake "command not found" result instead of running
                return subprocess.CompletedProcess(
                    args=args, returncode=1,
                    stdout="", stderr=f"BLOCKED IN TEST: {cmd}",
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
    harmoni_home = fake_home / ".harmoni"
    harmoni_home.mkdir()

    original_run = subprocess.run
    original_popen = subprocess.Popen

    with patch.dict(os.environ, {
        "HOME": str(fake_home),
        "HARMONI_HOME": str(harmoni_home),
    }):
        # Create required subdirectories
        (harmoni_home / "logs").mkdir(exist_ok=True)

        with patch("harmoni.core.config.HARMONI_HOME", harmoni_home), \
             patch("harmoni.core.config.DB_PATH", harmoni_home / "memory.db"), \
             patch("harmoni.core.config.LOG_DIR", harmoni_home / "logs"), \
             patch("harmoni.core.config.SETTINGS_PATH", harmoni_home / "settings.json"), \
             patch("subprocess.run", _safe_subprocess_run(original_run)), \
             patch("subprocess.Popen", _safe_subprocess_popen(original_popen)):
            yield fake_home


@pytest.fixture
def executor():
    """Provide a real Executor instance (safe — blocked commands are intercepted)."""
    from harmoni.core.executor import Executor
    return Executor()
