"""Handlers for file organization and file search intents."""

import os
from pathlib import Path

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult, resilient_call, sanitize_error
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.skills.file_organize import organize_directory
from cios.skills.file_search import find_and_open, search_files


def handle_file_organize(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Organize files in a directory by type."""
    target = intent.params.get("target", "downloads")
    path_map = {
        "downloads": "~/Downloads",
        "download": "~/Downloads",
        "desktop": "~/Desktop",
        "área de trabalho": "~/Desktop",
        "documents": "~/Documents",
        "document": "~/Documents",
        "documentos": "~/Documents",
        "documento": "~/Documents",
        "pictures": "~/Pictures",
        "picture": "~/Pictures",
        "fotos": "~/Pictures",
        "foto": "~/Pictures",
        "imagens": "~/Pictures",
        "home": "~",
        "files": ".",
        "arquivos": ".",
        "folder": ".",
        "pasta": ".",
    }
    directory = path_map.get(target, target)

    resolved = Path(directory).expanduser().resolve()
    if not resolved.is_dir():
        return PlanResult(
            plan_steps=[f"Looking for {target}"],
            results=[],
            outcome="failure",
            summary=f"Could not find folder: {target}",
            error=f"Directory not found: {directory}",
        )

    result = organize_directory(str(resolved))
    if result.errors:
        return PlanResult(
            plan_steps=result.plan_steps,
            results=[],
            outcome="failure",
            summary=f"Organized {result.moved} files with {len(result.errors)} errors",
            error=sanitize_error(result.errors[0], "file_organize") if result.errors else None,
        )

    summary_parts = [f"{result.moved} files organized"]
    if result.folders_created:
        summary_parts.append(f"Created: {', '.join(result.folders_created)}")

    return PlanResult(
        plan_steps=result.plan_steps,
        results=[],
        outcome="success",
        summary=". ".join(summary_parts),
    )


def handle_files_search(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Search for files by name or content."""
    query = intent.params.get("query", "")
    if not query:
        return PlanResult(
            plan_steps=["No search query"],
            results=[],
            outcome="failure",
            summary="What file are you looking for?",
        )

    report = search_files(query)

    if not report.results:
        from cios.core.humanizer import _LANG

        msg = (
            f"Nenhum arquivo encontrado para: {query}"
            if _LANG == "pt"
            else f"No files found for: {query}"
        )
        return PlanResult(plan_steps=report.plan_steps, results=[], outcome="success", summary=msg)

    lines = []
    for r in report.results[:10]:
        icon = {
            "document": "📄",
            "image": "🖼️",
            "video": "🎬",
            "audio": "🎵",
            "code": "💻",
            "archive": "📦",
        }.get(r.file_type, "📁")
        match_tag = " (conteúdo)" if r.match_type == "content" else ""
        lines.append(f"  {icon} {r.name} — {r.size_human} — {r.modified}{match_tag}")
        home = os.path.expanduser("~")
        display_path = r.path.replace(home, "~")
        lines.append(f"     {display_path}")

    from cios.core.humanizer import _LANG

    header = (
        f'Encontrados {len(report.results)} arquivo(s) para "{query}":'
        if _LANG == "pt"
        else f'Found {len(report.results)} file(s) for "{query}":'
    )
    tip = (
        '\nDiga "abrir arquivo [nome]" para abrir.'
        if _LANG == "pt"
        else '\nSay "open file [name]" to open.'
    )

    return PlanResult(
        plan_steps=report.plan_steps,
        results=[],
        outcome="success",
        summary=header + "\n" + "\n".join(lines) + tip,
        voice_mode="brief",
    )


def handle_files_open(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Find and open a file."""
    query = intent.params.get("query", "")
    if not query:
        return PlanResult(
            plan_steps=["No file specified"],
            results=[],
            outcome="failure",
            summary="Which file should I open?",
        )

    steps, ok, err = resilient_call(find_and_open, query, skill="file_search")
    return PlanResult(
        plan_steps=steps,
        results=[],
        outcome="success" if ok else "failure",
        summary=steps[-1] if ok and steps else (err or f"File not found: {query}"),
        error=err,
    )
