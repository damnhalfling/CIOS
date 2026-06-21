"""Tests for cios.core.privilege.PrivilegeManager."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from cios.core.privilege import PrivilegeManager, _filter_sudo_lines


@pytest.fixture
def priv():
    """Provide a fresh PrivilegeManager instance."""
    return PrivilegeManager()


# ═══════════════════════════════════════════════════════════════════════════
#  needs_elevation tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "command",
    [
        "sudo apt-get install curl",
        "apt-get update",
        "dpkg -i pkg.deb",
        "dpkg --install pkg.deb",
        "apt install curl",
        "systemctl restart nginx",
        "mount /dev/sda1 /mnt",
        "umount /mnt",
    ],
)
def test_needs_elevation_positive(priv, command):
    """Commands that require root should return True."""
    assert priv.needs_elevation(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "echo hello",
        "python app.py",
        "git commit",
        "",
    ],
)
def test_needs_elevation_negative(priv, command):
    """Commands that do NOT require root should return False."""
    assert priv.needs_elevation(command) is False


def test_needs_elevation_pure_function(priv):
    """Calling needs_elevation twice with same input returns same result (pure function)."""
    cmd = "apt-get install vim"
    result1 = priv.needs_elevation(cmd)
    result2 = priv.needs_elevation(cmd)
    assert result1 == result2 is True

    cmd2 = "echo hello"
    result3 = priv.needs_elevation(cmd2)
    result4 = priv.needs_elevation(cmd2)
    assert result3 == result4 is False


# ═══════════════════════════════════════════════════════════════════════════
#  password_required tests
# ═══════════════════════════════════════════════════════════════════════════


def test_password_required_nopasswd(priv):
    """When sudo -n true exits 0, password is NOT required."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("cios.core.privilege.subprocess.run", return_value=mock_result):
        assert priv.password_required() is False


def test_password_required_needs_password(priv):
    """When sudo -n true exits non-zero, password IS required."""
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("cios.core.privilege.subprocess.run", return_value=mock_result):
        assert priv.password_required() is True


def test_password_required_timeout(priv):
    """When sudo -n true raises TimeoutExpired, password IS required (fail-safe)."""
    with patch(
        "cios.core.privilege.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="sudo -n true", timeout=3),
    ):
        assert priv.password_required() is True


# ═══════════════════════════════════════════════════════════════════════════
#  run_elevated tests
# ═══════════════════════════════════════════════════════════════════════════


def test_run_elevated_with_password(priv):
    """With password: uses sudo -S, password in stdin, env vars set."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "installed ok"
    mock_proc.stderr = ""

    with patch("cios.core.privilege.subprocess.run", return_value=mock_proc) as mock_run:
        result = priv.run_elevated("apt-get install curl", password="s3cr3t")

    assert result.success is True
    assert result.stdout == "installed ok"

    # Verify call arguments
    call_args = mock_run.call_args
    cmd_args = call_args[0][0]
    assert cmd_args[0] == "sudo"
    assert cmd_args[1] == "-S"
    assert "s3cr3t" not in " ".join(cmd_args)  # password NOT in args

    # Verify password passed via stdin
    assert call_args[1]["input"] == "s3cr3t\n"

    # Verify env vars
    env = call_args[1]["env"]
    assert env["DEBIAN_FRONTEND"] == "noninteractive"
    assert env["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"


def test_run_elevated_without_password(priv):
    """Without password: uses sudo -n (non-interactive)."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "done"
    mock_proc.stderr = ""

    with patch("cios.core.privilege.subprocess.run", return_value=mock_proc) as mock_run:
        result = priv.run_elevated("systemctl status nginx", password="")

    assert result.success is True
    call_args = mock_run.call_args
    cmd_args = call_args[0][0]
    assert cmd_args[0] == "sudo"
    assert cmd_args[1] == "-n"
    assert call_args[1]["input"] is None


def test_run_elevated_timeout(priv):
    """When subprocess raises TimeoutExpired, returns success=False, returncode=-1."""
    with patch(
        "cios.core.privilege.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="sudo -n bash -c ...", timeout=120),
    ):
        result = priv.run_elevated("sleep 999", password="")

    assert result.success is False
    assert result.returncode == -1
    assert "timed out" in result.stderr.lower()


# ═══════════════════════════════════════════════════════════════════════════
#  _filter_sudo_lines tests
# ═══════════════════════════════════════════════════════════════════════════


def test_sudo_lines_filtered_from_stderr():
    """[sudo] prompt lines should be removed from stderr output."""
    stderr = "[sudo] password for user:\nE: Unable to locate package\nDone."
    filtered = _filter_sudo_lines(stderr)
    assert "[sudo]" not in filtered
    assert "E: Unable to locate package" in filtered
    assert "Done." in filtered
