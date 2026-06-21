"""Tests for cios.core.plan_executor.PlanExecutor."""

from unittest.mock import MagicMock, patch

import pytest

from cios.core.executor import ExecResult, Executor
from cios.core.plan_executor import PlanExecutor
from cios.core.privilege import ElevationResult, PrivilegeManager
from cios.core.task_queue import TaskManager


@pytest.fixture
def mock_executor():
    """Provide a mocked Executor."""
    mock = MagicMock(spec=Executor)
    return mock


@pytest.fixture
def mock_privilege():
    """Provide a mocked PrivilegeManager."""
    mock = MagicMock(spec=PrivilegeManager)
    mock.needs_elevation = MagicMock(return_value=False)
    mock.password_required = MagicMock(return_value=False)
    return mock


@pytest.fixture
def mock_task_manager():
    """Provide a mocked TaskManager."""
    mock = MagicMock(spec=TaskManager)
    mock.submit = MagicMock(return_value="task-abc123")
    return mock


@pytest.fixture
def plan_executor(mock_executor, mock_privilege, mock_task_manager):
    """Provide a PlanExecutor with mocked dependencies."""
    return PlanExecutor(
        executor=mock_executor,
        privilege=mock_privilege,
        task_manager=mock_task_manager,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  execute_sync tests
# ═══════════════════════════════════════════════════════════════════════════


def test_execute_sync_success(plan_executor, mock_executor, mock_privilege):
    """All steps succeed — verify results are recorded."""
    mock_privilege.needs_elevation.return_value = False
    mock_executor.run.return_value = ExecResult(
        command="echo hi",
        returncode=0,
        stdout="hi",
        stderr="",
        duration=0.1,
    )

    result = plan_executor.execute_sync(
        steps=["echo hi", "echo world"],
        explanation="Test plan",
    )

    assert result.status == "success"
    assert len(result.step_results) == 2
    assert all(r.success for r in result.step_results)
    assert mock_executor.run.call_count == 2


def test_execute_sync_fail_fast(plan_executor, mock_executor, mock_privilege):
    """First step fails — second step is NOT executed."""
    mock_privilege.needs_elevation.return_value = False
    mock_executor.run.return_value = ExecResult(
        command="failing-cmd",
        returncode=1,
        stdout="",
        stderr="command not found",
        duration=0.1,
    )

    result = plan_executor.execute_sync(
        steps=["failing-cmd", "echo should-not-run"],
        explanation="Fail fast test",
    )

    assert result.status == "error"
    assert len(result.step_results) == 1
    assert result.step_results[0].success is False
    # Only 1 call — second step never executed
    assert mock_executor.run.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════
#  needs_password tests
# ═══════════════════════════════════════════════════════════════════════════


def test_needs_password_true(plan_executor, mock_privilege):
    """Steps needing root + password_required → returns True."""
    mock_privilege.needs_elevation.return_value = True
    mock_privilege.password_required.return_value = True

    assert plan_executor.needs_password(["apt-get update"]) is True


def test_needs_password_false_no_root(plan_executor, mock_privilege):
    """Non-root steps → always returns False."""
    mock_privilege.needs_elevation.return_value = False

    assert plan_executor.needs_password(["echo hello", "ls -la"]) is False
    # password_required should not even be called
    mock_privilege.password_required.assert_not_called()


def test_needs_password_false_nopasswd(plan_executor, mock_privilege):
    """Root steps but NOPASSWD configured → returns False."""
    mock_privilege.needs_elevation.return_value = True
    mock_privilege.password_required.return_value = False

    assert plan_executor.needs_password(["apt-get update"]) is False


# ═══════════════════════════════════════════════════════════════════════════
#  empty plan tests
# ═══════════════════════════════════════════════════════════════════════════


def test_empty_plan(plan_executor):
    """execute_sync with empty list returns immediately with status='success'."""
    result = plan_executor.execute_sync(steps=[], explanation="Nothing to do")

    assert result.status == "success"
    assert result.steps == []
    assert result.step_results == []


# ═══════════════════════════════════════════════════════════════════════════
#  background dispatch tests
# ═══════════════════════════════════════════════════════════════════════════


def test_execute_background(plan_executor, mock_privilege, mock_task_manager):
    """execute() dispatches to task_manager and returns status='background' with task_id."""
    mock_privilege.needs_elevation.return_value = False

    result = plan_executor.execute(
        steps=["echo hello"],
        explanation="Background test",
    )

    assert result.status == "background"
    assert result.task_id == "task-abc123"
    mock_task_manager.submit.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
#  password gate tests
# ═══════════════════════════════════════════════════════════════════════════


def test_execute_needs_password_gate(plan_executor, mock_privilege):
    """When password needed but not provided, returns status='needs_password'."""
    mock_privilege.needs_elevation.return_value = True
    mock_privilege.password_required.return_value = True

    result = plan_executor.execute(
        steps=["apt-get install curl"],
        explanation="Install curl",
        password="",
    )

    assert result.status == "needs_password"
    assert result.summary  # Non-empty prompt
    assert result.step_results == []


# ═══════════════════════════════════════════════════════════════════════════
#  sudo prefix handling tests
# ═══════════════════════════════════════════════════════════════════════════


def test_sudo_prefix_stripped(plan_executor, mock_executor, mock_privilege):
    """'sudo apt-get update' → actual_cmd is 'apt-get update' routed to run_elevated."""
    # needs_elevation returns True for "sudo apt-get update"
    mock_privilege.needs_elevation.return_value = True
    mock_privilege.run_elevated.return_value = ElevationResult(
        success=True,
        stdout="updated",
        stderr="",
        returncode=0,
    )

    result = plan_executor.execute_sync(
        steps=["sudo apt-get update"],
        explanation="Sudo prefix test",
    )

    assert result.status == "success"
    # run_elevated should be called with the stripped command
    mock_privilege.run_elevated.assert_called_once()
    call_args = mock_privilege.run_elevated.call_args
    assert call_args[0][0] == "apt-get update"  # sudo prefix stripped


# ═══════════════════════════════════════════════════════════════════════════
#  handle_workflow_start delegation test
# ═══════════════════════════════════════════════════════════════════════════


def test_handle_workflow_start_delegates():
    """handle_workflow_start delegates to workflow_start skill and maps result correctly."""
    from cios.skills.dev_start import WorkflowResult

    mock_workflow_result = WorkflowResult(
        steps=["Found: cios", "Type: python", "Opening in code"],
        outcome="success",
        summary="Workspace ready: cios\nEditor opened",
        project_path="/home/user/cios",
        editor_opened=True,
        browser_opened=False,
    )

    with patch(
        "cios.core.handlers.dev.workflow_start", return_value=mock_workflow_result
    ) as mock_ws:
        from cios.core.handlers.dev import handle_workflow_start
        from cios.core.intent_parser import Intent, IntentType

        mock_executor = MagicMock()
        mock_memory = MagicMock()
        intent = Intent(
            type=IntentType.WORKFLOW_START,
            params={"project": "cios"},
            raw_input="abrir cios",
            confidence=1.0,
        )

        result = handle_workflow_start(intent, mock_executor, mock_memory)

    # Verify delegation happened
    mock_ws.assert_called_once_with("cios", mock_executor, mock_memory)

    # Verify PlanResult maps fields from WorkflowResult
    assert result.plan_steps == mock_workflow_result.steps
    assert result.outcome == mock_workflow_result.outcome
    assert result.summary == mock_workflow_result.summary
