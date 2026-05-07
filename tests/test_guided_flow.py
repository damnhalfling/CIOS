"""Tests for the Guided Flow Engine (GuidedFlowStep, GuidedFlow, multi-step flows)."""

from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from cios.core.bridge import (
    GuidedFlowStep,
    GuidedFlow,
    CIOSBridge,
    PendingQuestion,
)
from cios.core.intent_parser import Intent, IntentType


# ═══════════════════════════════════════════════════════════════════════════
#  DATACLASS TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestGuidedFlowStep:
    """GuidedFlowStep dataclass construction and defaults."""

    def test_basic_construction(self):
        step = GuidedFlowStep(
            question="Pick a network",
            question_type="choice",
            options=["Net1", "Net2"],
            param_key="ssid",
        )
        assert step.question == "Pick a network"
        assert step.question_type == "choice"
        assert step.options == ["Net1", "Net2"]
        assert step.param_key == "ssid"

    def test_defaults(self):
        step = GuidedFlowStep(question="Enter name", question_type="text")
        assert step.options == []
        assert step.param_key == ""

    def test_password_step(self):
        step = GuidedFlowStep(
            question="Senha para {ssid}?",
            question_type="password",
            param_key="password",
        )
        assert step.question_type == "password"
        assert "{ssid}" in step.question


class TestGuidedFlow:
    """GuidedFlow dataclass construction and defaults."""

    def test_basic_construction(self):
        intent = Intent(type=IntentType.NETWORK, confidence=0.9, params={"action": "connect"})
        steps = [
            GuidedFlowStep(question="Q1", question_type="choice", options=["A"], param_key="ssid"),
            GuidedFlowStep(question="Q2", question_type="password", param_key="password"),
        ]
        flow = GuidedFlow(intent=intent, steps=steps)
        assert flow.intent is intent
        assert len(flow.steps) == 2
        assert flow.current_step == 0
        assert flow.collected == {}

    def test_defaults(self):
        intent = Intent(type=IntentType.UNKNOWN, confidence=0.0)
        flow = GuidedFlow(intent=intent)
        assert flow.steps == []
        assert flow.current_step == 0
        assert flow.collected == {}


class TestPendingQuestionExtension:
    """PendingQuestion now supports flow_steps and flow_collected."""

    def test_legacy_pending_question_still_works(self):
        intent = Intent(type=IntentType.APP_LAUNCH, confidence=0.9, params={})
        pq = PendingQuestion(intent=intent, question_type="app", timestamp=1.0)
        assert pq.flow_steps is None
        assert pq.flow_collected == {}

    def test_pending_question_with_flow_steps(self):
        intent = Intent(type=IntentType.NETWORK, confidence=0.9, params={"action": "connect"})
        steps = [
            GuidedFlowStep(question="Q1", question_type="choice", options=["A"], param_key="ssid"),
        ]
        pq = PendingQuestion(
            intent=intent,
            question_type="ssid",
            options=["A"],
            timestamp=1.0,
            flow_steps=steps,
            flow_collected={"existing": "value"},
        )
        assert pq.flow_steps is not None
        assert len(pq.flow_steps) == 1
        assert pq.flow_collected == {"existing": "value"}


# ═══════════════════════════════════════════════════════════════════════════
#  INTEGRATION TESTS — MULTI-STEP NETWORK FLOW
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def bridge():
    """Provide a Bridge instance with MCP mocked (no real system polling)."""
    with patch("cios.core.mcp.context") as mock_ctx:
        mock_ctx.start = MagicMock()
        mock_ctx.stop = MagicMock()
        mock_ctx.boot_times = {}
        from cios.core.mcp import ContextSnapshot, SystemState
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
        b = CIOSBridge()
        yield b
        b.close()


