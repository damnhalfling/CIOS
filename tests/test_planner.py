"""Tests for the Planner module."""

from unittest.mock import patch, MagicMock

import pytest

from harmoni.core.executor import Executor, ExecResult
from harmoni.core.intent_parser import Intent, IntentType
from harmoni.core.memory import Memory
from harmoni.core.mcp import ContextSnapshot, WifiState, AudioState, BatteryState
from harmoni.core.planner import Planner, PlanResult


@pytest.fixture
def planner(tmp_path):
    """Provide a Planner with real Memory and Executor (isolated DB)."""
    from unittest.mock import patch as _patch

    db_path = tmp_path / "test_planner.db"
    with _patch("harmoni.core.config.DB_PATH", db_path), \
         _patch("harmoni.core.config.ensure_dirs", lambda: None):
        executor = Executor()
        memory = Memory()
        p = Planner(executor, memory)
        yield p
        memory.close()


class TestPlannerRouting:
    """Intent routing to correct handlers."""

    def test_unknown_intent_returns_failure(self, planner):
        intent = Intent(type=IntentType.UNKNOWN, confidence=0.0, raw_input="gibberish")
        result = planner.execute(intent)
        assert result.outcome == "failure"
        assert "don't understand" in result.summary.lower()

    def test_session_missing_action(self, planner):
        intent = Intent(type=IntentType.SESSION, confidence=0.9, params={})
        result = planner.execute(intent)
        assert result.outcome == "failure"

    def test_process_control_missing_port(self, planner):
        intent = Intent(type=IntentType.PROCESS_CONTROL, confidence=0.9, params={"action": "kill"})
        result = planner.execute(intent)
        assert result.outcome == "failure"
        assert "port" in result.summary.lower()

    def test_command_exec_missing_command(self, planner):
        intent = Intent(type=IntentType.COMMAND_EXEC, confidence=0.9, params={})
        result = planner.execute(intent)
        assert result.outcome == "failure"

    def test_app_launch_missing_app(self, planner):
        intent = Intent(type=IntentType.APP_LAUNCH, confidence=0.9, params={})
        result = planner.execute(intent)
        assert result.outcome == "failure"


class TestMCOPrecheck:
    """MCO (context-aware decision layer) pre-checks."""

    def test_audio_status_from_mcp(self, planner):
        """Audio status should be resolved from MCP state (instant)."""
        mock_snap = ContextSnapshot(
            audio=AudioState(volume=75, muted=False),
        )
        with patch("harmoni.core.planner.mcp") as mock_mcp:
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.audio = mock_snap.audio

            intent = Intent(type=IntentType.AUDIO, confidence=0.9, params={"action": "status"})
            result = planner.execute(intent)
            assert result.outcome == "success"
            assert "75%" in result.summary

    def test_audio_already_muted(self, planner):
        """If already muted, MCO short-circuits."""
        mock_snap = ContextSnapshot(
            audio=AudioState(volume=50, muted=True),
        )
        with patch("harmoni.core.planner.mcp") as mock_mcp:
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.audio = mock_snap.audio

            intent = Intent(type=IntentType.AUDIO, confidence=0.9, params={"action": "mute"})
            result = planner.execute(intent)
            assert result.outcome == "success"
            assert "already muted" in result.summary.lower()

    def test_network_status_from_mcp(self, planner):
        """Network status resolved from MCP state."""
        mock_snap = ContextSnapshot(
            wifi=WifiState(connected=True, ssid="Casa", signal=90, ip="192.168.1.5"),
        )
        with patch("harmoni.core.planner.mcp") as mock_mcp:
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.wifi = mock_snap.wifi

            intent = Intent(type=IntentType.NETWORK, confidence=0.9, params={"action": "status"})
            result = planner.execute(intent)
            assert result.outcome == "success"
            assert "Casa" in result.summary

    def test_network_already_connected(self, planner):
        """If already connected to requested SSID, MCO short-circuits."""
        mock_snap = ContextSnapshot(
            wifi=WifiState(connected=True, ssid="Casa", signal=90),
        )
        with patch("harmoni.core.planner.mcp") as mock_mcp:
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.wifi = mock_snap.wifi

            intent = Intent(
                type=IntentType.NETWORK, confidence=0.9,
                params={"action": "connect", "ssid": "Casa"},
            )
            result = planner.execute(intent)
            assert result.outcome == "success"
            assert "already connected" in result.summary.lower()


class TestPlannerCommandExec:
    """Command execution handler."""

    def test_command_exec_success(self, planner):
        intent = Intent(
            type=IntentType.COMMAND_EXEC, confidence=0.9,
            params={"command": "echo hello world"},
            raw_input="run echo hello world",
        )
        result = planner.execute(intent)
        assert result.outcome == "success"
        assert "hello world" in result.summary

    def test_command_exec_failure(self, planner):
        intent = Intent(
            type=IntentType.COMMAND_EXEC, confidence=0.9,
            params={"command": "false"},
            raw_input="run false",
        )
        result = planner.execute(intent)
        assert result.outcome == "failure"


class TestPlannerPower:
    """Power handler."""

    def test_battery_status_no_battery(self, planner):
        mock_snap = ContextSnapshot(
            battery=BatteryState(present=False),
        )
        with patch("harmoni.core.planner.mcp") as mock_mcp:
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.battery = mock_snap.battery

            intent = Intent(
                type=IntentType.POWER, confidence=0.9,
                params={"action": "battery_status"},
                raw_input="quanta bateria",
            )
            result = planner.execute(intent)
            assert result.outcome == "success"
            assert "no battery" in result.summary.lower() or "AC power" in result.summary

    def test_battery_status_low(self, planner):
        mock_snap = ContextSnapshot(
            battery=BatteryState(present=True, percent=10, charging=False, time_remaining="0h30m"),
        )
        with patch("harmoni.core.planner.mcp") as mock_mcp:
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.battery = mock_snap.battery

            intent = Intent(
                type=IntentType.POWER, confidence=0.9,
                params={"action": "battery_status"},
                raw_input="battery status",
            )
            result = planner.execute(intent)
            assert result.outcome == "success"
            assert "10%" in result.summary
            assert "critically low" in result.summary.lower()


class TestPlannerMemoryIntegration:
    """Planner stores results in memory."""

    def test_stores_success_in_memory(self, planner):
        intent = Intent(
            type=IntentType.COMMAND_EXEC, confidence=0.9,
            params={"command": "echo test"},
            raw_input="run echo test",
        )
        planner.execute(intent)

        recent = planner.memory.recent(1)
        assert len(recent) == 1
        assert recent[0].intent == "command_exec"
        assert recent[0].outcome == "success"

    def test_stores_failure_in_memory(self, planner):
        intent = Intent(
            type=IntentType.COMMAND_EXEC, confidence=0.9,
            params={"command": "exit 1"},
            raw_input="run exit 1",
        )
        result = planner.execute(intent)

        recent = planner.memory.recent(1)
        assert len(recent) == 1
        assert recent[0].outcome == "failure"
