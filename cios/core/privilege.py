"""Unified privilege escalation — single source of truth for root decisions and execution.

Replaces scattered logic from:
- bridge.py _step_needs_root_static()
- bridge.py _needs_sudo_password()
- skills/package_manager.py needs_sudo_password() + _run_privileged()
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from cios.core.executor import ExecResult


@dataclass
class ElevationResult:
    """Result of a privileged command execution."""

    success: bool
    stdout: str
    stderr: str
    returncode: int

    @property
    def exec_result(self) -> ExecResult:
        """Convert to ExecResult for backward compat."""
        return ExecResult(
            command="[privileged]",
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
            duration=0.0,
        )


def _filter_sudo_lines(text: str) -> str:
    """Remove stderr lines containing [sudo] prompts."""
    return "\n".join(line for line in text.splitlines() if "[sudo]" not in line)


# Environment used for all privileged executions
_PRIVILEGED_ENV = {
    "DEBIAN_FRONTEND": "noninteractive",
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
}


class PrivilegeManager:
    """Unified privilege escalation — owns 'does this need root?' and 'how to execute'."""

    ROOT_PATTERNS: tuple[str, ...] = (
        "sudo ",
        "dpkg -i",
        "dpkg --install",
        "apt-get",
        "apt ",
        "systemctl",
        "mount ",
        "umount ",
    )

    def needs_elevation(self, command: str) -> bool:
        """Determine if a shell command needs root privileges.

        Pure function — no side effects.
        """
        cmd = command.strip()
        if not cmd:
            return False
        if cmd.startswith("sudo "):
            return True
        return any(pattern in cmd for pattern in self.ROOT_PATTERNS)

    def password_required(self) -> bool:
        """Check if sudo requires a password (no NOPASSWD configured).

        Fail-safe: returns True on timeout or exception.
        """
        try:
            r = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True,
                timeout=3,
            )
            return r.returncode != 0
        except Exception:
            return True

    def run_elevated(
        self,
        command: str,
        password: str = "",
        timeout: int = 120,
    ) -> ElevationResult:
        """Execute a command with elevated privileges.

        If password is provided, uses sudo -S (reads from stdin).
        If not, uses sudo -n (non-interactive / NOPASSWD).
        Password never appears in command-line arguments.
        """
        env = {**os.environ, **_PRIVILEGED_ENV}

        if password:
            cmd_args = ["sudo", "-S", "bash", "-c", command]
            stdin_data = password + "\n"
        else:
            cmd_args = ["sudo", "-n", "bash", "-c", command]
            stdin_data = None

        try:
            proc = subprocess.run(
                cmd_args,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            return ElevationResult(
                success=proc.returncode == 0,
                stdout=proc.stdout,
                stderr=_filter_sudo_lines(proc.stderr),
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return ElevationResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                returncode=-1,
            )
        except Exception as e:
            return ElevationResult(
                success=False,
                stdout="",
                stderr=str(e),
                returncode=-1,
            )

    def run_elevated_list(
        self,
        commands: list[str],
        password: str = "",
        timeout: int = 120,
    ) -> list[ElevationResult]:
        """Execute multiple commands sequentially with elevation.

        Stops on first failure (fail-fast).
        """
        results: list[ElevationResult] = []
        for cmd in commands:
            result = self.run_elevated(cmd, password=password, timeout=timeout)
            results.append(result)
            if not result.success:
                break
        return results
