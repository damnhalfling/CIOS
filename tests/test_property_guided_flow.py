"""Property-based tests for Guided Flow.

Feature: produto-percebido, Property 7: Guided flow presents correct options for network connection
Feature: produto-percebido, Property 8: Conversation context preserves pending question state
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.bridge import CIOSBridge
from cios.core.intent_parser import Intent, IntentType
from cios.skills.network import WifiNetwork

# ═══════════════════════════════════════════════════════════════════════════
#  STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════

# Generate valid SSIDs: non-empty printable strings without newlines or colons
# (colons are used as nmcli delimiter, so real SSIDs parsed by list_networks
# won't contain them; newlines would break the display)
_ssid = (
    st.text(
        alphabet=st.sampled_from(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- "
        ),
        min_size=1,
        max_size=32,
    )
    .map(str.strip)
    .filter(lambda s: len(s) > 0 and not s.isdigit())
)

# Generate signal strengths in valid range
_signal = st.integers(min_value=0, max_value=100)

# Generate a single WifiNetwork
_wifi_network = st.builds(
    WifiNetwork,
    ssid=_ssid,
    signal=_signal,
    security=st.sampled_from(["WPA2", "WPA3", "Open", "WEP"]),
    active=st.just(False),
)

# Generate non-empty lists of WifiNetwork with unique SSIDs (up to 8, matching
# the [:8] slice in _needs_clarification)
_wifi_network_list = st.lists(
    _wifi_network,
    min_size=1,
    max_size=8,
    unique_by=lambda n: n.ssid,
)


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _make_bridge():
    """Create a Bridge instance with MCP fully mocked."""
    with patch("cios.core.mcp.context") as mock_ctx:
        mock_ctx.start = MagicMock()
        mock_ctx.stop = MagicMock()
        mock_ctx.boot_times = {}
        mock_ctx.notify_activity = MagicMock()
        mock_ctx.force_update_wifi = MagicMock()
        mock_ctx.force_update_audio = MagicMock()
        mock_ctx.force_update = MagicMock()
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
        bridge = CIOSBridge()
    return bridge


# ═══════════════════════════════════════════════════════════════════════════
#  PROPERTY TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestGuidedFlowNetworkOptions:
    """Property 7: Guided flow presents correct options for network connection.

    Feature: produto-percebido, Property 7: Guided flow presents correct options for network connection
    """

    @given(networks=_wifi_network_list)
    @settings(max_examples=20, deadline=None)
    def test_guided_flow_presents_all_ssids_as_options(self, networks: list[WifiNetwork]):
        """For any non-empty list of WiFi networks, when a network connect
        intent is issued without an SSID and no known networks match, the
        Bridge should return a response containing all available SSIDs as
        selectable options.

        **Validates: Requirements 5.1, 5.2**
        """
        bridge = _make_bridge()
        try:
            with (
                patch("cios.skills.network.list_networks", return_value=networks),
                patch("cios.core.mcp.context") as mock_mcp,
            ):
                # Not connected, no known networks
                mock_mcp.wifi.connected = False
                mock_mcp.known_networks = []

                result = bridge.execute_command("conectar wifi")

            # The response should be successful (it's a clarification, not an error)
            assert result["status"] == "success", (
                f"Expected success status, got '{result['status']}'"
            )

            # All SSIDs should appear in the response text
            response_text = result["result"]
            for net in networks:
                assert net.ssid in response_text, (
                    f"SSID '{net.ssid}' not found in response: {response_text}"
                )

            # A pending question should be set with flow_steps
            pq = bridge._pending_question
            assert pq is not None, "Expected a pending question to be set"
            assert pq.flow_steps is not None, "Expected flow_steps to be set"

            # The options in the pending question should contain all SSIDs
            expected_ssids = [n.ssid for n in networks]
            assert pq.options == expected_ssids, (
                f"Expected options {expected_ssids}, got {pq.options}"
            )
        finally:
            bridge.close()

    @given(networks=_wifi_network_list)
    @settings(max_examples=20, deadline=2000)
    def test_unknown_network_triggers_password_prompt(self, networks: list[WifiNetwork]):
        """For any non-empty list of WiFi networks, selecting an unknown
        network (not in known_networks) should trigger a password prompt
        as the next step in the guided flow.

        **Validates: Requirements 5.1, 5.2**
        """
        bridge = _make_bridge()
        try:
            # Step 1: Trigger the guided flow
            with (
                patch("cios.skills.network.list_networks", return_value=networks),
                patch("cios.core.mcp.context") as mock_mcp,
            ):
                mock_mcp.wifi.connected = False
                mock_mcp.known_networks = []

                bridge.execute_command("conectar wifi")

            # Verify guided flow was set up
            assert bridge._pending_question is not None, "Expected pending question"
            assert bridge._pending_question.flow_steps is not None, "Expected flow_steps"

            # The flow_steps should have a password step for unknown networks
            flow_steps = bridge._pending_question.flow_steps
            password_steps = [s for s in flow_steps if s.param_key == "password"]
            assert len(password_steps) >= 1, (
                f"Expected at least one password step in flow_steps, "
                f"got steps: {[(s.param_key, s.question_type) for s in flow_steps]}"
            )

            # The password step should be of type "password"
            pw_step = password_steps[0]
            assert pw_step.question_type == "password", (
                f"Expected password step type 'password', got '{pw_step.question_type}'"
            )

            # Step 2: Answer with the first SSID (unknown network → should ask password)
            first_ssid = networks[0].ssid
            with patch("cios.core.mcp.context") as mock_mcp:
                mock_mcp.known_networks = []  # Not a known network
                mock_mcp.notify_activity = MagicMock()

                result2 = bridge.execute_command(first_ssid)

            # Should ask for password (the response should mention "Senha" or "password")
            assert bridge._pending_question is not None, (
                f"Expected pending question for password after selecting unknown "
                f"network '{first_ssid}', but got none. Result: {result2}"
            )

            # The collected params should have the SSID
            if bridge._pending_question.flow_collected:
                assert bridge._pending_question.flow_collected.get("ssid") == first_ssid, (
                    f"Expected collected ssid='{first_ssid}', "
                    f"got {bridge._pending_question.flow_collected}"
                )
        finally:
            bridge.close()


# ═══════════════════════════════════════════════════════════════════════════
#  STRATEGIES FOR PROPERTY 8
# ═══════════════════════════════════════════════════════════════════════════

# Generate answer strings: non-empty printable text that a user might type
# as an answer to a clarification question.
_answer_text = (
    st.text(
        alphabet=st.sampled_from(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- "
        ),
        min_size=1,
        max_size=30,
    )
    .map(str.strip)
    .filter(lambda s: len(s) > 0)
)

# Generate port numbers as strings (what a user would type when asked "Qual porta?")
_port_answer = st.integers(min_value=10, max_value=65535).map(str)

# Intent scenarios that trigger clarification (missing required params)
# Each tuple: (intent, expected_question_type, param_key_filled, answer_strategy)
_CLARIFICATION_SCENARIOS = [
    (
        "app_launch_no_app",
        lambda: Intent(
            type=IntentType.APP_LAUNCH,
            confidence=0.9,
            params={},
            raw_input="abrir",
        ),
        "app",
        "app",
    ),
    (
        "process_control_kill_no_port",
        lambda: Intent(
            type=IntentType.PROCESS_CONTROL,
            confidence=0.9,
            params={"action": "kill", "port": None},
            raw_input="matar processo",
        ),
        "port",
        "port",
    ),
    (
        "file_organize_no_target",
        lambda: Intent(
            type=IntentType.FILE_ORGANIZE,
            confidence=0.9,
            params={},
            raw_input="organizar",
        ),
        "target",
        "target",
    ),
]

# Strategy that picks one of the clarification scenarios
_scenario_index = st.sampled_from(range(len(_CLARIFICATION_SCENARIOS)))


# ═══════════════════════════════════════════════════════════════════════════
#  PROPERTY 8 TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestConversationContextPendingQuestion:
    """Property 8: Conversation context preserves pending question state.

    Feature: produto-percebido, Property 8: Conversation context preserves pending question state

    For any intent that triggers a clarification question (missing app name,
    missing port, missing target), the Bridge should set a _pending_question,
    and the next user input should be processed as an answer to that question
    (filling the correct intent param) rather than as a new independent intent.

    **Validates: Requirements 5.4**
    """

    @given(answer=_answer_text)
    @settings(max_examples=20, deadline=None)
    def test_app_launch_missing_app_sets_pending_and_fills_param(self, answer: str):
        """APP_LAUNCH without app → sets _pending_question with question_type='app',
        next input fills the 'app' param.

        **Validates: Requirements 5.4**
        """
        bridge = _make_bridge()
        try:
            intent = Intent(
                type=IntentType.APP_LAUNCH,
                confidence=0.9,
                params={},
                raw_input="abrir",
            )

            # Mock parse_intent to return our intent missing the app param
            with (
                patch("cios.core.bridge.parse_intent", return_value=intent),
                patch("cios.core.bridge.classify_intent", return_value=None),
            ):
                result = bridge.execute_command("abrir")

            # 1. _pending_question should be set
            assert bridge._pending_question is not None, (
                "Expected _pending_question to be set for APP_LAUNCH without app"
            )
            assert bridge._pending_question.question_type == "app", (
                f"Expected question_type='app', got '{bridge._pending_question.question_type}'"
            )

            # 2. Next input should be processed as an answer, not a new intent
            # Mock the planner execution to capture what intent gets executed
            executed_intents = []

            def mock_execute(intent_arg):
                executed_intents.append(intent_arg)
                from cios.core.planner import PlanResult

                return PlanResult(
                    plan_steps=["Abrindo app"],
                    results=[],
                    summary=f"App {intent_arg.params.get('app', '')} aberto",
                    outcome="success",
                )

            with (
                patch.object(bridge._planner, "execute", side_effect=mock_execute),
                patch("cios.core.mcp.context") as mock_ctx,
            ):
                mock_ctx.notify_activity = MagicMock()
                mock_ctx.snapshot.return_value = MagicMock()
                result2 = bridge.execute_command(answer)

            # 3. The answer should have filled the 'app' param
            assert len(executed_intents) == 1, (
                f"Expected exactly 1 intent execution, got {len(executed_intents)}"
            )
            assert executed_intents[0].params.get("app") == answer, (
                f"Expected app='{answer}', got '{executed_intents[0].params.get('app')}'"
            )

            # 4. _pending_question should be cleared after answering
            assert bridge._pending_question is None, (
                "Expected _pending_question to be None after answer was processed"
            )
        finally:
            bridge.close()

    @given(port_str=_port_answer)
    @settings(max_examples=20, deadline=None)
    def test_process_control_missing_port_sets_pending_and_fills_param(self, port_str: str):
        """PROCESS_CONTROL kill without port → sets _pending_question with
        question_type='port', next input fills the 'port' param.

        **Validates: Requirements 5.4**
        """
        bridge = _make_bridge()
        try:
            intent = Intent(
                type=IntentType.PROCESS_CONTROL,
                confidence=0.9,
                params={"action": "kill", "port": None},
                raw_input="matar processo",
            )

            with (
                patch("cios.core.bridge.parse_intent", return_value=intent),
                patch("cios.core.bridge.classify_intent", return_value=None),
            ):
                result = bridge.execute_command("matar processo")

            # 1. _pending_question should be set
            assert bridge._pending_question is not None, (
                "Expected _pending_question to be set for PROCESS_CONTROL without port"
            )
            assert bridge._pending_question.question_type == "port", (
                f"Expected question_type='port', got '{bridge._pending_question.question_type}'"
            )

            # 2. Next input should be processed as an answer
            executed_intents = []

            def mock_execute(intent_arg):
                executed_intents.append(intent_arg)
                from cios.core.planner import PlanResult

                return PlanResult(
                    plan_steps=["Matando processo"],
                    results=[],
                    summary="Processo encerrado",
                    outcome="success",
                )

            with (
                patch.object(bridge._planner, "execute", side_effect=mock_execute),
                patch("cios.core.mcp.context") as mock_ctx,
            ):
                mock_ctx.notify_activity = MagicMock()
                mock_ctx.snapshot.return_value = MagicMock()
                result2 = bridge.execute_command(port_str)

            # 3. The answer should have filled the 'port' param as an integer
            assert len(executed_intents) == 1, (
                f"Expected exactly 1 intent execution, got {len(executed_intents)}"
            )
            expected_port = int(port_str)
            assert executed_intents[0].params.get("port") == expected_port, (
                f"Expected port={expected_port}, got '{executed_intents[0].params.get('port')}'"
            )

            # 4. _pending_question should be cleared
            assert bridge._pending_question is None, (
                "Expected _pending_question to be None after answer was processed"
            )
        finally:
            bridge.close()

    @given(answer=_answer_text)
    @settings(max_examples=20, deadline=None)
    def test_file_organize_missing_target_sets_pending_and_fills_param(self, answer: str):
        """FILE_ORGANIZE without target → sets _pending_question with
        question_type='target', next input fills the 'target' param.

        **Validates: Requirements 5.4**
        """
        bridge = _make_bridge()
        try:
            intent = Intent(
                type=IntentType.FILE_ORGANIZE,
                confidence=0.9,
                params={},
                raw_input="organizar",
            )

            with (
                patch("cios.core.bridge.parse_intent", return_value=intent),
                patch("cios.core.bridge.classify_intent", return_value=None),
            ):
                result = bridge.execute_command("organizar")

            # 1. _pending_question should be set
            assert bridge._pending_question is not None, (
                "Expected _pending_question to be set for FILE_ORGANIZE without target"
            )
            assert bridge._pending_question.question_type == "target", (
                f"Expected question_type='target', got '{bridge._pending_question.question_type}'"
            )

            # 2. Next input should be processed as an answer, not a new intent
            # For FILE_ORGANIZE, after filling target, it needs confirmation.
            # The _handle_answer path calls _execute_intent which goes through
            # the planner. But first, _needs_confirmation may fire. Let's mock
            # the planner to capture the intent.
            executed_intents = []

            def mock_execute(intent_arg):
                executed_intents.append(intent_arg)
                from cios.core.planner import PlanResult

                return PlanResult(
                    plan_steps=["Organizando arquivos"],
                    results=[],
                    summary="Arquivos organizados",
                    outcome="success",
                )

            with (
                patch.object(bridge._planner, "execute", side_effect=mock_execute),
                patch("cios.core.mcp.context") as mock_ctx,
            ):
                mock_ctx.notify_activity = MagicMock()
                mock_ctx.snapshot.return_value = MagicMock()
                result2 = bridge.execute_command(answer)

            # 3. The answer should have filled the 'target' param
            assert len(executed_intents) == 1, (
                f"Expected exactly 1 intent execution, got {len(executed_intents)}"
            )
            assert executed_intents[0].params.get("target") == answer, (
                f"Expected target='{answer}', got '{executed_intents[0].params.get('target')}'"
            )

            # 4. _pending_question should be cleared
            assert bridge._pending_question is None, (
                "Expected _pending_question to be None after answer was processed"
            )
        finally:
            bridge.close()

    @given(scenario_idx=_scenario_index, answer=_answer_text)
    @settings(max_examples=20, deadline=None)
    def test_pending_question_prevents_new_intent_parsing(self, scenario_idx: int, answer: str):
        """When _pending_question is set, the next input is processed as an
        answer (via _handle_answer) rather than being parsed as a new intent.

        This verifies that parse_intent is NOT called for the answer input.

        **Validates: Requirements 5.4**
        """
        scenario_name, intent_factory, question_type, param_key = _CLARIFICATION_SCENARIOS[
            scenario_idx
        ]
        bridge = _make_bridge()
        try:
            intent = intent_factory()

            # Step 1: Trigger clarification
            with (
                patch("cios.core.bridge.parse_intent", return_value=intent),
                patch("cios.core.bridge.classify_intent", return_value=None),
            ):
                bridge.execute_command(intent.raw_input)

            assert bridge._pending_question is not None, (
                f"Scenario '{scenario_name}': expected _pending_question to be set"
            )

            # Step 2: Send the answer — parse_intent should NOT be called
            parse_intent_calls = []

            def tracking_parse_intent(text):
                parse_intent_calls.append(text)
                return Intent(type=IntentType.UNKNOWN, confidence=0.0, raw_input=text)

            # For port scenario, use a numeric answer
            actual_answer = answer
            if param_key == "port":
                actual_answer = "3000"

            def mock_execute(intent_arg):
                from cios.core.planner import PlanResult

                return PlanResult(
                    plan_steps=["Step"],
                    results=[],
                    summary="Done",
                    outcome="success",
                )

            with (
                patch("cios.core.bridge.parse_intent", side_effect=tracking_parse_intent),
                patch.object(bridge._planner, "execute", side_effect=mock_execute),
                patch("cios.core.mcp.context") as mock_ctx,
            ):
                mock_ctx.notify_activity = MagicMock()
                mock_ctx.snapshot.return_value = MagicMock()
                bridge.execute_command(actual_answer)

            # parse_intent should NOT have been called — the answer goes through
            # _handle_answer, not the normal intent parsing path
            assert len(parse_intent_calls) == 0, (
                f"Scenario '{scenario_name}': parse_intent was called {len(parse_intent_calls)} "
                f"time(s) for the answer input, but it should have been handled by _handle_answer. "
                f"Calls: {parse_intent_calls}"
            )
        finally:
            bridge.close()
