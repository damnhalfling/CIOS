"""Handlers for system health, session control, and power intents."""

from cios.core.executor import Executor
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.core.handlers._common import PlanResult, resilient_call
from cios.core.mcp import context as mcp
from cios.skills.system_health import check_system_health
from cios.skills.session_control import (
    execute_session_action,
    get_session_action,
)
from cios.skills import power as power_skill


def handle_system_health(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Check CPU, memory, disk health."""
    report = check_system_health()
    return PlanResult(
        plan_steps=report.plan_steps,
        results=[],
        outcome="success" if report.status == "healthy" else (
            "failure" if report.status == "critical" else "recovered"
        ),
        summary="\n".join(report.summary_lines),
        voice_mode="brief",
    )


def handle_session(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle session actions: shutdown, reboot, suspend, lock."""
    action_name = intent.params.get("action", "")
    if not action_name:
        return PlanResult(
            plan_steps=["No action specified"],
            results=[], outcome="failure",
            summary="What should I do? (shutdown, reboot, suspend, lock)",
            error="Missing session action",
        )

    action = get_session_action(action_name)
    if not action:
        return PlanResult(
            plan_steps=[f"Unknown action: {action_name}"],
            results=[], outcome="failure",
            summary=f"I don't know how to: {action_name}",
            error=f"Unknown session action: {action_name}",
        )

    plan_steps, success, error = resilient_call(
        execute_session_action, action_name, skill="session", retryable=False)
    return PlanResult(
        plan_steps=plan_steps,
        results=[], outcome="success" if success else "failure",
        summary=action.description if success else f"Failed: {action.description}",
        error=error,
    )


def handle_power(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle power/battery/brightness intents."""
    action = intent.params.get("action", "battery_status")

    if action == "battery_status":
        bat = mcp.battery
        if not bat.present:
            return PlanResult(
                plan_steps=["Checking battery"], results=[],
                outcome="success",
                summary="No battery detected — running on AC power")
        pct = bat.percent
        if bat.charging:
            summary = f"Battery: {pct}% ⚡ Charging"
        else:
            summary = f"Battery: {pct}%"
            if bat.time_remaining:
                summary += f" — {bat.time_remaining} remaining"
        if pct < 15:
            summary += "\n⚠ Battery critically low!"
        elif pct < 30:
            summary += "\n⚠ Battery getting low"
        return PlanResult(
            plan_steps=["Checking battery"], results=[],
            outcome="success", summary=summary)

    if action == "brightness_status":
        level = power_skill.get_brightness()
        if level < 0:
            return PlanResult(
                plan_steps=["Checking brightness"], results=[],
                outcome="failure",
                summary="Brightness control not available")
        return PlanResult(
            plan_steps=["Checking brightness"], results=[],
            outcome="success", summary=f"Brightness: {level}%")

    if action == "brightness_up":
        delta = intent.params.get("delta", 10)
        steps, ok, msg = resilient_call(
            power_skill.change_brightness, delta, skill="power")
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure", summary=msg)

    if action == "brightness_down":
        delta = intent.params.get("delta", 10)
        steps, ok, msg = resilient_call(
            power_skill.change_brightness, -delta, skill="power")
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure", summary=msg)

    if action == "brightness_set":
        level = intent.params.get("level", 50)
        steps, ok, msg = resilient_call(
            power_skill.set_brightness, level, skill="power")
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure", summary=msg)

    if action == "power_saving":
        steps, ok, msg = resilient_call(
            power_skill.enable_power_saving, skill="power")
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure", summary=msg)

    return PlanResult(
        plan_steps=["Checking battery"], results=[], outcome="failure",
        summary="Unknown power action")
