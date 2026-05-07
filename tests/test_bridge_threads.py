"""Integration tests for Bridge + ThreadManager flow.

Tests the full integration between CIOSBridge and ThreadManager:
- Command submission → route_input → classify → record_turn
- Pending question flow: clarification asked → user answers → routed correctly
- Thread transition: unrelated input → old thread closed, new thread created

Validates: Requirements 1.1, 2.2, 2.3, 4.1
"""

import time
from unittest.mock import patch, MagicMock

import pytest

from cios.core.bridge import CIOSBridge


@pytest.fixture
def bridge():
    """Provide a Bridge instance with MCP and heavy deps mocked."""
    with patch("cios.core.mcp.context") as mock_ctx:
        mock_ctx.start = MagicMock()
        mock_ctx.stop = MagicMock()
        mock_ctx.boot_times = {}
        mock_ctx.notify_activity = MagicMock()
        mock_ctx.wifi = MagicMock(connected=False)
        mock_ctx.known_networks = []
        # Mock snapshot for get_system_status
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


class TestFullCommandFlow:
    """Test full flow: submit command → route_input → classify → record_turn.

    Validates: Requirements 1.1, 4.1
    """

    def test_command_creates_thread_and_records_turn(self, bridge):
        """A command creates a new thread and records the turn."""
        # Initially no active thread
        assert bridge._thread_manager._active_thread is None

        # Execute a simple command
        result = bridge.execute_command("run echo hello", confirmed=True)
        assert result["status"] == "success"

        # Thread should now exist with a recorded turn
        thread = bridge._thread_manager._active_thread
        assert thread is not None
        assert thread.status == "active"
        assert len(thread.turns) == 1
        assert thread.turns[0].user_input == "run echo hello"
        assert thread.turns[0].intent_type == "command_exec"

    def test_consecutive_commands_same_thread_within_temporal_window(self, bridge):
        """Commands within 90s continue the same thread."""
        # First command
        bridge.execute_command("run echo first", confirmed=True)
        thread_id_1 = bridge._thread_manager._active_thread.id

        # Second command immediately (within temporal window)
        # Same intent category (command_exec) + temporal proximity → CONTINUE
        bridge.execute_command("run echo second", confirmed=True)
        thread_id_2 = bridge._thread_manager._active_thread.id

        # Should be the same thread (same intent + temporal proximity = 2 medium signals)
        assert thread_id_1 == thread_id_2
        assert len(bridge._thread_manager._active_thread.turns) == 2

    def test_thread_records_dominant_intent(self, bridge):
        """Thread tracks the dominant intent across turns."""
        bridge.execute_command("run echo hello", confirmed=True)
        bridge.execute_command("run ls", confirmed=True)

        thread = bridge._thread_manager._active_thread
        assert thread.dominant_intent == "command_exec"

    def test_route_input_called_on_each_command(self, bridge):
        """Every command goes through route_input for proper routing."""
        with patch.object(
            bridge._thread_manager, "route_input", wraps=bridge._thread_manager.route_input
        ) as mock_route:
            bridge.execute_command("run echo test", confirmed=True)
            mock_route.assert_called_once_with("run echo test")


