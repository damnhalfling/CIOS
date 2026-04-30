"""Tests for the Bridge module (integration)."""

from unittest.mock import patch, MagicMock

import pytest

from harmoni.core.bridge import HarmoniBridge


@pytest.fixture
def bridge():
    """Provide a Bridge instance with MCP mocked (no real system polling)."""
    with patch("harmoni.core.mcp.context") as mock_ctx:
        mock_ctx.start = MagicMock()
        mock_ctx.stop = MagicMock()
        mock_ctx.boot_times = {}
        # Mock snapshot for get_system_status (returns real-looking data)
        from harmoni.core.mcp import ContextSnapshot, SystemState
        mock_snapshot = ContextSnapshot(
            system=SystemState(
                cpu_percent=15.0,
                cpu_cores=4,
                mem_percent=45.2,
                mem_used_gb=3.6,
                mem_total_gb=8.0,
                disk_percent=55.0,
                disk_free_gb=100.0,
            ),
        )
        mock_ctx.snapshot.return_value = mock_snapshot
        b = HarmoniBridge()
        yield b
        b.close()


class TestBridgeBasic:
    """Basic bridge behavior."""

    def test_empty_command(self, bridge):
        result = bridge.execute_command("")
        assert result["status"] == "success"
        assert result["steps"] == []
        assert result["confirm"] is None

    def test_whitespace_command(self, bridge):
        result = bridge.execute_command("   ")
        assert result["status"] == "success"

    def test_result_structure(self, bridge):
        result = bridge.execute_command("echo hello")
        assert "steps" in result
        assert "result" in result
        assert "status" in result
        assert "confirm" in result
        assert "voice_mode" in result


class TestBridgeIntentRouting:
    """Bridge routes intents correctly."""

    def test_command_exec(self, bridge):
        result = bridge.execute_command("run echo hello", confirmed=True)
        assert result["status"] == "success"
        assert "hello" in result["result"]

    def test_unknown_intent_without_llm(self, bridge):
        """Unknown intent without LLM fallback returns error."""
        with patch("harmoni.core.bridge.resolve_unknown_intent", return_value=None):
            result = bridge.execute_command("asdfghjkl")
            assert result["status"] == "error"


class TestBridgeConfirmation:
    """Confirmation flow for destructive actions."""

    def test_file_organize_needs_confirmation(self, bridge):
        result = bridge.execute_command("organize my downloads")
        assert result["confirm"] is not None
        assert "organize" in result["confirm"].lower() or "Organize" in result["confirm"]

    def test_session_shutdown_needs_confirmation(self, bridge):
        result = bridge.execute_command("desligar")
        assert result["confirm"] is not None

    def test_session_reboot_needs_confirmation(self, bridge):
        result = bridge.execute_command("reiniciar")
        assert result["confirm"] is not None

    def test_suspend_no_confirmation(self, bridge):
        """Non-destructive session actions don't need confirmation."""
        with patch("harmoni.core.planner.execute_session_action") as mock_exec:
            mock_exec.return_value = (["Suspender (modo dormir)"], True, None)
            result = bridge.execute_command("suspender", confirmed=True)
            # suspend is not destructive, so no confirm
            assert result["confirm"] is None

    def test_disk_clean_needs_confirmation(self, bridge):
        result = bridge.execute_command("limpar cache")
        assert result["confirm"] is not None


class TestBridgeErrorHandling:
    """Error handling in bridge."""

    def test_exception_returns_error(self, bridge):
        with patch("harmoni.core.bridge.parse_intent", side_effect=RuntimeError("boom")):
            result = bridge.execute_command("anything")
            assert result["status"] == "error"


class TestBridgeSystemStatus:
    """System status endpoint."""

    def test_get_system_status_structure(self, bridge):
        status = bridge.get_system_status()
        assert "cpu_percent" in status
        assert "mem_percent" in status
        assert "disk_percent" in status
        assert "hostname" in status
        assert isinstance(status["cpu_percent"], float)
        assert isinstance(status["mem_total_gb"], float)


class TestBridgeRecentActivity:
    """Recent activity endpoint."""

    def test_get_recent_activity_empty(self, bridge):
        activity = bridge.get_recent_activity()
        assert isinstance(activity, list)

    def test_get_recent_activity_after_command(self, bridge):
        bridge.execute_command("run echo test", confirmed=True)
        activity = bridge.get_recent_activity()
        assert len(activity) >= 1
        assert "time" in activity[0]
        assert "text" in activity[0]
        assert "outcome" in activity[0]
