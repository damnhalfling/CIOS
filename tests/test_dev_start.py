"""Unit tests for dev_start skill hardening (Task 1.5).

Tests cover:
- Stale dependency detection (package-lock.json mtime vs node_modules)
- Polling port wait (_wait_for_port_free)
- Editor detection (_detect_editor)
- Browser launch step
- Session persistence after successful Dev Start
"""

import os
import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from harmoni.skills.dev_start import (
    ProjectInfo,
    needs_install,
    _wait_for_port_free,
    _detect_editor,
    execute_dev_start,
)


# ── Stale dependency detection ──────────────────────────────────────────


class TestNeedsInstallStaleDeps:
    """Stale dependency detection via lock file mtime comparison."""

    def test_node_no_node_modules_needs_install(self, tmp_path):
        """Missing node_modules → needs install."""
        (tmp_path / "package.json").write_text("{}")
        project = ProjectInfo(
            type="node", root=str(tmp_path),
            start_command="npm start", install_command="npm install",
            port=3000, package_manager="npm",
        )
        assert needs_install(project) is True

    def test_node_fresh_node_modules_no_install(self, tmp_path):
        """node_modules exists, no lock file → skip install."""
        (tmp_path / "package.json").write_text("{}")
        (tmp_path / "node_modules").mkdir()
        project = ProjectInfo(
            type="node", root=str(tmp_path),
            start_command="npm start", install_command="npm install",
            port=3000, package_manager="npm",
        )
        assert needs_install(project) is False

    def test_node_stale_lock_newer_than_node_modules(self, tmp_path):
        """package-lock.json newer than node_modules → needs install."""
        (tmp_path / "package.json").write_text("{}")
        nm = tmp_path / "node_modules"
        nm.mkdir()
        # Set node_modules mtime to the past
        old_time = time.time() - 100
        os.utime(nm, (old_time, old_time))
        # Create lock file (will have current mtime, which is newer)
        (tmp_path / "package-lock.json").write_text("{}")
        project = ProjectInfo(
            type="node", root=str(tmp_path),
            start_command="npm start", install_command="npm install",
            port=3000, package_manager="npm",
        )
        assert needs_install(project) is True

    def test_node_lock_older_than_node_modules(self, tmp_path):
        """package-lock.json older than node_modules → skip install."""
        (tmp_path / "package.json").write_text("{}")
        lock = tmp_path / "package-lock.json"
        lock.write_text("{}")
        # Set lock file mtime to the past
        old_time = time.time() - 100
        os.utime(lock, (old_time, old_time))
        # Create node_modules (will have current mtime, which is newer)
        (tmp_path / "node_modules").mkdir()
        project = ProjectInfo(
            type="node", root=str(tmp_path),
            start_command="npm start", install_command="npm install",
            port=3000, package_manager="npm",
        )
        assert needs_install(project) is False

    def test_python_no_venv_needs_install(self, tmp_path):
        """Python project without venv → needs install."""
        project = ProjectInfo(
            type="python", root=str(tmp_path),
            start_command="python app.py", install_command="pip install -r requirements.txt",
            port=8000,
        )
        assert needs_install(project) is True

    def test_python_with_venv_no_install(self, tmp_path):
        """Python project with .venv → skip install."""
        (tmp_path / ".venv").mkdir()
        project = ProjectInfo(
            type="python", root=str(tmp_path),
            start_command="python app.py", install_command="pip install -r requirements.txt",
            port=8000,
        )
        assert needs_install(project) is False


# ── Polling port wait ───────────────────────────────────────────────────


class TestWaitForPortFree:
    """Polling loop replaces fixed time.sleep(2)."""

    @patch("harmoni.skills.dev_start._is_port_in_use", return_value=False)
    def test_port_already_free_returns_immediately(self, mock_port):
        """If port is free on first check, return True immediately."""
        start = time.monotonic()
        result = _wait_for_port_free(3000, timeout=3.0, interval=0.2)
        elapsed = time.monotonic() - start
        assert result is True
        assert elapsed < 0.5  # Should be nearly instant

    @patch("harmoni.skills.dev_start._is_port_in_use", side_effect=[True, True, False])
    def test_port_becomes_free_after_retries(self, mock_port):
        """Port becomes free after a few checks → returns True."""
        result = _wait_for_port_free(3000, timeout=3.0, interval=0.05)
        assert result is True

    @patch("harmoni.skills.dev_start._is_port_in_use", return_value=True)
    def test_port_never_free_returns_false(self, mock_port):
        """Port stays occupied → returns False after timeout."""
        start = time.monotonic()
        result = _wait_for_port_free(3000, timeout=0.3, interval=0.05)
        elapsed = time.monotonic() - start
        assert result is False
        assert elapsed >= 0.25  # Should have waited close to timeout


