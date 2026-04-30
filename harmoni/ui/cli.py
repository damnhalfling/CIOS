"""Minimal fullscreen terminal UI for the Harmoni OS."""

import time
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.live import Live
from rich import box

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML

from harmoni.core.config import HARMONI_HOME, ensure_dirs
from harmoni.core.executor import Executor
from harmoni.core.intent_parser import parse_intent, IntentType
from harmoni.core.memory import Memory
from harmoni.core.model_router import resolve_unknown_intent
from harmoni.core.planner import Planner, PlanResult

console = Console()

BANNER = r"""
[bold cyan]╔═══════════════════════════════════════════════════════════╗
║                    HARMONI OS                             ║
║          AI-first system interface · always present        ║
╚═══════════════════════════════════════════════════════════╝[/bold cyan]
"""

HELP_TEXT = """[dim]Commands:  "start my backend" · "fix it" · "status" · "kill process on port 3000"
           "show logs" · "run <command>" · "help" · "exit"[/dim]"""


def _render_plan(steps: list[str]) -> Panel:
    """Render a plan as a compact panel."""
    text = Text()
    for i, step in enumerate(steps, 1):
        text.append(f"  {i}. ", style="bold yellow")
        text.append(f"{step}\n", style="white")
    return Panel(text, title="[bold]Plan[/bold]", border_style="yellow", box=box.ROUNDED, padding=(0, 1))


def _render_result(result: PlanResult) -> Panel:
    """Render execution result."""
    if result.outcome == "success":
        style = "green"
        icon = "✓"
    elif result.outcome == "recovered":
        style = "yellow"
        icon = "⟳"
    else:
        style = "red"
        icon = "✗"

    text = Text()
    text.append(f" {icon} ", style=f"bold {style}")
    text.append(result.summary, style=style)

    # Never show raw stderr — the humanizer already handled the error message
    # If there's additional context, show it dimmed but sanitized
    if result.outcome == "failure" and result.error:
        import re
        # Strip paths, PIDs, and technical noise
        hint = re.sub(r'/[\w/.\-]+', '', result.error)
        hint = re.sub(r'\(PID \d+\)', '', hint)
        hint = re.sub(r'\s+', ' ', hint).strip()
        if hint and hint != result.summary and len(hint) > 5:
            text.append(f"\n  {hint[:120]}", style="dim")

    return Panel(
        text,
        title=f"[bold {style}]Result[/bold {style}]",
        border_style=style,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def _show_thinking():
    """Brief thinking indicator."""
    console.print("  [dim cyan]⟡ analyzing...[/dim cyan]")


def run_ui() -> None:
    """Main UI loop."""
    ensure_dirs()

    executor = Executor()
    memory = Memory()
    planner = Planner(executor, memory)

    history_file = HARMONI_HOME / "history.txt"
    session: PromptSession = PromptSession(
        history=FileHistory(str(history_file)),
    )

    console.clear()
    console.print(BANNER)
    console.print(HELP_TEXT)
    console.print()

    while True:
        try:
            user_input = session.prompt(
                HTML("<ansicyan><b>harmoni</b></ansicyan> <ansiwhite>›</ansiwhite> "),
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Harmoni detaching. System continues.[/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Harmoni detaching. System continues.[/dim]")
            break

        if user_input.lower() in ("help", "?"):
            console.print(HELP_TEXT)
            continue

        if user_input.lower() == "history":
            records = memory.recent(10)
            if not records:
                console.print("[dim]No history yet.[/dim]")
                continue
            table = Table(title="Recent Actions", box=box.SIMPLE)
            table.add_column("Time", style="dim")
            table.add_column("Input", style="cyan")
            table.add_column("Outcome", style="green")
            for rec in records:
                t = time.strftime("%H:%M:%S", time.localtime(rec.timestamp))
                table.add_row(t, rec.user_input[:40], rec.outcome)
            console.print(table)
            continue

        # --- Parse intent ---
        _show_thinking()
        intent = parse_intent(user_input)

        # If pattern matching failed, try LLM
        if intent.type == IntentType.UNKNOWN:
            resolved = resolve_unknown_intent(user_input)
            if resolved:
                intent = resolved
            else:
                console.print(
                    "[yellow]  I don't understand that. Try 'help' for examples.[/yellow]\n"
                )
                continue

        # --- Show plan preview ---
        console.print(f"  [dim]Intent: {intent.type.value} (confidence: {intent.confidence:.0%})[/dim]")

        # --- Execute ---
        start = time.monotonic()
        result = planner.execute(intent)
        elapsed = time.monotonic() - start

        # --- Display ---
        if result.plan_steps:
            console.print(_render_plan(result.plan_steps))
        console.print(_render_result(result))
        console.print(f"  [dim]Completed in {elapsed:.1f}s[/dim]\n")

    memory.close()
