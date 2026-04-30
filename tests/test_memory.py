"""Tests for the Memory module."""

import time

import pytest

from harmoni.core.memory import Memory, MemoryRecord


@pytest.fixture
def memory(tmp_path):
    """Provide a fresh Memory instance with isolated DB per test."""
    from unittest.mock import patch

    db_path = tmp_path / "test_memory.db"
    with patch("harmoni.core.config.DB_PATH", db_path), \
         patch("harmoni.core.config.ensure_dirs", lambda: None):
        mem = Memory()
        yield mem
        mem.close()


class TestMemoryStore:
    """Storing and retrieving records."""

    def test_store_and_retrieve(self, memory):
        record = MemoryRecord(
            timestamp=time.time(),
            user_input="start my backend",
            intent="dev_start",
            plan=["Install deps", "Start server"],
            commands=["npm install", "npm run dev"],
            outcome="success",
        )
        memory.store(record)

        recent = memory.recent(1)
        assert len(recent) == 1
        assert recent[0].user_input == "start my backend"
        assert recent[0].intent == "dev_start"
        assert recent[0].outcome == "success"
        assert recent[0].plan == ["Install deps", "Start server"]
        assert recent[0].commands == ["npm install", "npm run dev"]

    def test_store_with_error(self, memory):
        record = MemoryRecord(
            timestamp=time.time(),
            user_input="start server",
            intent="dev_start",
            plan=["Start server"],
            commands=["npm run dev"],
            outcome="failure",
            error="EADDRINUSE: port 3000 in use",
        )
        memory.store(record)

        recent = memory.recent(1)
        assert recent[0].error == "EADDRINUSE: port 3000 in use"

    def test_store_with_context(self, memory):
        record = MemoryRecord(
            timestamp=time.time(),
            user_input="start backend",
            intent="dev_start",
            plan=["Start"],
            commands=["npm start"],
            outcome="success",
            context={"target": "backend", "port": 3000},
        )
        memory.store(record)

        recent = memory.recent(1)
        assert recent[0].context == {"target": "backend", "port": 3000}


class TestMemoryLastFailure:
    """Retrieving last failure."""

    def test_last_failure_returns_most_recent(self, memory):
        # Store a success
        memory.store(MemoryRecord(
            timestamp=time.time() - 100,
            user_input="open chrome",
            intent="app_launch",
            plan=["Open Chrome"],
            commands=[],
            outcome="success",
        ))
        # Store a failure
        memory.store(MemoryRecord(
            timestamp=time.time() - 50,
            user_input="start server",
            intent="dev_start",
            plan=["Start"],
            commands=["npm start"],
            outcome="failure",
            error="EADDRINUSE: port 3000 in use",
        ))
        # Store another success
        memory.store(MemoryRecord(
            timestamp=time.time(),
            user_input="check status",
            intent="status",
            plan=["Check"],
            commands=[],
            outcome="success",
        ))

        last = memory.last_failure()
        assert last is not None
        assert last.intent == "dev_start"
        assert "port 3000" in last.error

    def test_last_failure_by_intent(self, memory):
        memory.store(MemoryRecord(
            timestamp=time.time(),
            user_input="start server",
            intent="dev_start",
            plan=["Start"],
            commands=[],
            outcome="failure",
            error="Port in use",
        ))
        memory.store(MemoryRecord(
            timestamp=time.time(),
            user_input="connect wifi",
            intent="network",
            plan=["Connect"],
            commands=[],
            outcome="failure",
            error="Network not found",
        ))

        last = memory.last_failure(intent="dev_start")
        assert last is not None
        assert last.intent == "dev_start"

    def test_last_failure_none_when_no_failures(self, memory):
        memory.store(MemoryRecord(
            timestamp=time.time(),
            user_input="open chrome",
            intent="app_launch",
            plan=["Open"],
            commands=[],
            outcome="success",
        ))
        last = memory.last_failure()
        assert last is None

    def test_recovered_counts_as_failure(self, memory):
        memory.store(MemoryRecord(
            timestamp=time.time(),
            user_input="start server",
            intent="dev_start",
            plan=["Start"],
            commands=[],
            outcome="recovered",
            error="Port conflict resolved",
        ))

        last = memory.last_failure()
        assert last is not None
        assert last.outcome == "recovered"


class TestMemoryRecent:
    """Retrieving recent records."""

    def test_recent_respects_limit(self, memory):
        for i in range(20):
            memory.store(MemoryRecord(
                timestamp=time.time() + i,
                user_input=f"command {i}",
                intent="command_exec",
                plan=[f"Step {i}"],
                commands=[f"cmd {i}"],
                outcome="success",
            ))

        recent = memory.recent(5)
        assert len(recent) == 5

    def test_recent_ordered_by_timestamp_desc(self, memory):
        for i in range(5):
            memory.store(MemoryRecord(
                timestamp=1000.0 + i,
                user_input=f"command {i}",
                intent="command_exec",
                plan=[],
                commands=[],
                outcome="success",
            ))

        recent = memory.recent(5)
        assert recent[0].user_input == "command 4"
        assert recent[-1].user_input == "command 0"

    def test_recent_empty_db(self, memory):
        assert memory.recent(10) == []
