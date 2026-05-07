"""Handlers for command execution, self-update, and intelligence intents."""

from cios.core.executor import Executor
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.core.handlers._common import PlanResult, sanitize_error
from cios.skills import self_update as update_skill


def handle_command_exec(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Execute a raw shell command."""
    command = intent.params.get("command", "")
    if not command:
        return PlanResult(
            plan_steps=["No command provided"],
            results=[], outcome="failure",
            summary="What command should I run?",
            error="Missing command",
        )

    result = executor.run(command)
    if result.success:
        output = result.stdout[:500].strip()
        summary = output if output else "Done"
    else:
        summary = sanitize_error(result.stderr, "command")
    return PlanResult(
        plan_steps=[f"Execute: {command}"],
        results=[result],
        outcome="success" if result.success else "failure",
        summary=summary,
        error=sanitize_error(result.stderr, "command") if not result.success else None,
    )


def handle_self_update(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle version check and self-update."""
    action = intent.params.get("action", "check")

    if action == "version":
        version = update_skill.get_current_version()
        return PlanResult(
            plan_steps=["Checking version"],
            results=[], outcome="success",
            summary=f"CIOS v{version}")

    if action == "check":
        steps, summary = update_skill.check_update_summary()
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success", summary=summary)

    if action == "update":
        info = update_skill.check_update(use_cache=False)
        if not info.has_update:
            return PlanResult(
                plan_steps=["Verificando atualizações"],
                results=[], outcome="success",
                summary=f"Já está na versão mais recente (v{info.current_version})")

        steps, ok, msg = update_skill.download_and_install(info)
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure",
            summary=msg)

    return PlanResult(
        plan_steps=["Checking version"], results=[], outcome="failure",
        summary="Ação de atualização desconhecida")


def handle_intelligence(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle Intelligence intents (news, explain, write, summarize, translate)."""
    from cios.core.intelligence import intelligence

    sub_intent = intent.params.get("intent", "chat")
    query = intent.params.get("query", intent.raw_input)

    if not intelligence.is_logged_in:
        return PlanResult(
            plan_steps=["Verificando Intelligence"],
            results=[], outcome="failure",
            summary="Faça login no CIOS Intelligence para usar este recurso. "
                    "Use a área de login na sidebar.",
            voice_mode="full")

    result = intelligence.query(query, intent=sub_intent)

    if result.success:
        return PlanResult(
            plan_steps=["Consultando CIOS Intelligence"],
            results=[], outcome="success",
            summary=result.text,
            voice_mode="full")
    else:
        return PlanResult(
            plan_steps=["Consultando CIOS Intelligence"],
            results=[], outcome="failure",
            summary=result.text,
            voice_mode="full")
