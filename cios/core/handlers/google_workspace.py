"""Handlers for Google Workspace intents — email, drive, calendar, gchat.

Routes intent types to the appropriate Google skill.
Requires: user logged into Intelligence with workspace=true.
"""

import logging

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult
from cios.core.intent_parser import Intent
from cios.core.memory import Memory

logger = logging.getLogger(__name__)


def _get_mcp_client(memory: Memory):
    """Get GoogleMCPClient from the current session.

    Returns None if user is not logged into Intelligence.
    """
    try:
        import json

        from cios.core.config import CIOS_HOME
        from cios.core.google_mcp import GoogleMCPClient

        auth_file = CIOS_HOME / "intelligence.json"
        if not auth_file.exists():
            return None

        data = json.loads(auth_file.read_text())
        api_url = data.get("api_url", "https://api.cios-ai.com")
        jwt_token = data.get("token", "")

        if not jwt_token:
            return None

        return GoogleMCPClient(api_url=api_url, jwt_token=jwt_token)
    except Exception as e:
        logger.error("Failed to create MCP client: %s", e)
        return None


def _no_workspace() -> PlanResult:
    """Return error when workspace is not connected."""
    return PlanResult(
        plan_steps=["Verificando conexão Google Workspace"],
        results=[],
        outcome="failure",
        summary="Google Workspace não conectado. Faça login no Intelligence com permissões expandidas.",
        error="workspace_not_connected",
    )


# ═══════════════════════════════════════════════════════════════════════════
#  EMAIL HANDLER (#558)
# ═══════════════════════════════════════════════════════════════════════════


