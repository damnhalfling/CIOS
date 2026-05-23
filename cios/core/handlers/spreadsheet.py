"""Handler for spreadsheet intents — read, search, update spreadsheet files."""

import re

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.skills.spreadsheet import (
    find_spreadsheet,
    read_spreadsheet,
    search_value,
    update_cell,
)


def handle_spreadsheet(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle spreadsheet operations: read, search, update."""
    query = intent.params.get("query", "")
    action = intent.params.get("action", "read")

    if not query:
        return PlanResult(
            plan_steps=["Aguardando informação"],
            results=[],
            outcome="failure",
            summary="Qual planilha você quer acessar?",
        )

    # Extract spreadsheet name from query
    # Patterns: "planilha custos-aws, quanto gastamos" → name="custos-aws", rest="quanto gastamos"
    name, rest = _extract_name_and_query(query)

    # Find the spreadsheet file
    file_path = find_spreadsheet(name)
    if not file_path:
        return PlanResult(
            plan_steps=[f"Buscando planilha '{name}'"],
            results=[],
            outcome="failure",
            summary=f"Planilha '{name}' não encontrada.",
            error="file_not_found",
        )

    if action == "read":
        result = read_spreadsheet(file_path)
        if result.success:
            return PlanResult(
                plan_steps=result.plan_steps,
                results=[],
                outcome="success",
                summary=result.message,
                voice_mode="brief",
            )
        return PlanResult(
            plan_steps=result.plan_steps,
            results=[],
            outcome="failure",
            summary=result.message,
            error=result.error,
        )

    elif action == "query":
        # Try to extract column name and row query from the rest
        # "quanto gastamos no último mês" → search for the value
        if rest:
            # First try a general search
            result = search_value(file_path, rest)
            if result.success and result.data:
                cells = result.data
                if isinstance(cells, list) and cells:
                    # Format results
                    lines = []
                    for cell in cells[:5]:
                        lines.append(f"  {cell.column}: {cell.value} (linha {cell.row})")
                    return PlanResult(
                        plan_steps=result.plan_steps,
                        results=[],
                        outcome="success",
                        summary=result.message + "\n" + "\n".join(lines),
                        voice_mode="full",
                    )

        # Fallback: show structure
        result = read_spreadsheet(file_path)
        return PlanResult(
            plan_steps=result.plan_steps,
            results=[],
            outcome="success" if result.success else "failure",
            summary=result.message,
            error=result.error,
        )

    elif action == "update":
        # Parse update command: "valor de 1500 para 1750" or "1500 → 1750"
        old_val, new_val, col_hint = _parse_update(rest or query)

        if not old_val or not new_val:
            return PlanResult(
                plan_steps=["Analisando comando"],
                results=[],
                outcome="failure",
                summary="Não entendi a alteração. Diga algo como: "
                "'atualize planilha X, mude 1500 para 1750'",
            )

        result = update_cell(file_path, old_val, new_val, col_hint)
        if result.success:
            return PlanResult(
                plan_steps=result.plan_steps,
                results=[],
                outcome="success",
                summary=result.message,
            )
        return PlanResult(
            plan_steps=result.plan_steps,
            results=[],
            outcome="failure",
            summary=result.message,
            error=result.error,
        )

    # Unknown action — default to read
    result = read_spreadsheet(file_path)
    return PlanResult(
        plan_steps=result.plan_steps,
        results=[],
        outcome="success" if result.success else "failure",
        summary=result.message,
        error=result.error,
    )


def _extract_name_and_query(query: str) -> tuple[str, str]:
    """Extract spreadsheet name and remaining query from user input.

    Examples:
        "custos-aws, quanto gastamos no último mês" → ("custos-aws", "quanto gastamos no último mês")
        "custos-aws" → ("custos-aws", "")
        "custos aws quanto gastamos" → ("custos aws", "quanto gastamos")
    """
    # Split on comma
    if "," in query:
        parts = query.split(",", 1)
        return parts[0].strip(), parts[1].strip()

    # Split on question words
    q_words = r"\b(quanto|qual|quais|tem|what|how|which|has)\b"
    match = re.search(q_words, query, re.IGNORECASE)
    if match:
        name = query[: match.start()].strip()
        rest = query[match.start() :].strip()
        return name, rest

    # No separator found — entire thing is the name
    return query, ""


def _parse_update(text: str) -> tuple[str, str, str | None]:
    """Parse an update command to extract old value, new value, and optional column hint.

    Patterns:
        "1500 para 1750" → ("1500", "1750", None)
        "mude 1500 para 1750" → ("1500", "1750", None)
        "de 1500 para 1750" → ("1500", "1750", None)
        "valor 1500 → 1750" → ("1500", "1750", None)
        "coluna custo de 1500 para 1750" → ("1500", "1750", "custo")
        "corrija gastamos 1750" → needs context, harder to parse

    Returns:
        (old_value, new_value, column_hint) or ("", "", None) if can't parse
    """
    # Pattern: "de X para Y" or "X para Y" or "X → Y" or "X to Y"
    patterns = [
        r"(?:de\s+)?(\S+)\s+(?:para|→|->|to)\s+(\S+)",
        r"(?:mude?|change|corrija|fix)\s+(\S+)\s+(?:para|→|->|to|por)\s+(\S+)",
        r"(\d[\d.,]*)\s*(?:para|→|->|to)\s*(\d[\d.,]*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            old_val = match.group(1)
            new_val = match.group(2)

            # Check for column hint before the match
            col_hint = None
            prefix = text[: match.start()].strip()
            col_match = re.search(r"(?:coluna|column|campo|field)\s+(\w+)", prefix, re.IGNORECASE)
            if col_match:
                col_hint = col_match.group(1)

            return old_val, new_val, col_hint

    return "", "", None
