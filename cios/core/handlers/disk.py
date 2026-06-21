"""Handler for disk analysis intents."""

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult, sanitize_error
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.skills.disk_analysis import analyze_disk, clean_safe


def handle_disk(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle disk analyze/clean actions."""
    action = intent.params.get("action", "analyze")

    if action == "clean":
        steps, freed, errors = clean_safe()
        if errors:
            return PlanResult(
                plan_steps=steps,
                results=[],
                outcome="recovered" if freed > 0 else "failure",
                summary=f"Freed {freed // (1024 * 1024)}MB with {len(errors)} errors",
                error=sanitize_error(errors[0], "disk") if errors else None,
            )
        return PlanResult(
            plan_steps=steps,
            results=[],
            outcome="success",
            summary=f"Freed {freed // (1024 * 1024)}MB",
        )

    # Default: analyze
    report = analyze_disk()
    return PlanResult(
        plan_steps=report.plan_steps,
        results=[],
        outcome="success" if report.percent_used < 90 else "warning",
        summary="\n".join(report.summary_lines),
        voice_mode="brief",
    )