# ── Editor detection ────────────────────────────────────────────────────


class TestDetectEditor:
    """Editor detection: code > codium > VISUAL > EDITOR > None."""

    @patch("shutil.which", side_effect=lambda cmd: "/usr/bin/code" if cmd == "code" else None)
    def test_detects_vscode(self, mock_which):
        assert _detect_editor() == "code"

    @patch("shutil.which", side_effect=lambda cmd: "/usr/bin/codium" if cmd == "codium" else None)
    def test_detects_codium(self, mock_which):
        assert _detect_editor() == "codium"

    @patch("shutil.which", return_value=None)
    @patch.dict(os.environ, {"VISUAL": "vim"}, clear=False)
    def test_falls_back_to_visual_env(self, mock_which):
        # shutil.which returns None for code/codium, but we need it to
        # return something for "vim"
        def which_side_effect(cmd):
            if cmd == "vim":
                return "/usr/bin/vim"
            return None
        mock_which.side_effect = which_side_effect
        assert _detect_editor() == "vim"

    @patch("shutil.which", return_value=None)
    @patch.dict(os.environ, {"VISUAL": "", "EDITOR": ""}, clear=False)
    def test_returns_none_when_no_editor(self, mock_which):
        assert _detect_editor() is None


# ── Full execute_dev_start with new steps ───────────────────────────────


