"""Tests for the Planner module."""

from unittest.mock import patch

import pytest

from cios.core.executor import Executor
from cios.core.intent_parser import Intent, IntentType
from cios.core.mcp import AudioState, BatteryState, ContextSnapshot, WifiState
from cios.core.memory import Memory
from cios.core.planner import Planner


@pytest.fixture
def planner(tmp_path):
    """Provide a Planner with real Memory and Executor (isolated DB)."""
    from unittest.mock import patch as _patch

    db_path = tmp_path / "test_planner.db"
    with (
        _patch("cios.core.config.DB_PATH", db_path),
        _patch("cios.core.config.ensure_dirs", lambda: None),
    ):
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
        assert (
            "don't understand" in result.summary.lower() or "não entendi" in result.summary.lower()
        )

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
        with (
            patch("cios.core.planner.mcp") as mock_mcp,
            patch("cios.core.handlers.audio.mcp") as mock_mcp2,
        ):
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.audio = mock_snap.audio
            mock_mcp2.audio = mock_snap.audio

            intent = Intent(type=IntentType.AUDIO, confidence=0.9, params={"action": "status"})
            result = planner.execute(intent)
            assert result.outcome == "success"
            assert "75%" in result.summary

    def test_audio_already_muted(self, planner):
        """If already muted, MCO short-circuits."""
        mock_snap = ContextSnapshot(
            audio=AudioState(volume=50, muted=True),
        )
        with patch("cios.core.planner.mcp") as mock_mcp:
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
        with (
            patch("cios.core.planner.mcp") as mock_mcp,
            patch("cios.core.handlers.network.mcp") as mock_mcp2,
        ):
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.wifi = mock_snap.wifi
            mock_mcp2.wifi = mock_snap.wifi

            intent = Intent(type=IntentType.NETWORK, confidence=0.9, params={"action": "status"})
            result = planner.execute(intent)
            assert result.outcome == "success"
            assert "Casa" in result.summary

    def test_network_already_connected(self, planner):
        """If already connected to requested SSID, MCO short-circuits."""
        mock_snap = ContextSnapshot(
            wifi=WifiState(connected=True, ssid="Casa", signal=90),
        )
        with (
            patch("cios.core.planner.mcp") as mock_mcp,
            patch("cios.core.handlers.network.mcp") as mock_mcp2,
        ):
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.wifi = mock_snap.wifi
            mock_mcp2.wifi = mock_snap.wifi

            intent = Intent(
                type=IntentType.NETWORK,
                confidence=0.9,
                params={"action": "connect", "ssid": "Casa"},
            )
            result = planner.execute(intent)
            assert result.outcome == "success"
            assert "already connected" in result.summary.lower()


