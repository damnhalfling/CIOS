"""Handlers for app launch, list apps, and explore system intents."""

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult, resilient_call
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.skills.app_launcher import find_app, launch_app
from cios.skills.explore_system import format_capabilities, list_installed_apps_grouped


def handle_app_launch(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Find and launch a desktop application."""
    app_name = intent.params.get("app", "")
    if not app_name:
        return PlanResult(
            plan_steps=["No app specified"],
            results=[],
            outcome="failure",
            summary="Which app should I open?",
            error="Missing app name",
        )

    app = find_app(app_name)
    if not app:
        return PlanResult(
            plan_steps=[f"Searching for {app_name}"],
            results=[],
            outcome="failure",
            summary=f"App not found: {app_name}",
            error=f"Could not find application matching '{app_name}'",
        )

    plan_steps, success, error = resilient_call(
        launch_app, app, skill="app_launch", retryable=False
    )
    return PlanResult(
        plan_steps=plan_steps,
        results=[],
        outcome="success" if success else "failure",
        summary=f"{app.name} opened" if success else f"Failed to open {app.name}",
        error=error,
    )


def handle_explore_system(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Show what CIOS can do, or respond to greetings conversationally."""
    from cios.core.humanizer import _LANG

    # Greetings get a conversational response, not a capability list
    if not intent.params or intent.params.get("action") != "list":
        import random

        greetings_pt = [
            "Olá! No que posso ajudar?",
            "Oi! O que quer fazer?",
            "Fala! Como posso ajudar?",
            "E aí! O que precisa?",
        ]
        greetings_en = [
            "Hey! What can I do for you?",
            "Hi! How can I help?",
            "Hello! What do you need?",
        ]
        responses = greetings_pt if _LANG == "pt" else greetings_en
        return PlanResult(
            plan_steps=["Greeting"],
            results=[],
            outcome="success",
            summary=random.choice(responses),
            voice_mode="full",
        )

    steps, summary = format_capabilities(_LANG)
    return PlanResult(
        plan_steps=steps, results=[], outcome="success", summary=summary, voice_mode="brief"
    )


def handle_list_apps(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """List installed apps grouped by category."""
    from cios.core.humanizer import _LANG

    steps, summary = list_installed_apps_grouped(_LANG)
    return PlanResult(
        plan_steps=steps, results=[], outcome="success", summary=summary, voice_mode="brief"
    )
