"""Handlers for desktop features — theming, scheduler, display, automount.

#506-509 — Desktop completude handlers
"""

import logging

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult
from cios.core.intent_parser import Intent
from cios.core.memory import Memory

logger = logging.getLogger(__name__)


def handle_theming(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle theming intents: set dark/light, toggle."""
    from cios.skills.theming import set_theme, toggle_theme, get_current_theme

    action = intent.params.get("action", "toggle")
    theme = intent.params.get("theme", "")

    if action == "set" and theme:
        success, message = set_theme(theme)
        return PlanResult(
            plan_steps=[f"Alterando tema para {theme}"],
            results=[],
            outcome="success" if success else "failure",
            summary=message,
        )
    elif action == "toggle":
        success, message = toggle_theme()
        return PlanResult(
            plan_steps=["Alternando tema"],
            results=[],
            outcome="success" if success else "failure",
            summary=message,
        )
    else:
        current = get_current_theme()
        return PlanResult(
            plan_steps=["Verificando tema"],
            results=[],
            outcome="success",
            summary=f"Tema atual: {current}. Diga 'modo escuro' ou 'modo claro' para alterar.",
        )


def handle_scheduler(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle scheduler intents: reminders, timers."""
    from cios.skills.scheduler import scheduler, parse_time_expression

    action = intent.params.get("action", "remind")
    text = intent.params.get("text", "")
    time_expr = intent.params.get("time_expr", "")

    # Parse time from the expression
    raw = time_expr or text
    trigger_at = parse_time_expression(raw)

    if not trigger_at:
        return PlanResult(
            plan_steps=["Analisando horário"],
            results=[],
            outcome="failure",
            summary="Não entendi o horário. Tente: 'lembra-me às 17h' ou 'daqui a 30 minutos'.",
        )

    # Extract the reminder text (remove time parts)
    import re
    reminder_text = text or "Lembrete"
    # Clean time expressions from the text
    reminder_text = re.sub(
        r"(?:às|as|at)\s+\d{1,2}(?::\d{2})?\s*h?", "", reminder_text
    ).strip()
    reminder_text = re.sub(
        r"(?:daqui\s+a|in|em)\s+\d+\s*(?:min|minuto|minute|hora|hour|h)", "", reminder_text
    ).strip()
    if not reminder_text:
        reminder_text = "Lembrete"

    # Ensure scheduler is running
    scheduler.start()

    # Add the reminder
    task = scheduler.add_reminder(reminder_text, trigger_at)

    time_str = trigger_at.strftime("%H:%M")
    return PlanResult(
        plan_steps=[f"Agendando lembrete para {time_str}"],
        results=[],
        outcome="success",
        summary=f"Lembrete agendado: '{reminder_text}' às {time_str}.",
    )