class TestPlannerCommandExec:
    """Command execution handler."""

    def test_command_exec_success(self, planner):
        intent = Intent(
            type=IntentType.COMMAND_EXEC,
            confidence=0.9,
            params={"command": "echo hello world"},
            raw_input="run echo hello world",
        )
        result = planner.execute(intent)
        assert result.outcome == "success"
        assert "hello world" in result.summary

    def test_command_exec_failure(self, planner):
        intent = Intent(
            type=IntentType.COMMAND_EXEC,
            confidence=0.9,
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
        with (
            patch("cios.core.planner.mcp") as mock_mcp,
            patch("cios.core.handlers.system.mcp") as mock_mcp2,
        ):
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.battery = mock_snap.battery
            mock_mcp2.battery = mock_snap.battery

            intent = Intent(
                type=IntentType.POWER,
                confidence=0.9,
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
        with (
            patch("cios.core.planner.mcp") as mock_mcp,
            patch("cios.core.handlers.system.mcp") as mock_mcp2,
        ):
            mock_mcp.snapshot.return_value = mock_snap
            mock_mcp.battery = mock_snap.battery
            mock_mcp2.battery = mock_snap.battery

            intent = Intent(
                type=IntentType.POWER,
                confidence=0.9,
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
            type=IntentType.COMMAND_EXEC,
            confidence=0.9,
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
            type=IntentType.COMMAND_EXEC,
            confidence=0.9,
            params={"command": "exit 1"},
            raw_input="run exit 1",
        )
        result = planner.execute(intent)

        recent = planner.memory.recent(1)
        assert len(recent) == 1
        assert recent[0].outcome == "failure"


class TestContinueProjectHandler:
    """Unit tests for _handle_continue_project handler.

    Validates: Requirements 2.2, 2.4, 2.5
    """

    def test_bare_continuar_resolves_to_most_recent_project(self, planner):
        """Bare 'continuar' with no project param uses the most recent session.

        Validates: Requirements 2.4
        """
        from cios.core.memory import SessionContext

        # Save two sessions with different timestamps — "beta" is more recent
        planner.memory.save_session(
            SessionContext(
                project_name="alpha",
                project_path="/tmp/alpha",
                project_type="node",
                editor_command="code",
                server_pid=1000,
                server_port=3000,
                browser_url="http://localhost:3000",
                start_command="npm run dev",
                timestamp=100.0,
            )
        )
        planner.memory.save_session(
            SessionContext(
                project_name="beta",
                project_path="/tmp/beta",
                project_type="node",
                editor_command="code",
                server_pid=2000,
                server_port=4000,
                browser_url="http://localhost:4000",
                start_command="npm run dev",
                timestamp=200.0,
            )
        )

        intent = Intent(
            type=IntentType.CONTINUE_PROJECT,
            confidence=0.9,
            params={},
            raw_input="continuar",
        )

        with (
            patch("cios.core.handlers.dev._is_port_in_use", return_value=True),
            patch("cios.core.handlers.dev._detect_editor", return_value="code"),
            patch("cios.core.handlers.dev._open_editor") as mock_editor,
            patch("cios.core.handlers.dev._open_browser") as mock_browser,
            patch("os.path.exists", return_value=True),
        ):
            result = planner._handle_continue_project(intent)

        assert result.outcome == "success"
        # Should restore "beta" (most recent, timestamp=200)
        assert "beta" in result.summary.lower() or "beta" in " ".join(result.plan_steps).lower()
        mock_editor.assert_called_once_with("code", "/tmp/beta")
        mock_browser.assert_called_once()

    def test_continuar_projeto_x_with_existing_session(self, planner):
        """'continuar projeto fidelidade' restores the named session.

        Validates: Requirements 2.2
        """
        from cios.core.memory import SessionContext

        planner.memory.save_session(
            SessionContext(
                project_name="fidelidade",
                project_path="/tmp/fidelidade",
                project_type="node",
                editor_command="code",
                server_pid=5000,
                server_port=3001,
                browser_url="http://localhost:3001",
                start_command="npm run dev",
                timestamp=300.0,
            )
        )

        intent = Intent(
            type=IntentType.CONTINUE_PROJECT,
            confidence=0.95,
            params={"project": "fidelidade"},
            raw_input="continuar projeto fidelidade",
        )

        with (
            patch("cios.core.handlers.dev._is_port_in_use", return_value=True),
            patch("cios.core.handlers.dev._detect_editor", return_value="code"),
            patch("cios.core.handlers.dev._open_editor") as mock_editor,
            patch("cios.core.handlers.dev._open_browser") as mock_browser,
            patch("os.path.exists", return_value=True),
        ):
            result = planner._handle_continue_project(intent)

        assert result.outcome == "success"
        assert "fidelidade" in result.summary.lower()
        mock_editor.assert_called_once_with("code", "/tmp/fidelidade")
        mock_browser.assert_called_once()

    def test_deleted_project_path_returns_error_with_suggestions(self, planner):
        """When the saved project path no longer exists, return error + available projects.

        Validates: Requirements 2.5
        """
        from cios.core.memory import SessionContext

        planner.memory.save_session(
            SessionContext(
                project_name="deleted-app",
                project_path="/tmp/deleted-app",
                project_type="node",
                editor_command="code",
                server_port=3000,
                browser_url="http://localhost:3000",
                start_command="npm run dev",
                timestamp=100.0,
            )
        )
        planner.memory.save_session(
            SessionContext(
                project_name="other-project",
                project_path="/tmp/other-project",
                project_type="python",
                editor_command="code",
                server_port=8000,
                browser_url="http://localhost:8000",
                start_command="python manage.py runserver",
                timestamp=200.0,
            )
        )

        intent = Intent(
            type=IntentType.CONTINUE_PROJECT,
            confidence=0.95,
            params={"project": "deleted-app"},
            raw_input="continuar projeto deleted-app",
        )

        def fake_exists(path):
            # deleted-app path doesn't exist, other-project does
            return "deleted-app" not in str(path)

        with patch("os.path.exists", side_effect=fake_exists):
            result = planner._handle_continue_project(intent)

        assert result.outcome == "failure"
        assert "não encontrado" in result.summary.lower() or "removido" in result.summary.lower()
        # Should suggest available projects
        assert "other-project" in result.summary

    def test_no_sessions_at_all_returns_failure(self, planner):
        """Bare 'continuar' with empty memory returns failure.

        Validates: Requirements 2.4
        """
        intent = Intent(
            type=IntentType.CONTINUE_PROJECT,
            confidence=0.9,
            params={},
            raw_input="continuar",
        )

        result = planner._handle_continue_project(intent)

        assert result.outcome == "failure"
        assert "no recent projects" in result.summary.lower()

    def test_project_not_found_but_others_exist(self, planner):
        """Named project not in sessions, but other sessions exist → failure + suggestions.

        Validates: Requirements 2.5
        """
        from cios.core.memory import SessionContext

        planner.memory.save_session(
            SessionContext(
                project_name="webapp",
                project_path="/tmp/webapp",
                project_type="node",
                editor_command="code",
                server_port=3000,
                browser_url="http://localhost:3000",
                start_command="npm run dev",
                timestamp=100.0,
            )
        )
        planner.memory.save_session(
            SessionContext(
                project_name="api-service",
                project_path="/tmp/api-service",
                project_type="python",
                editor_command="code",
                server_port=8000,
                browser_url="http://localhost:8000",
                start_command="python manage.py runserver",
                timestamp=200.0,
            )
        )

        intent = Intent(
            type=IntentType.CONTINUE_PROJECT,
            confidence=0.95,
            params={"project": "nonexistent"},
            raw_input="continuar projeto nonexistent",
        )

        result = planner._handle_continue_project(intent)

        assert result.outcome == "failure"
        assert "não encontrado" in result.summary.lower()
        # Should list available projects as suggestions
        assert "webapp" in result.summary or "api-service" in result.summary