class TestPendingQuestionFlow:
    """Test pending question flow: clarification → answer → routed correctly.

    Validates: Requirements 1.1, 2.2
    """

    def _trigger_app_clarification(self, bridge):
        """Helper: mock parse_intent to return APP_LAUNCH without app param, triggering clarification."""
        from cios.core.intent_parser import Intent, IntentType
        mock_intent = Intent(type=IntentType.APP_LAUNCH, params={}, confidence=0.9)
        with patch("cios.core.bridge.parse_intent", return_value=mock_intent):
            with patch("cios.core.bridge.classify_intent", return_value=None):
                return bridge.execute_command("abrir")

    def _trigger_file_organize_clarification(self, bridge):
        """Helper: mock parse_intent to return FILE_ORGANIZE without target."""
        from cios.core.intent_parser import Intent, IntentType
        mock_intent = Intent(type=IntentType.FILE_ORGANIZE, params={}, confidence=0.9)
        with patch("cios.core.bridge.parse_intent", return_value=mock_intent):
            with patch("cios.core.bridge.classify_intent", return_value=None):
                return bridge.execute_command("organizar")

    def test_app_launch_clarification_sets_pending_question(self, bridge):
        """APP_LAUNCH without app name triggers clarification and sets pending question."""
        result = self._trigger_app_clarification(bridge)

        # Should ask which app to open
        assert "app" in result["result"].lower() or "qual" in result["result"].lower()

        # Pending question should be set on the active thread
        thread = bridge._thread_manager._active_thread
        assert thread is not None
        assert thread.pending_question is not None
        assert thread.pending_question.question_type == "app"

    def test_answer_to_pending_question_routed_correctly(self, bridge):
        """After clarification, the next input is routed as an answer."""
        # Trigger clarification
        self._trigger_app_clarification(bridge)

        # Verify pending question exists
        assert bridge._thread_manager._active_thread.pending_question is not None

        # Answer the question — should be routed as answer_pending
        with patch.object(bridge, "_handle_answer", wraps=bridge._handle_answer) as mock_handle:
            result = bridge.execute_command("firefox")
            mock_handle.assert_called_once()

    def test_pending_question_cleared_after_answer(self, bridge):
        """Pending question is cleared after the user answers."""
        # Trigger clarification for app launch
        self._trigger_app_clarification(bridge)
        assert bridge._thread_manager._active_thread.pending_question is not None

        # Answer it
        with patch("cios.core.bridge.CIOSBridge._execute_intent") as mock_exec:
            mock_exec.return_value = {
                "steps": ["Launching firefox"],
                "result": "Firefox aberto",
                "status": "success",
                "confirm": None,
                "voice_mode": "full",
            }
            bridge.execute_command("firefox")

        # Pending question should be cleared
        assert bridge._thread_manager._active_thread.pending_question is None

    def test_file_organize_clarification_flow(self, bridge):
        """File organize without target triggers clarification, answer fills param."""
        # Trigger clarification
        self._trigger_file_organize_clarification(bridge)

        # Should ask which folder
        assert bridge._thread_manager._active_thread.pending_question is not None
        assert bridge._thread_manager._active_thread.pending_question.question_type == "target"

        # Answer with target — should route as answer and fill the param
        with patch("cios.core.bridge.CIOSBridge._execute_intent") as mock_exec:
            mock_exec.return_value = {
                "steps": ["Organizing downloads"],
                "result": "Organizado",
                "status": "success",
                "confirm": None,
                "voice_mode": "full",
            }
            bridge.execute_command("downloads")
            # Verify the intent was called with the target filled in
            called_intent = mock_exec.call_args[0][0]
            assert called_intent.params.get("target") == "downloads"

    def test_pending_question_same_thread(self, bridge):
        """Pending question and answer stay in the same thread."""
        self._trigger_app_clarification(bridge)
        thread_id = bridge._thread_manager._active_thread.id

        with patch("cios.core.bridge.CIOSBridge._execute_intent") as mock_exec:
            mock_exec.return_value = {
                "steps": [],
                "result": "Done",
                "status": "success",
                "confirm": None,
                "voice_mode": "full",
            }
            bridge.execute_command("firefox")

        # Should still be the same thread
        assert bridge._thread_manager._active_thread.id == thread_id


