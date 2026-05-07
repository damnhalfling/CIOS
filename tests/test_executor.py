"""Tests for the Executor module."""

import pytest

from cios.core.executor import Executor, ExecResult


class TestExecResult:
    """ExecResult dataclass behavior."""

    def test_success_when_returncode_zero(self):
        r = ExecResult(command="echo hi", returncode=0, stdout="hi", stderr="", duration=0.1)
        assert r.success is True

    def test_failure_when_returncode_nonzero(self):
        r = ExecResult(command="false", returncode=1, stdout="", stderr="error", duration=0.1)
        assert r.success is False

    def test_failure_when_timed_out(self):
        r = ExecResult(command="sleep 999", returncode=0, stdout="", stderr="", duration=5.0, timed_out=True)
        assert r.success is False


class TestExecutor:
    """Executor command execution."""

    def test_run_simple_command(self, executor):
        result = executor.run("echo hello")
        assert result.success
        assert "hello" in result.stdout

    def test_run_failing_command(self, executor):
        result = executor.run("false")
        assert not result.success
        assert result.returncode != 0

    def test_run_captures_stderr(self, executor):
        result = executor.run("echo error >&2")
        assert "error" in result.stderr

    def test_run_with_timeout(self, executor):
        result = executor.run("sleep 10", timeout=1)
        assert result.timed_out
        assert not result.success

    def test_run_with_cwd(self, executor, tmp_path):
        result = executor.run("pwd", cwd=str(tmp_path))
        assert result.success
        assert str(tmp_path) in result.stdout

    def test_run_with_env(self, executor):
        result = executor.run("echo $MY_VAR", env={"MY_VAR": "test_value"})
        assert result.success
        assert "test_value" in result.stdout

    def test_blocked_commands(self, executor):
        result = executor.run("rm -rf /")
        assert not result.success
        assert "BLOCKED" in result.stderr

    def test_blocked_fork_bomb(self, executor):
        result = executor.run(":(){:|:&};:")
        assert not result.success
        assert "BLOCKED" in result.stderr

    def test_duration_tracked(self, executor):
        result = executor.run("sleep 0.1")
        assert result.duration >= 0.1

    def test_kill_by_port_runs(self, executor):
        # Just verify it doesn't crash — port likely not in use
        result = executor.kill_by_port(59999)
        # May succeed or fail depending on system, but shouldn't raise
        assert isinstance(result, ExecResult)

    def test_find_port_user_empty(self, executor):
        # Port 59999 is unlikely to be in use
        result = executor.find_port_user(59999)
        # Should return None or empty string
        assert result is None or result == ""
