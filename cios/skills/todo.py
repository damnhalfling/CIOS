"""Skill: todo — Local task management for the user.

Stores personal TODOs in ~/.cios/todos.json.
Tasks have: id, text, priority (high/medium/low), created_at, done, done_at.

The briefing system reads from this to show "O que tenho pra hoje".
Users can also sync from Google Calendar/Tasks via Intelligence API.

Usage (via intent):
    "adiciona tarefa: revisar PR do maestro"
    "minhas tarefas"
    "marca tarefa 3 como feita"
    "remove tarefa 2"
    "próximas tarefas"   → top 5 by priority
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_TODO_FILE = Path.home() / ".cios" / "todos.json"


@dataclass
class Todo:
    """A single TODO item."""

    id: int
    text: str
    priority: str = "medium"  # high, medium, low
    created_at: str = ""
    done: bool = False
    done_at: str = ""
    source: str = "local"  # local, calendar, intelligence

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Todo":
        return cls(
            id=d.get("id", 0),
            text=d.get("text", ""),
            priority=d.get("priority", "medium"),
            created_at=d.get("created_at", ""),
            done=d.get("done", False),
            done_at=d.get("done_at", ""),
            source=d.get("source", "local"),
        )


def _load_todos() -> list[Todo]:
    """Load todos from file."""
    if not _TODO_FILE.exists():
        return []
    try:
        data = json.loads(_TODO_FILE.read_text(encoding="utf-8"))
        return [Todo.from_dict(d) for d in data]
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load todos: %s", e)
        return []


def _save_todos(todos: list[Todo]) -> None:
    """Save todos to file."""
    _TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TODO_FILE.write_text(
        json.dumps([t.to_dict() for t in todos], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _next_id(todos: list[Todo]) -> int:
    """Get next available ID."""
    if not todos:
        return 1
    return max(t.id for t in todos) + 1


# ─── Public API ──────────────────────────────────────────────────────────


def add_todo(text: str, priority: str = "medium") -> Todo:
    """Add a new TODO. Returns the created item."""
    todos = _load_todos()
    todo = Todo(
        id=_next_id(todos),
        text=text.strip(),
        priority=priority if priority in ("high", "medium", "low") else "medium",
        created_at=datetime.now().isoformat(),
    )
    todos.append(todo)
    _save_todos(todos)
    logger.info("Todo added: #%d '%s' (%s)", todo.id, todo.text, todo.priority)
    return todo


def list_todos(include_done: bool = False) -> list[Todo]:
    """List todos. By default only pending ones, sorted by priority."""
    todos = _load_todos()
    if not include_done:
        todos = [t for t in todos if not t.done]
    # Sort: high > medium > low
    priority_order = {"high": 0, "medium": 1, "low": 2}
    todos.sort(key=lambda t: priority_order.get(t.priority, 1))
    return todos


def get_top_tasks(limit: int = 5) -> list[Todo]:
    """Get top N most urgent pending tasks (for briefing)."""
    return list_todos(include_done=False)[:limit]


def mark_done(task_id: int) -> Todo | None:
    """Mark a task as done. Returns the task or None if not found."""
    todos = _load_todos()
    for t in todos:
        if t.id == task_id:
            t.done = True
            t.done_at = datetime.now().isoformat()
            _save_todos(todos)
            return t
    return None


def remove_todo(task_id: int) -> bool:
    """Remove a task entirely. Returns True if found and removed."""
    todos = _load_todos()
    original_len = len(todos)
    todos = [t for t in todos if t.id != task_id]
    if len(todos) < original_len:
        _save_todos(todos)
        return True
    return False


def import_from_intelligence(tasks: list[dict]) -> int:
    """Import tasks from Intelligence API (calendar, inferred).

    Avoids duplicates by checking text similarity.
    Returns number of tasks imported.
    """
    todos = _load_todos()
    existing_texts = {t.text.lower() for t in todos}
    imported = 0

    for task in tasks:
        text = task.get("text", "").strip()
        if not text or text.lower() in existing_texts:
            continue
        todo = Todo(
            id=_next_id(todos),
            text=text,
            priority=task.get("priority", "medium"),
            created_at=datetime.now().isoformat(),
            source=task.get("source", "intelligence"),
        )
        todos.append(todo)
        existing_texts.add(text.lower())
        imported += 1

    if imported:
        _save_todos(todos)
    return imported
