"""Handlers for log analysis and fix-last-error intents."""

import logging
import re
import time

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.skills.dev_start import detect_project, execute_dev_start
from cios.skills.log_analysis import analyze_text

logger = logging.getLogger(__name__)


def handle_log_analysis(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Analyze recent logs or last failure."""
    last = memory.last_failure()
    if last and last.error:
        combined = "\n".join(last.commands) + "\n" + (last.error or "")
        insight = analyze_text(combined, source="memory")
    else:
        from cios.skills.log_analysis import read_system_logs

        logs = read_system_logs(executor)
        insight = analyze_text(logs, source="system_logs")

    lines_display = "\n".join(insight.error_lines[:5]) if insight.error_lines else "No errors"
    summary = f"Root cause: {insight.root_cause}\nSuggestion: {insight.suggestion}"

    return PlanResult(
        plan_steps=["Read logs", "Analyze errors"],
        results=[],
        outcome="success",
        summary=f"{lines_display}\n\n{summary}",
        voice_mode="brief",
    )


def handle_fix_last_error(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Attempt to automatically fix the last recorded failure."""
    last = memory.last_failure()
    if last is None:
        return PlanResult(
            plan_steps=["Check memory for last failure"],
            results=[],
            outcome="success",
            summary="No recent failures found in memory.",
        )

    error_text = last.error or ""
    combined = error_text + "\n" + "\n".join(last.commands)
    insight = analyze_text(combined, source="memory")

    if insight.root_cause in ("No errors detected", "Unrecognized error"):
        if "port" in error_text.lower() and "in use" in error_text.lower():
            insight.root_cause = error_text
            insight.suggestion = "Kill the process using the port and retry"
        elif "module" in error_text.lower() or "not found" in error_text.lower():
            insight.root_cause = error_text
            insight.suggestion = "Reinstall dependencies"

    plan_steps = [f"Found last failure: {last.intent}", f"Root cause: {insight.root_cause}"]
    results = []

    if "port" in insight.root_cause.lower():
        port_match = re.search(r"(\d{4,5})", insight.root_cause)
        port = int(port_match.group(1)) if port_match else 3000
        plan_steps.append(f"Killing process on port {port}")
        kill_result = executor.kill_by_port(port)
        results.append(kill_result)
        time.sleep(1)

        if last.intent == "dev_start":
            plan_steps.append("Retrying server start")
            project = detect_project(last.context.get("directory", "."))
            start_plan, start_results, pid = execute_dev_start(
                executor,
                project=project,
                memory=memory,
            )
            plan_steps.extend(start_plan)
            results.extend(start_results)

            if pid:
                return PlanResult(
                    plan_steps=plan_steps,
                    results=results,
                    outcome="recovered",
                    summary="Fixed port conflict and restarted server",
                )

    elif "module" in insight.root_cause.lower() or "install" in insight.suggestion.lower():
        plan_steps.append("Reinstalling dependencies")
        project = detect_project(".")
        if project.install_command:
            install_result = executor.run(project.install_command, cwd=project.root, timeout=180)
            results.append(install_result)
            if install_result.success and last.intent == "dev_start":
                plan_steps.append("Retrying server start")
                start_plan, start_results, pid = execute_dev_start(
                    executor,
                    project=project,
                    memory=memory,
                )
                plan_steps.extend(start_plan)
                results.extend(start_results)
                if pid:
                    return PlanResult(
                        plan_steps=plan_steps,
                        results=results,
                        outcome="recovered",
                        summary="Reinstalled components and restarted — running now",
                    )

    failed = [r for r in results if not r.success]
    if failed:
        return PlanResult(
            plan_steps=plan_steps,
            results=results,
            outcome="failure",
            summary=f"Attempted fix but failed. {insight.suggestion}",
            error=insight.root_cause,
        )

    return PlanResult(
        plan_steps=plan_steps,
        results=results,
        outcome="recovered" if results else "success",
        summary=f"Applied fix: {insight.suggestion}",
    )
