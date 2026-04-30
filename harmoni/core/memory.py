"""SQLite-backed memory for intents, commands, and outcomes."""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Optional

from harmoni.core import config as _config


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

    def close(self) -> None:
        self._conn.close()