def handle_email(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle email intents: search, read, draft, label."""
    mcp = _get_mcp_client(memory)
    if not mcp:
        return _no_workspace()

    from cios.skills.email import draft_email, search_emails

    action = intent.params.get("action", "search")
    query = intent.params.get("query", "")

    if action == "search" or not action:
        if not query:
            return PlanResult(
                plan_steps=["Aguardando"],
                results=[],
                outcome="failure",
                summary="O que você quer buscar nos emails?",
            )

        result = search_emails(mcp, query)
        if "error" in result:
            return PlanResult(
                plan_steps=["Buscando emails"],
                results=[],
                outcome="failure",
                summary=f"Erro ao buscar emails: {result['error']}",
            )

        count = result.get("count", 0)
        emails = result.get("emails", [])
        if count == 0:
            return PlanResult(
                plan_steps=["Buscando emails"],
                results=[],
                outcome="success",
                summary=f"Nenhum email encontrado para '{query}'.",
            )

        # Format email list
        lines = []
        for e in emails[:5]:
            subject = e.get("subject", "(sem assunto)")
            sender = e.get("from", "")
            lines.append(f"• {subject} — {sender}")

        summary = f"Encontrei {count} email(s):\n" + "\n".join(lines)
        return PlanResult(
            plan_steps=["Buscando emails"],
            results=[],
            outcome="success",
            summary=summary,
            data={"emails": emails[:10]},
        )

    elif action == "draft":
        to = intent.params.get("to", "")
        subject = intent.params.get("subject", "")
        body = intent.params.get("body", "")

        if not to:
            return PlanResult(
                plan_steps=["Criando rascunho"],
                results=[],
                outcome="failure",
                summary="Para quem é o email?",
            )

        result = draft_email(mcp, to, subject, body)
        if "error" in result:
            return PlanResult(
                plan_steps=["Criando rascunho"],
                results=[],
                outcome="failure",
                summary=f"Erro ao criar rascunho: {result['error']}",
            )

        return PlanResult(
            plan_steps=["Criando rascunho"],
            results=[],
            outcome="success",
            summary=f"Rascunho criado para {to}.",
        )

    return PlanResult(
        plan_steps=["Email"],
        results=[],
        outcome="failure",
        summary="Não entendi a ação de email.",
    )


# ═══════════════════════════════════════════════════════════════════════════
#  DRIVE HANDLER (#559)
# ═══════════════════════════════════════════════════════════════════════════


def handle_drive(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle drive intents: search, read, create."""
    mcp = _get_mcp_client(memory)
    if not mcp:
        return _no_workspace()

    from cios.skills.drive import search_files

    action = intent.params.get("action", "search")
    query = intent.params.get("query", "")

    if action == "search" or not action:
        if not query:
            return PlanResult(
                plan_steps=["Aguardando"],
                results=[],
                outcome="failure",
                summary="O que você quer buscar no Drive?",
            )

        result = search_files(mcp, query)
        if "error" in result:
            return PlanResult(
                plan_steps=["Buscando no Drive"],
                results=[],
                outcome="failure",
                summary=f"Erro ao buscar no Drive: {result['error']}",
            )

        count = result.get("count", 0)
        files = result.get("files", [])
        if count == 0:
            return PlanResult(
                plan_steps=["Buscando no Drive"],
                results=[],
                outcome="success",
                summary=f"Nenhum arquivo encontrado para '{query}'.",
            )

        lines = [f"• {f.get('name', '?')}" for f in files[:5]]
        summary = f"Encontrei {count} arquivo(s):\n" + "\n".join(lines)
        return PlanResult(
            plan_steps=["Buscando no Drive"],
            results=[],
            outcome="success",
            summary=summary,
            data={"files": files[:10]},
        )

    return PlanResult(
        plan_steps=["Drive"],
        results=[],
        outcome="failure",
        summary="Não entendi a ação do Drive.",
    )


# ═══════════════════════════════════════════════════════════════════════════
#  CALENDAR HANDLER (#561)
# ═══════════════════════════════════════════════════════════════════════════


def handle_calendar(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle calendar intents: list events, create event."""
    mcp = _get_mcp_client(memory)
    if not mcp:
        return _no_workspace()

    from cios.skills.calendar import create_event, list_events

    action = intent.params.get("action", "list")

    if action == "list" or not action:
        days = intent.params.get("days", 7)
        result = list_events(mcp, days=days)
        if "error" in result:
            return PlanResult(
                plan_steps=["Consultando agenda"],
                results=[],
                outcome="failure",
                summary=f"Erro ao consultar agenda: {result['error']}",
            )

        events = result.get("events", [])
        if not events:
            return PlanResult(
                plan_steps=["Consultando agenda"],
                results=[],
                outcome="success",
                summary=f"Nenhum evento nos próximos {days} dias.",
            )

        lines = []
        for ev in events[:7]:
            summary_ev = ev.get("summary", "(sem título)")
            start = ev.get("start", "")
            lines.append(f"• {summary_ev} — {start}")

        summary = f"{len(events)} evento(s) nos próximos {days} dias:\n" + "\n".join(lines)
        return PlanResult(
            plan_steps=["Consultando agenda"],
            results=[],
            outcome="success",
            summary=summary,
            data={"events": events},
        )

    elif action == "create":
        title = intent.params.get("title", "")
        start = intent.params.get("start", "")
        end = intent.params.get("end", "")

        if not title or not start:
            return PlanResult(
                plan_steps=["Criando evento"],
                results=[],
                outcome="failure",
                summary="Preciso do título e horário do evento.",
            )

        result = create_event(mcp, summary=title, start=start, end=end or start)
        if "error" in result:
            return PlanResult(
                plan_steps=["Criando evento"],
                results=[],
                outcome="failure",
                summary=f"Erro ao criar evento: {result['error']}",
            )

        return PlanResult(
            plan_steps=["Criando evento"],
            results=[],
            outcome="success",
            summary=f"Evento '{title}' criado.",
        )

    return PlanResult(
        plan_steps=["Agenda"],
        results=[],
        outcome="failure",
        summary="Não entendi a ação da agenda.",
    )


# ═══════════════════════════════════════════════════════════════════════════
#  GCHAT HANDLER (#560)
# ═══════════════════════════════════════════════════════════════════════════


def handle_gchat(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle Google Chat intents: search, send."""
    mcp = _get_mcp_client(memory)
    if not mcp:
        return _no_workspace()

    from cios.skills.gchat import search_messages, send_message

    action = intent.params.get("action", "search")
    query = intent.params.get("query", "")

    if action == "search":
        if not query:
            return PlanResult(
                plan_steps=["Aguardando"],
                results=[],
                outcome="failure",
                summary="O que você quer buscar no Chat?",
            )

        result = search_messages(mcp, query)
        if "error" in result:
            return PlanResult(
                plan_steps=["Buscando no Chat"],
                results=[],
                outcome="failure",
                summary=f"Erro ao buscar no Chat: {result['error']}",
            )

        messages = result.get("messages", [])
        if not messages:
            return PlanResult(
                plan_steps=["Buscando no Chat"],
                results=[],
                outcome="success",
                summary=f"Nenhuma mensagem encontrada para '{query}'.",
            )

        lines = [f"• {m.get('sender', '?')}: {m.get('text', '')[:50]}" for m in messages[:5]]
        summary = f"{len(messages)} mensagem(ns):\n" + "\n".join(lines)
        return PlanResult(
            plan_steps=["Buscando no Chat"],
            results=[],
            outcome="success",
            summary=summary,
            data={"messages": messages[:10]},
        )

    elif action == "send":
        space = intent.params.get("space", "")
        text = intent.params.get("text", "")

        if not space or not text:
            return PlanResult(
                plan_steps=["Enviando mensagem"],
                results=[],
                outcome="failure",
                summary="Preciso saber para qual espaço e o que enviar.",
            )

        result = send_message(mcp, space, text)
        if "error" in result:
            return PlanResult(
                plan_steps=["Enviando mensagem"],
                results=[],
                outcome="failure",
                summary=f"Erro ao enviar: {result['error']}",
            )

        return PlanResult(
            plan_steps=["Enviando mensagem"],
            results=[],
            outcome="success",
            summary="Mensagem enviada.",
        )

    return PlanResult(
        plan_steps=["Chat"],
        results=[],
        outcome="failure",
        summary="Não entendi a ação do Chat.",
    )
