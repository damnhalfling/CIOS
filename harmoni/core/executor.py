"""Safe shell executor with timeout, streaming output, and error capture."""

import os
import subprocess
import signal
import time
from dataclasses import dataclass
from typing import Optional

from harmoni.core.config import COMMAND_TIMEOUT_SECONDS


@dataclass
class ExecResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out


class Executor:
    """Execute shell commands safely with timeout and capture."""

    # Commands that are never allowed
    BLOCKED = frozenset(["rm -rf /", "mkfs", "dd if=/dev/zero", ":(){:|:&};:"])

    def run(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: Optional[int] = None,
        env: Optional[dict] = None,
    ) -> ExecResult:
        """Run a shell command and return structured result."""
        timeout = timeout or COMMAND_TIMEOUT_SECONDS

        # Safety check
        for blocked in self.BLOCKED:
            if blocked in command:
                return ExecResult(
                    command=command,
                    returncode=1,
                    stdout="",
                    stderr=f"BLOCKED: dangerous command pattern '{blocked}'",
                    duration=0.0,
                )

        merged_env = {**os.environ, **(env or {})}
        start = time.monotonic()

        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                env=merged_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = time.monotonic() - start
            return ExecResult(
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration=duration,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return ExecResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration=duration,
                timed_out=True,
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ExecResult(
                command=command,
                returncode=-1,
                stdout="",
                stderr=str(e),
                duration=duration,
            )

    def run_background(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
    ) -> subprocess.Popen:
        """Start a long-running process in the background."""
        merged_env = {**os.environ, **(env or {})}
        return subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid,
        )

    def kill_by_port(self, port: int) -> ExecResult:
        """Kill whatever process is listening on the given port."""
        return self.run(f"fuser -k {port}/tcp 2>/dev/null || lsof -ti:{port} | xargs -r kill -9")

    def find_port_user(self, port: int) -> Optional[str]:
        """Return the PID/name using a port, or None."""
        result = self.run(f"lsof -i:{port} -t 2>/dev/null || fuser {port}/tcp 2>/dev/null")
        output = result.stdout.strip() or result.stderr.strip()
        return output if output else None