class TestGuidedFlowNetworkConnect:
    """Multi-step guided flow for network connect (SSID → password)."""

    def test_network_connect_no_ssid_builds_guided_flow(self, bridge):
        """Network connect without SSID triggers guided flow with flow_steps."""
        from cios.skills.network import WifiNetwork

        networks = [
            WifiNetwork(ssid="HomeNet", signal=80, security="WPA2"),
            WifiNetwork(ssid="CafeWifi", signal=60, security="WPA2"),
        ]

        with patch("cios.skills.network.list_networks", return_value=networks), \
             patch("cios.core.mcp.context") as mock_mcp:
            # Not connected, no known networks
            mock_mcp.wifi.connected = False
            mock_mcp.known_networks = []

            result = bridge.execute_command("conectar wifi")

        assert result["status"] == "success"
        assert "HomeNet" in result["result"]
        assert "CafeWifi" in result["result"]
        # Should have set a pending question with flow_steps
        assert bridge._pending_question is not None
        assert bridge._pending_question.flow_steps is not None
        assert len(bridge._pending_question.flow_steps) == 2

    def test_guided_flow_ssid_then_password(self, bridge):
        """Full multi-step: pick SSID → enter password → execute."""
        from cios.skills.network import WifiNetwork

        networks = [
            WifiNetwork(ssid="HomeNet", signal=80, security="WPA2"),
            WifiNetwork(ssid="CafeWifi", signal=60, security="WPA2"),
        ]

        with patch("cios.skills.network.list_networks", return_value=networks), \
             patch("cios.core.mcp.context") as mock_mcp:
            mock_mcp.wifi.connected = False
            mock_mcp.known_networks = []

            # Step 1: trigger the guided flow
            result1 = bridge.execute_command("conectar wifi")
            assert "HomeNet" in result1["result"]

        # Step 2: answer with SSID (unknown network → should ask password)
        with patch("cios.core.mcp.context") as mock_mcp:
            mock_mcp.known_networks = []  # Not a known network
            mock_mcp.notify_activity = MagicMock()

            result2 = bridge.execute_command("HomeNet")

        assert result2["status"] == "success"
        assert "Senha" in result2["result"] or "password" in result2["result"].lower()
        assert bridge._pending_question is not None

        # Step 3: answer with password → should execute
        with patch("cios.core.mcp.context") as mock_mcp, \
             patch("cios.core.bridge.CIOSBridge._execute_intent") as mock_exec:
            mock_mcp.notify_activity = MagicMock()
            mock_exec.return_value = {
                "steps": ["Connecting to HomeNet"],
                "result": "Conectado a HomeNet",
                "status": "success",
                "confirm": None,
                "voice_mode": "full",
            }

            result3 = bridge.execute_command("mypassword123")

        assert result3["status"] == "success"
        # Verify the intent was called with both ssid and password
        call_args = mock_exec.call_args
        intent_arg = call_args[0][0]
        assert intent_arg.params["ssid"] == "HomeNet"
        assert intent_arg.params["password"] == "mypassword123"

    def test_guided_flow_known_network_skips_password(self, bridge):
        """Known network skips the password step and executes directly."""
        from cios.skills.network import WifiNetwork

        networks = [
            WifiNetwork(ssid="SavedNet", signal=90, security="WPA2"),
        ]

        with patch("cios.skills.network.list_networks", return_value=networks), \
             patch("cios.core.mcp.context") as mock_mcp:
            mock_mcp.wifi.connected = False
            mock_mcp.known_networks = []

            # Step 1: trigger guided flow
            result1 = bridge.execute_command("conectar wifi")
            assert "SavedNet" in result1["result"]

        # Step 2: answer with SSID of a known network → should skip password
        with patch("cios.core.mcp.context") as mock_mcp, \
             patch("cios.core.bridge.CIOSBridge._execute_intent") as mock_exec:
            mock_mcp.known_networks = ["SavedNet"]  # Known network!
            mock_mcp.notify_activity = MagicMock()
            mock_exec.return_value = {
                "steps": ["Connecting to SavedNet"],
                "result": "Conectado a SavedNet",
                "status": "success",
                "confirm": None,
                "voice_mode": "full",
            }

            result2 = bridge.execute_command("SavedNet")

        # Should have executed directly (no password prompt)
        assert result2["status"] == "success"
        assert bridge._pending_question is None
        mock_exec.assert_called_once()

    def test_guided_flow_numeric_selection(self, bridge):
        """User can select a network by number (1-based index)."""
        from cios.skills.network import WifiNetwork

        networks = [
            WifiNetwork(ssid="Alpha", signal=90, security="WPA2"),
            WifiNetwork(ssid="Beta", signal=70, security="WPA2"),
            WifiNetwork(ssid="Gamma", signal=50, security="Open"),
        ]

        with patch("cios.skills.network.list_networks", return_value=networks), \
             patch("cios.core.mcp.context") as mock_mcp:
            mock_mcp.wifi.connected = False
            mock_mcp.known_networks = []

            bridge.execute_command("conectar wifi")

        # Select network #2 (Beta) — unknown, should ask password
        with patch("cios.core.mcp.context") as mock_mcp:
            mock_mcp.known_networks = []
            result = bridge.execute_command("2")

        assert "Beta" in result["result"] or "Senha" in result["result"]
        # The pending question should have collected ssid=Beta
        assert bridge._pending_question is not None
        assert bridge._pending_question.flow_collected.get("ssid") == "Beta"


class TestGuidedFlowBackwardCompatibility:
    """Existing single-question flows still work after the refactoring."""

    def test_app_launch_clarification_still_works(self, bridge):
        """APP_LAUNCH without app name still uses legacy single-question path."""
        # "abrir" alone parses as UNKNOWN, so mock the intent to APP_LAUNCH with no app
        mock_intent = Intent(type=IntentType.APP_LAUNCH, confidence=0.9, params={})
        with patch("cios.core.bridge.parse_intent", return_value=mock_intent):
            result = bridge.execute_command("abrir")
        assert "app" in result["result"].lower() or "Qual" in result["result"]
        assert bridge._pending_question is not None
        assert bridge._pending_question.flow_steps is None  # Legacy path

    def test_process_control_clarification_still_works(self, bridge):
        """PROCESS_CONTROL kill without port still uses legacy path."""
        result = bridge.execute_command("matar processo na porta")
        assert "porta" in result["result"].lower() or "Qual" in result["result"]
        assert bridge._pending_question is not None
        assert bridge._pending_question.flow_steps is None

    def test_file_organize_clarification_still_works(self, bridge):
        """FILE_ORGANIZE without target still uses legacy path."""
        mock_intent = Intent(type=IntentType.FILE_ORGANIZE, confidence=0.9, params={})
        with patch("cios.core.bridge.parse_intent", return_value=mock_intent):
            result = bridge.execute_command("organizar")
        assert bridge._pending_question is not None
        assert bridge._pending_question.flow_steps is None
        assert bridge._pending_question.question_type == "target"
