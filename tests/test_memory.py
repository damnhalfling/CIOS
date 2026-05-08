"""Tests for the Memory module."""

import time

import pytest

from cios.core.memory import Memory, MemoryRecord


@pytest.fixture
def memory(tmp_path):
    """Provide a fresh Memory instance with isolated DB per test."""
    from unittest.mock import patch

    db_path = tmp_path / "test_memory.db"
    with (
        patch("cios.core.config.DB_PATH", db_path),
        patch("cios.core.config.ensure_dirs", lambda: None),
    ):
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
        memory.store(
            MemoryRecord(
                timestamp=time.time() - 100,
                user_input="open chrome",
                intent="app_launch",
                plan=["Open Chrome"],
                commands=[],
                outcome="success",
            )
        )
        # Store a failure
        memory.store(
            MemoryRecord(
                timestamp=time.time() - 50,
                user_input="start server",
                intent="dev_start",
                plan=["Start"],
                commands=["npm start"],
                outcome="failure",
                error="EADDRINUSE: port 3000 in use",
            )
        )
        # Store another success
        memory.store(
            MemoryRecord(
                timestamp=time.time(),
                user_input="check status",
                intent="status",
                plan=["Check"],
                commands=[],
                outcome="success",
            )
        )

        last = memory.last_failure()
        assert last is not None
        assert last.intent == "dev_start"
        assert "port 3000" in last.error

    def test_last_failure_by_intent(self, memory):
        memory.store(
            MemoryRecord(
                timestamp=time.time(),
                user_input="start server",
                intent="dev_start",
                plan=["Start"],
                commands=[],
                outcome="failure",
                error="Port in use",
            )
        )
        memory.store(
            MemoryRecord(
                timestamp=time.time(),
                user_input="connect wifi",
                intent="network",
                plan=["Connect"],
                commands=[],
                outcome="failure",
                error="Network not found",
            )
        )

        last = memory.last_failure(intent="dev_start")
        assert last is not None
        assert last.intent == "dev_start"

    def test_last_failure_none_when_no_failures(self, memory):
        memory.store(
            MemoryRecord(
                timestamp=time.time(),
                user_input="open chrome",
                intent="app_launch",
                plan=["Open"],
                commands=[],
                outcome="success",
            )
        )
        last = memory.last_failure()
        assert last is None

    def test_recovered_counts_as_failure(self, memory):
        memory.store(
            MemoryRecord(
                timestamp=time.time(),
                user_input="start server",
                intent="dev_start",
                plan=["Start"],
                commands=[],
                outcome="recovered",
                error="Port conflict resolved",
            )
        )

        last = memory.last_failure()
        assert last is not None
        assert last.outcome == "recovered"


class TestMemoryRecent:
    """Retrieving recent records."""

    def test_recent_respects_limit(self, memory):
        for i in range(20):
            memory.store(
                MemoryRecord(
                    timestamp=time.time() + i,
                    user_input=f"command {i}",
                    intent="command_exec",
                    plan=[f"Step {i}"],
                    commands=[f"cmd {i}"],
                    outcome="success",
                )
            )

        recent = memory.recent(5)
        assert len(recent) == 5

    def test_recent_ordered_by_timestamp_desc(self, memory):
        for i in range(5):
            memory.store(
                MemoryRecord(
                    timestamp=1000.0 + i,
                    user_input=f"command {i}",
                    intent="command_exec",
                    plan=[],
                    commands=[],
                    outcome="success",
                )
            )

        recent = memory.recent(5)
        assert recent[0].user_input == "command 4"
        assert recent[-1].user_input == "command 0"

    def test_recent_empty_db(self, memory):
        assert memory.recent(10) == []


# --- Session Context Tests ---

from cios.core.memory import SessionContext


def _make_session(name: str = "fidelidade", **overrides) -> SessionContext:
    """Helper to create a SessionContext with sensible defaults."""
    defaults = dict(
        project_name=name,
        project_path=f"/home/user/projects/{name}",
        project_type="node",
        editor_command="code",
        server_pid=1234,
        server_port=3000,
        browser_url="http://localhost:3000",
        start_command="npm run dev",
        timestamp=time.time(),
    )
    defaults.update(overrides)
    return SessionContext(**defaults)


class TestSessionSaveAndGet:
    """Saving and retrieving session contexts."""

    def test_save_and_get_session(self, memory):
        ctx = _make_session("fidelidade")
        memory.save_session(ctx)

        result = memory.get_session("fidelidade")
        assert result is not None
        assert result.project_name == "fidelidade"
        assert result.project_path == "/home/user/projects/fidelidade"
        assert result.project_type == "node"
        assert result.editor_command == "code"
        assert result.server_pid == 1234
        assert result.server_port == 3000
        assert result.browser_url == "http://localhost:3000"
        assert result.start_command == "npm run dev"

    def test_save_replaces_existing_session(self, memory):
        ctx1 = _make_session("fidelidade", server_port=3000, timestamp=1000.0)
        ctx2 = _make_session("fidelidade", server_port=4000, timestamp=2000.0)

        memory.save_session(ctx1)
        memory.save_session(ctx2)

        result = memory.get_session("fidelidade")
        assert result is not None
        assert result.server_port == 4000
        assert result.timestamp == 2000.0

    def test_get_session_nonexistent(self, memory):
        assert memory.get_session("nonexistent") is None

    def test_save_session_with_none_server_pid(self, memory):
        ctx = _make_session("myapp", server_pid=None)
        memory.save_session(ctx)

        result = memory.get_session("myapp")
        assert result is not None
        assert result.server_pid is None

    def test_save_session_with_empty_optional_fields(self, memory):
        ctx = SessionContext(
            project_name="minimal",
            project_path="/tmp/minimal",
            project_type="python",
            timestamp=time.time(),
        )
        memory.save_session(ctx)

        result = memory.get_session("minimal")
        assert result is not None
        assert result.editor_command == ""
        assert result.server_pid is None
        assert result.server_port == 0
        assert result.browser_url == ""
        assert result.start_command == ""


class TestSessionGetLatest:
    """Retrieving the most recent session across all projects."""

    def test_get_latest_session(self, memory):
        memory.save_session(_make_session("alpha", timestamp=1000.0))
        memory.save_session(_make_session("beta", timestamp=3000.0))
        memory.save_session(_make_session("gamma", timestamp=2000.0))

        latest = memory.get_latest_session()
        assert latest is not None
        assert latest.project_name == "beta"

    def test_get_latest_session_empty_db(self, memory):
        assert memory.get_latest_session() is None


class TestSessionListSessions:
    """Listing all saved sessions."""

    def test_list_sessions_ordered_by_timestamp_desc(self, memory):
        memory.save_session(_make_session("alpha", timestamp=1000.0))
        memory.save_session(_make_session("beta", timestamp=3000.0))
        memory.save_session(_make_session("gamma", timestamp=2000.0))

        sessions = memory.list_sessions()
        assert len(sessions) == 3
        assert sessions[0].project_name == "beta"
        assert sessions[1].project_name == "gamma"
        assert sessions[2].project_name == "alpha"

    def test_list_sessions_empty_db(self, memory):
        assert memory.list_sessions() == []
