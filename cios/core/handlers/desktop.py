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
    from cios.skills.theming import get_current_theme, set_theme, toggle_theme

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
    from cios.skills.scheduler import parse_time_expression, scheduler

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
    reminder_text = re.sub(r"(?:às|as|at)\s+\d{1,2}(?::\d{2})?\s*h?", "", reminder_text).strip()
    reminder_text = re.sub(
        r"(?:daqui\s+a|in|em)\s+\d+\s*(?:min|minuto|minute|hora|hour|h)", "", reminder_text
    ).strip()
    if not reminder_text:
        reminder_text = "Lembrete"

    # Ensure scheduler is running
    scheduler.start()

    # Add the reminder
    scheduler.add_reminder(reminder_text, trigger_at)

    time_str = trigger_at.strftime("%H:%M")
    return PlanResult(
        plan_steps=[f"Agendando lembrete para {time_str}"],
        results=[],
        outcome="success",
        summary=f"Lembrete agendado: '{reminder_text}' às {time_str}.",
    )


def handle_vpn(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle VPN intents: connect, disconnect, status."""
    from cios.skills.vpn import connect_vpn, disconnect_vpn, get_vpn_status

    action = intent.params.get("action", "status")
    name = intent.params.get("name", "")

    if action == "connect":
        steps, success, msg = connect_vpn(name)
    elif action == "disconnect":
        steps, success, msg = disconnect_vpn(name)
    else:
        steps, success, msg = get_vpn_status()

    return PlanResult(
        plan_steps=steps,
        results=[],
        outcome="success" if success else "failure",
        summary=msg,
    )


def handle_firewall(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle firewall intents: allow/deny port, enable/disable."""
    from cios.skills.firewall import (
        allow_port,
        deny_port,
        disable_firewall,
        enable_firewall,
        get_status,
    )

    action = intent.params.get("action", "status")
    port = intent.params.get("port", 0)

    if action == "allow" and port:
        steps, success, msg = allow_port(port)
    elif action == "deny" and port:
        steps, success, msg = deny_port(port)
    elif action == "enable":
        steps, success, msg = enable_firewall()
    elif action == "disable":
        steps, success, msg = disable_firewall()
    else:
        steps, success, msg = get_status()

    return PlanResult(
        plan_steps=steps,
        results=[],
        outcome="success" if success else "failure",
        summary=msg,
    )


def handle_trash(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle trash intents: list, empty, restore."""
    from cios.skills.trash import empty_trash, get_trash_size, list_trash, restore_file

    action = intent.params.get("action", "list")
    name = intent.params.get("name", "")

    if action == "empty":
        steps, success, msg = empty_trash()
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if success else "failure", summary=msg
        )

    elif action == "restore" and name:
        steps, success, msg = restore_file(name)
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if success else "failure", summary=msg
        )

    else:
        # List trash contents
        items = list_trash()
        total_bytes, count = get_trash_size()
        if not items:
            return PlanResult(
                plan_steps=["Verificando lixeira"],
                results=[],
                outcome="success",
                summary="Lixeira vazia.",
            )

        from cios.skills.trash import _format_size

        lines = [f"• {item.name} ({item.deletion_date[:10]})" for item in items[:10]]
        summary = f"Lixeira: {count} item(ns), {_format_size(total_bytes)}:\n" + "\n".join(lines)
        return PlanResult(
            plan_steps=["Verificando lixeira"],
            results=[],
            outcome="success",
            summary=summary,
        )