class TestExecuteDevStartHardened:
    """Integration tests for the hardened execute_dev_start flow."""

    def _make_mock_executor(self, server_pid=12345):
        """Create a mock executor with a fake background process."""
        executor = MagicMock()
        executor.run.return_value = MagicMock(
            success=True, stdout="ok", stderr="", returncode=0,
        )
        mock_proc = MagicMock()
        mock_proc.pid = server_pid
        mock_proc.poll.return_value = None  # Server still running
        executor.run_background.return_value = mock_proc
        return executor

    @patch("harmoni.skills.dev_start._open_browser")
    @patch("harmoni.skills.dev_start._open_editor")
    @patch("harmoni.skills.dev_start._detect_editor", return_value="code")
    @patch("harmoni.skills.dev_start._is_port_in_use", return_value=False)
    @patch("harmoni.skills.dev_start.time.sleep")
    def test_editor_and_browser_steps_in_plan(
        self, mock_sleep, mock_port, mock_detect_ed, mock_open_ed, mock_open_br,
    ):
        """Successful dev start includes editor_open and browser_open steps."""
        executor = self._make_mock_executor()
        project = ProjectInfo(
            type="node", root="/tmp/myproject",
            start_command="npm run dev", install_command="npm install",
            port=3000, package_manager="npm",
        )
        # node_modules exists so no install needed
        with patch("harmoni.skills.dev_start.needs_install", return_value=False):
            plan, results, pid = execute_dev_start(executor, project=project)

        assert pid == 12345
        assert any("Editor opened" in s for s in plan)
        assert any("Browser opened" in s for s in plan)
        mock_open_ed.assert_called_once_with("code", "/tmp/myproject")
        mock_open_br.assert_called_once_with("http://localhost:3000")

    @patch("harmoni.skills.dev_start._open_browser")
    @patch("harmoni.skills.dev_start._open_editor")
    @patch("harmoni.skills.dev_start._detect_editor", return_value=None)
    @patch("harmoni.skills.dev_start._is_port_in_use", return_value=False)
    @patch("harmoni.skills.dev_start.time.sleep")
    def test_no_editor_skips_editor_step(
        self, mock_sleep, mock_port, mock_detect_ed, mock_open_ed, mock_open_br,
    ):
        """When no editor is detected, the editor step is skipped."""
        executor = self._make_mock_executor()
        project = ProjectInfo(
            type="node", root="/tmp/myproject",
            start_command="npm run dev", install_command="npm install",
            port=3000, package_manager="npm",
        )
        with patch("harmoni.skills.dev_start.needs_install", return_value=False):
            plan, results, pid = execute_dev_start(executor, project=project)

        assert pid == 12345
        assert not any("Editor opened" in s for s in plan)
        # Browser should still open
        assert any("Browser opened" in s for s in plan)
        mock_open_ed.assert_not_called()

    @patch("harmoni.skills.dev_start._open_browser")
    @patch("harmoni.skills.dev_start._open_editor")
    @patch("harmoni.skills.dev_start._detect_editor", return_value="code")
    @patch("harmoni.skills.dev_start._is_port_in_use", return_value=False)
    @patch("harmoni.skills.dev_start.time.sleep")
    def test_session_persisted_to_memory(
        self, mock_sleep, mock_port, mock_detect_ed, mock_open_ed, mock_open_br,
    ):
        """Successful dev start persists SessionContext to Memory."""
        from harmoni.core.memory import Memory, SessionContext

        executor = self._make_mock_executor(server_pid=9999)
        project = ProjectInfo(
            type="node", root="/tmp/myproject",
            start_command="npm run dev", install_command="npm install",
            port=3000, package_manager="npm",
        )
        memory = MagicMock(spec=Memory)

        with patch("harmoni.skills.dev_start.needs_install", return_value=False):
            plan, results, pid = execute_dev_start(
                executor, project=project, memory=memory,
            )

        assert pid == 9999
        assert any("Session saved" in s for s in plan)
        memory.save_session.assert_called_once()
        ctx = memory.save_session.call_args[0][0]
        assert isinstance(ctx, SessionContext)
        assert ctx.project_name == "myproject"
        assert ctx.project_path == "/tmp/myproject"
        assert ctx.project_type == "node"
        assert ctx.editor_command == "code"
        assert ctx.server_pid == 9999
        assert ctx.server_port == 3000
        assert ctx.browser_url == "http://localhost:3000"
        assert ctx.start_command == "npm run dev"

    @patch("harmoni.skills.dev_start._open_browser")
    @patch("harmoni.skills.dev_start._open_editor")
    @patch("harmoni.skills.dev_start._detect_editor", return_value="code")
    @patch("harmoni.skills.dev_start._is_port_in_use", return_value=False)
    @patch("harmoni.skills.dev_start.time.sleep")
    def test_no_memory_skips_session_persist(
        self, mock_sleep, mock_port, mock_detect_ed, mock_open_ed, mock_open_br,
    ):
        """When memory is None, session persistence is skipped gracefully."""
        executor = self._make_mock_executor()
        project = ProjectInfo(
            type="node", root="/tmp/myproject",
            start_command="npm run dev", install_command="npm install",
            port=3000, package_manager="npm",
        )
        with patch("harmoni.skills.dev_start.needs_install", return_value=False):
            plan, results, pid = execute_dev_start(
                executor, project=project, memory=None,
            )

        assert pid == 12345
        assert not any("Session saved" in s for s in plan)

    @patch("harmoni.skills.dev_start._wait_for_port_free", return_value=True)
    @patch("harmoni.skills.dev_start._open_browser")
    @patch("harmoni.skills.dev_start._open_editor")
    @patch("harmoni.skills.dev_start._detect_editor", return_value="code")
    @patch("harmoni.skills.dev_start._is_port_in_use", return_value=True)
    @patch("harmoni.skills.dev_start.time.sleep")
    def test_port_conflict_uses_polling(
        self, mock_sleep, mock_port_in_use, mock_detect_ed,
        mock_open_ed, mock_open_br, mock_wait,
    ):
        """Port conflict resolution uses polling instead of fixed sleep."""
        executor = self._make_mock_executor()
        # After kill, _is_port_in_use is still True (mocked), but
        # _wait_for_port_free returns True (port freed via polling)
        project = ProjectInfo(
            type="node", root="/tmp/myproject",
            start_command="npm run dev", install_command="npm install",
            port=3000, package_manager="npm",
        )
        with patch("harmoni.skills.dev_start.needs_install", return_value=False):
            plan, results, pid = execute_dev_start(executor, project=project)

        # Verify polling was used (not time.sleep(2))
        mock_wait.assert_called()
        # The old fixed sleep(2) should NOT have been called
        # (time.sleep is only called for the verify step, not port wait)