class TestThreadTransition:
    """Test thread transition: unrelated input → old thread closed, new thread created.

    Validates: Requirements 2.3, 4.1
    """

    def test_unrelated_input_after_timeout_creates_new_thread(self, bridge):
        """After temporal window expires, unrelated input creates a new thread."""
        # Execute first command
        bridge.execute_command("run echo hello", confirmed=True)
        first_thread_id = bridge._thread_manager._active_thread.id

        # Simulate time passing beyond the 90s classification window
        # Manipulate the last turn's timestamp and the activity timer
        thread = bridge._thread_manager._active_thread
        thread.turns[-1].timestamp = time.time() - 100  # 100s ago
        bridge._thread_manager._last_activity_mono = time.monotonic() - 100

        # Execute an unrelated command (different intent category)
        # "abrir firefox" is app_launch, different from command_exec
        # But we need to avoid clarification, so use a full command
        with patch("cios.core.bridge.CIOSBridge._execute_intent") as mock_exec:
            mock_exec.return_value = {
                "steps": ["Opening firefox"],
                "result": "Firefox aberto",
                "status": "success",
                "confirm": None,
                "voice_mode": "full",
            }
            bridge.execute_command("abrir firefox")

        # Should be a different thread
        second_thread_id = bridge._thread_manager._active_thread.id
        assert first_thread_id != second_thread_id

    def test_old_thread_closed_on_transition(self, bridge):
        """When a new thread is created, the old one is closed and persisted."""
        # Execute first command
        bridge.execute_command("run echo hello", confirmed=True)
        first_thread_id = bridge._thread_manager._active_thread.id

        # Simulate time passing beyond temporal window
        thread = bridge._thread_manager._active_thread
        thread.turns[-1].timestamp = time.time() - 100
        bridge._thread_manager._last_activity_mono = time.monotonic() - 100

        # Spy on the store's save_thread to verify persistence
        with patch.object(
            bridge._thread_manager._store, "save_thread", wraps=bridge._thread_manager._store.save_thread
        ) as mock_save:
            with patch("cios.core.bridge.CIOSBridge._execute_intent") as mock_exec:
                mock_exec.return_value = {
                    "steps": [],
                    "result": "Done",
                    "status": "success",
                    "confirm": None,
                    "voice_mode": "full",
                }
                bridge.execute_command("abrir firefox")

            # The old thread should have been saved
            mock_save.assert_called_once()
            saved_thread = mock_save.call_args[0][0]
            assert saved_thread.id == first_thread_id
            assert saved_thread.status == "completed"
            assert saved_thread.closed_at is not None

    def test_pronoun_continues_thread(self, bridge):
        """Input with a pronoun reference continues the active thread."""
        # First command
        bridge.execute_command("run echo hello", confirmed=True)
        thread_id = bridge._thread_manager._active_thread.id

        # Simulate some time passing (but use pronoun to force continuation)
        thread = bridge._thread_manager._active_thread
        thread.turns[-1].timestamp = time.time() - 100
        bridge._thread_manager._last_activity_mono = time.monotonic() - 100

        # Use a pronoun — should continue the thread regardless of time
        bridge.execute_command("run that again", confirmed=True)
        assert bridge._thread_manager._active_thread.id == thread_id

    def test_continuation_phrase_continues_thread(self, bridge):
        """Explicit continuation phrases keep the same thread."""
        bridge.execute_command("run echo hello", confirmed=True)
        thread_id = bridge._thread_manager._active_thread.id

        # Simulate time passing
        thread = bridge._thread_manager._active_thread
        thread.turns[-1].timestamp = time.time() - 100
        bridge._thread_manager._last_activity_mono = time.monotonic() - 100

        # Use continuation phrase
        bridge.execute_command("and also run echo world", confirmed=True)
        assert bridge._thread_manager._active_thread.id == thread_id

    def test_inactivity_timeout_closes_thread(self, bridge):
        """Thread is auto-closed after 180s of inactivity."""
        bridge.execute_command("run echo hello", confirmed=True)
        first_thread_id = bridge._thread_manager._active_thread.id

        # Simulate 181s of inactivity (beyond THREAD_INACTIVITY_TIMEOUT=180)
        bridge._thread_manager._last_activity_mono = time.monotonic() - 181

        # Next command should trigger inactivity check and create new thread
        bridge.execute_command("run echo world", confirmed=True)

        # Should be a new thread
        assert bridge._thread_manager._active_thread.id != first_thread_id


class TestThreadStateIntegrity:
    """Test thread-safe state management through the bridge.

    Validates: Requirements 4.1
    """

    def test_thread_lock_protects_state(self, bridge):
        """Thread manager uses a lock for state mutations."""
        # Verify the lock exists
        import threading
        assert hasattr(bridge._thread_manager, "_lock")
        assert isinstance(bridge._thread_manager._lock, type(threading.Lock()))

        # Execute a command — verify state is consistent after
        bridge.execute_command("run echo test", confirmed=True)
        thread = bridge._thread_manager._active_thread
        assert thread is not None
        assert len(thread.turns) == 1
        # The lock ensures atomic state — no partial updates visible

    def test_record_turn_updates_thread_atomically(self, bridge):
        """record_turn adds turn to active thread under lock."""
        bridge.execute_command("run echo hello", confirmed=True)

        thread = bridge._thread_manager._active_thread
        assert len(thread.turns) == 1

        turn = thread.turns[0]
        assert turn.user_input == "run echo hello"
        assert turn.intent_type == "command_exec"
        assert turn.timestamp > 0

    def test_multiple_commands_maintain_order(self, bridge):
        """Multiple commands maintain correct turn ordering."""
        bridge.execute_command("run echo first", confirmed=True)
        bridge.execute_command("run echo second", confirmed=True)
        bridge.execute_command("run echo third", confirmed=True)

        thread = bridge._thread_manager._active_thread
        assert len(thread.turns) == 3
        assert thread.turns[0].user_input == "run echo first"
        assert thread.turns[1].user_input == "run echo second"
        assert thread.turns[2].user_input == "run echo third"

        # Timestamps should be non-decreasing
        for i in range(1, len(thread.turns)):
            assert thread.turns[i].timestamp >= thread.turns[i - 1].timestamp
