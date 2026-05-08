"""Handlers for process control and status intents."""

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult, sanitize_error
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.skills.process_control import (
    find_process_on_port,
    kill_process_on_port,
    list_listening_ports,
)


def handle_process_control(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Kill or query processes on a specific port."""
    port = intent.params.get("port")
    action = intent.params.get("action", "kill")

    if port is None:
        return PlanResult(
            plan_steps=["No port specified"],
            results=[],
            outcome="failure",
            summary="Which port? e.g., 'kill process on port 3000'",
            error="Missing port",
        )

    if action == "query":
        info = find_process_on_port(port)
        if info:
            summary = f"Port {port}: {info['name']} is using it"
        else:
            summary = f"Port {port} is free"
        return PlanResult(
            plan_steps=[f"Check port {port}"],
            results=[],
            outcome="success",
            summary=summary,
        )

    plan, result = kill_process_on_port(executor, port)
    return PlanResult(
        plan_steps=plan,
        results=[result],
        outcome="success" if result.success else "failure",
        summary=f"Killed process on port {port}"
        if result.success
        else f"Failed to kill process on port {port}",
        error=sanitize_error(result.stderr, "process_control") if not result.success else None,
    )


def handle_status(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """List currently listening ports/services."""
    ports = list_listening_ports()
    if ports:
        lines = [f"  :{p['port']}  {p['name']}" for p in ports[:15]]
        summary = "Listening ports:\n" + "\n".join(lines)
    else:
        summary = "No services currently listening."

    return PlanResult(
        plan_steps=["Check running services"],
        results=[],
        outcome="success",
        summary=summary,
        voice_mode="brief",
    )
