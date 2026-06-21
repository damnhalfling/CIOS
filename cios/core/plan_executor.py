"""PlanExecutor — executes Intelligence-generated multi-step shell plans.

Handles password request flow, background dispatch via TaskManager,
and progress feedback. Extracted from bridge.py _execute_plan_steps()
and _run_plan_steps().
"""

from __future__ import annotations

from dataclasses import dataclass

from cios.core.executor import Executor
from cios.core.privilege import ElevationResult, PrivilegeManager
from cios.core.task_queue import Task, TaskManager


@dataclass
class PlanStepResult:
    """Result of a single plan step."""

    command: str  # Truncated to 80 chars
    success: bool
    output: str  # Truncated stdout or error message


@dataclass
class PlanExecutionResult:
    """Result of executing an entire plan."""

    steps: list[str]
    step_results: list[PlanStepResult]
    status: str  # "success" | "error" | "background" | "needs_password"
    summary: str
    task_id: str | None = None


class PlanExecutor:
    """Executes Intelligence-generated execution plans.

    Responsibilities:
    - Analyze plan steps for privilege requirements
    - Request password via callback when needed
    - Dispatch long-running plans to background (via TaskManager)
    - Track progress per-step
    - Report results in UI-friendly format
    """

    def __init__(
        self,
        executor: Executor,
        privilege: PrivilegeManager,
        task_manager: TaskManager,
    ) -> None:
        self._executor = executor
        self._privilege = privilege
        self._task_manager = task_manager

    def needs_password(self, steps: list[str]) -> bool:
        """Check if any step in the plan requires a password.

        Returns True if at least one step needs elevation AND
        sudo requires a password.
        """
        needs_root = any(self._privilege.needs_elevation(s) for s in steps)
        if not needs_root:
            return False
        return self._privilege.password_required()

    def execute(
        self,
        steps: list[str],
        explanation: str,
        password: str = "",
    ) -> PlanExecutionResult:
        """Execute a plan's steps, dispatching to background.

        Flow:
        1. Empty plan → return success immediately
        2. Check if any step needs elevation
        3. If needs password and none provided → return needs_password status
        4. Submit task to TaskManager for background execution
        5. Return immediately with task_id
        """
        if not steps:
            return PlanExecutionResult(
                steps=[],
                step_results=[],
                status="success",
                summary=explanation or "Nenhum passo a executar",
            )

        # Check privilege requirements
        needs_root = any(self._privilege.needs_elevation(s) for s in steps)

        if needs_root and self._privilege.password_required() and not password:
            return PlanExecutionResult(
                steps=[],
                step_results=[],
                status="needs_password",
                summary=f"{explanation}\n\nPreciso da tua senha pra executar:",
            )

        # Create background task
        task = Task(
            description=explanation[:60] or "Executando plano",
            context="plan_execution",
        )

        # Define execution function for TaskManager
        def execute_fn(t: Task) -> dict:
            result = self._execute_steps_sync(steps, password, task=t)
            return {
                "steps": result.steps,
                "result": result.summary,
                "status": result.status,
                "voice_mode": "full",
            }

        task._execute_fn = execute_fn
        task_id = self._task_manager.submit(task)

        return PlanExecutionResult(
            steps=[f"⟳ {explanation[:60]}"],
            step_results=[],
            status="background",
            summary=f"Executando: {explanation[:80]}",
            task_id=task_id,
        )

    def execute_sync(
        self,
        steps: list[str],
        explanation: str,
        password: str = "",
    ) -> PlanExecutionResult:
        """Execute plan steps synchronously (for tests or small plans).

        Runs all steps in the current thread. Used by tests to verify
        plan execution without background threads.
        """
        if not steps:
            return PlanExecutionResult(
                steps=[],
                step_results=[],
                status="success",
                summary=explanation or "Nenhum passo a executar",
            )

        return self._execute_steps_sync(steps, password)

    def _execute_steps_sync(
        self,
        steps: list[str],
        password: str,
        task: Task | None = None,
    ) -> PlanExecutionResult:
        """Internal: run steps sequentially with progress reporting.

        For each step:
        - Strip 'sudo ' prefix if present
        - Check needs_elevation → run_elevated or run normally
        - Report progress to task
        - Stop on first failure
        """
        all_results: list[PlanStepResult] = []
        display_steps: list[str] = []
        failed = False

        for i, step_cmd in enumerate(steps, 1):
            actual_cmd = step_cmd.strip()
            needs_root = self._privilege.needs_elevation(actual_cmd)

            # Strip sudo prefix — privilege.run_elevated handles it
            if actual_cmd.startswith("sudo "):
                actual_cmd = actual_cmd[5:]
                needs_root = True

            # Progress reporting
            if task:
                task.add_progress(
                    f"[{i}/{len(steps)}] {actual_cmd[:50]}",
                    (i / len(steps)) * 90,
                )

            # Execute
            if needs_root:
                result = self._privilege.run_elevated(actual_cmd, password=password)
            else:
                exec_result = self._executor.run(actual_cmd, timeout=120)
                result = ElevationResult(
                    success=exec_result.success,
                    stdout=exec_result.stdout,
                    stderr=exec_result.stderr,
                    returncode=exec_result.returncode,
                )

            # Record result
            if result.success:
                output = result.stdout.strip()[:150]
                all_results.append(PlanStepResult(actual_cmd[:80], True, output))
                display_steps.append(f"✓ {actual_cmd[:50]}")
            else:
                error = result.stderr.strip()[:200]
                # Strip sudo prompt noise
                error = "\n".join(line for line in error.splitlines() if "[sudo]" not in line)
                all_results.append(PlanStepResult(actual_cmd[:80], False, error))
                display_steps.append(f"✗ {actual_cmd[:50]}")
                failed = True
                break  # Stop on first failure

        if task:
            task.add_progress("Concluído", 100.0)

        return PlanExecutionResult(
            steps=display_steps,
            step_results=all_results,
            status="error" if failed else "success",
            summary="\n".join(display_steps) or "Concluído",
        )
