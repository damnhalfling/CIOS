"""SQLite-backed memory for intents, commands, and outcomes."""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional

from cios.core import config as _config


@dataclass
class MemoryRecord:
    timestamp: float
    user_input: str
    intent: str
    plan: list[str]
    commands: list[str]
    outcome: str  # "success" | "failure" | "recovered"
    error: Optional[str] = None
    context: dict = field(default_factory=dict)


@dataclass
class SessionContext:
    project_name: str
    project_path: str
    project_type: str  # "node", "python", etc.
    editor_command: str = ""
    server_pid: Optional[int] = None
    server_port: int = 0
    browser_url: str = ""
    start_command: str = ""
    timestamp: float = field(default_factory=time.time)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    user_input TEXT NOT NULL,
    intent TEXT NOT NULL,
    plan TEXT NOT NULL,
    commands TEXT NOT NULL,
    outcome TEXT NOT NULL,
    error TEXT,
    context TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_intent ON memory(intent);
CREATE INDEX IF NOT EXISTS idx_memory_timestamp ON memory(timestamp DESC);

CREATE TABLE IF NOT EXISTS session_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    project_path TEXT NOT NULL,
    project_type TEXT NOT NULL,
    editor_command TEXT DEFAULT '',
    server_pid INTEGER,
    server_port INTEGER DEFAULT 0,
    browser_url TEXT DEFAULT '',
    start_command TEXT DEFAULT '',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_project ON session_context(project_name);
CREATE INDEX IF NOT EXISTS idx_session_timestamp ON session_context(timestamp DESC);
"""


class Memory:
    """Persistent memory store. Thread-safe for use with HTTP servers."""

    def __init__(self) -> None:
        _config.ensure_dirs()
        self._conn = sqlite3.connect(str(_config.DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = __import__("threading").Lock()
        self._conn.executescript(_SCHEMA)

    def store(self, record: MemoryRecord) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO memory
                   (timestamp, user_input, intent, plan, commands, outcome, error, context)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.timestamp,
                    record.user_input,
                    record.intent,
                    json.dumps(record.plan),
                    json.dumps(record.commands),
                    record.outcome,
                    record.error,
                    json.dumps(record.context),
                ),
            )
            self._conn.commit()

    def last_failure(self, intent: Optional[str] = None) -> Optional[MemoryRecord]:
        """Get the most recent failure, optionally filtered by intent."""
        with self._lock:
            if intent:
                row = self._conn.execute(
                    """SELECT * FROM memory
                       WHERE outcome IN ('failure', 'recovered') AND intent = ?
                       ORDER BY timestamp DESC LIMIT 1""",
                    (intent,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    """SELECT * FROM memory
                       WHERE outcome IN ('failure', 'recovered')
                       ORDER BY timestamp DESC LIMIT 1""",
                ).fetchone()
        return self._row_to_record(row) if row else None

    def recent(self, limit: int = 10) -> list[MemoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            timestamp=row["timestamp"],
            user_input=row["user_input"],
            intent=row["intent"],
            plan=json.loads(row["plan"]),
            commands=json.loads(row["commands"]),
            outcome=row["outcome"],
            error=row["error"],
            context=json.loads(row["context"]) if row["context"] else {},
        )

    # --- Session Context ---

    def save_session(self, ctx: SessionContext) -> None:
        """Persist a session context. Replaces any existing session for the same project_name."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM session_context WHERE project_name = ?",
                (ctx.project_name,),
            )
            self._conn.execute(
                """INSERT INTO session_context
                   (project_name, project_path, project_type, editor_command,
                    server_pid, server_port, browser_url, start_command, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ctx.project_name,
                    ctx.project_path,
                    ctx.project_type,
                    ctx.editor_command,
                    ctx.server_pid,
                    ctx.server_port,
                    ctx.browser_url,
                    ctx.start_command,
                    ctx.timestamp,
                ),
            )
            self._conn.commit()

    def get_session(self, project_name: str) -> Optional[SessionContext]:
        """Retrieve the most recent session for a given project name."""
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM session_context
                   WHERE project_name = ?
                   ORDER BY timestamp DESC LIMIT 1""",
                (project_name,),
            ).fetchone()
        return self._row_to_session(row) if row else None

    def get_latest_session(self) -> Optional[SessionContext]:
        """Retrieve the session with the maximum timestamp across all projects."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM session_context ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self) -> list[SessionContext]:
        """List all saved sessions, most recent first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM session_context ORDER BY timestamp DESC"
            ).fetchall()
        return [self._row_to_session(r) for r in rows]

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> SessionContext:
        return SessionContext(
            project_name=row["project_name"],
            project_path=row["project_path"],
            project_type=row["project_type"],
            editor_command=row["editor_command"] or "",
            server_pid=row["server_pid"],
            server_port=row["server_port"] or 0,
            browser_url=row["browser_url"] or "",
            start_command=row["start_command"] or "",
            timestamp=row["timestamp"],
        )

    def close(self) -> None:
        self._conn.close()
