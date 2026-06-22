"""Property-based tests for Dev Start workflow.

Feature: produto-percebido
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.executor import ExecResult
from cios.skills.dev_start import ProjectInfo, execute_dev_start

# --- Strategies ---

_project_type = st.sampled_from(["node", "python", "unknown"])
_port = st.integers(min_value=1024, max_value=65535)
_dep_state = st.sampled_from(["installed", "not_installed"])
_port_state = st.sampled_from(["free", "occupied"])


def _build_project_info(proj_type: str, port: int) -> ProjectInfo:
    """Build a ProjectInfo for the given type and port."""
    if proj_type == "node":
        return ProjectInfo(
            type="node",
            root="/tmp/test-project",
            start_command="npm run dev",
            install_command="npm install",
            port=port,
            package_manager="npm",
        )
    elif proj_type == "python":
        return ProjectInfo(
            type="python",
            root="/tmp/test-project",
            start_command="python app.py",
            install_command="pip install -r requirements.txt",
            port=port,
        )
    else:
        return ProjectInfo(
            type="unknown",
            root="/tmp/test-project",
            start_command="",
            install_command="",
            port=0,
        )


def _make_mock_executor(server_pid: int = 42) -> MagicMock:
    """Create a mock Executor whose background process stays alive."""
    executor = MagicMock()
    executor.run.return_value = ExecResult(
        command="mock",
        returncode=0,
        stdout="ok",
        stderr="",
        duration=0.0,
    )
    mock_proc = MagicMock()
    mock_proc.pid = server_pid
    mock_proc.poll.return_value = None  # server still running
    executor.run_background.return_value = mock_proc
    executor.kill_by_port.return_value = ExecResult(
        command="kill",
        returncode=0,
        stdout="",
        stderr="",
        duration=0.0,
    )
    return executor


# --- Property Tests ---


class TestDevStartWorkflowProperty:
    """Property 1: Dev Start workflow produces correct plan for any project configuration.

    Feature: produto-percebido, Property 1: Dev Start workflow produces correct plan for any project configuration
    """

    @given(
        proj_type=_project_type,
        port=_port,
        dep_state=_dep_state,
        port_state=_port_state,
    )
    @settings(max_examples=20)
    def test_dev_start_plan_correctness(
        self,
        proj_type: str,
        port: int,
        dep_state: str,
        port_state: str,
    ):
        """For any valid ProjectInfo configuration, execute_dev_start produces a
        correct plan: unknown projects fail with a human message, installed deps
        skip install, occupied ports include a port-clearing step, and the final
        step indicates server running or a clear failure reason.

        **Validates: Requirements 1.1, 1.3, 1.5**
        """
        project = _build_project_info(proj_type, port)
        executor = _make_mock_executor()

        deps_installed = dep_state == "installed"
        port_occupied = port_state == "occupied"

        with (
            patch("cios.skills.dev_start.needs_install", return_value=not deps_installed),
            patch("cios.skills.dev_start._is_port_in_use", return_value=port_occupied),
            patch("cios.skills.dev_start._wait_for_port_free", return_value=True),
            patch("cios.skills.dev_start._detect_editor", return_value=None),
            patch("cios.skills.dev_start._open_browser"),
            patch("cios.skills.dev_start.time.sleep"),
        ):
            plan, results, pid = execute_dev_start(executor, project=project)

        # (a) Unknown projects return failure with a human-readable message
        if proj_type == "unknown":
            assert pid is None, "Unknown project should not produce a server PID"
            assert len(plan) >= 1, "Unknown project should produce at least one plan step"
            plan_text = " ".join(plan).lower()
            assert "could not" in plan_text or "not" in plan_text or "unknown" in plan_text, (
                f"Unknown project plan should contain a human-readable failure message, got: {plan}"
            )
            # No further assertions needed for unknown projects
            return

        # (b) Projects with installed deps skip the install step
        if deps_installed:
            install_steps = [
                s for s in plan if "install" in s.lower() or "dependencies" in s.lower()
            ]
            assert len(install_steps) == 0, (
                f"Installed deps should skip install step, but found: {install_steps}"
            )
        else:
            install_steps = [
                s for s in plan if "install" in s.lower() or "dependencies" in s.lower()
            ]
            assert len(install_steps) >= 1, (
                f"Missing deps should include an install step, but plan was: {plan}"
            )

        # (c) Occupied ports include a port-clearing step before server start
        if port_occupied:
            port_steps = [s for s in plan if "port" in s.lower() or "kill" in s.lower()]
            assert len(port_steps) >= 1, (
                f"Occupied port should include a port-clearing step, but plan was: {plan}"
            )
            # The port-clearing step should appear before the server start step
            start_indices = [i for i, s in enumerate(plan) if "starting server" in s.lower()]
            port_indices = [
                i
                for i, s in enumerate(plan)
                if "port" in s.lower() and ("kill" in s.lower() or "in use" in s.lower())
            ]
            if start_indices and port_indices:
                assert min(port_indices) < min(start_indices), (
                    "Port-clearing step should appear before server start step"
                )

        # (d) Final plan step indicates server running or a clear failure reason
        assert len(plan) >= 1, "Plan should have at least one step"
        final_step = plan[-1].lower()
        indicates_running = (
            "running" in final_step
            or "browser" in final_step
            or "editor" in final_step
            or "session" in final_step
        )
        indicates_failure = (
            "fail" in final_step
            or "error" in final_step
            or "could not" in final_step
            or "exited" in final_step
        )
        assert indicates_running or indicates_failure, (
            f"Final plan step should indicate server running or failure, got: '{plan[-1]}'"
        )
