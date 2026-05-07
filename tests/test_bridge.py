"""Tests for the Bridge module (integration)."""

from unittest.mock import patch, MagicMock

import pytest

from cios.core.bridge import CIOSBridge


@pytest.fixture
def bridge():
    """Provide a Bridge instance with MCP mocked (no real system polling)."""
    with patch("cios.core.mcp.context") as mock_ctx:
        mock_ctx.start = MagicMock()
        mock_ctx.stop = MagicMock()
        mock_ctx.boot_times = {}
        # Mock snapshot for get_system_status (returns real-looking data)
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
        with patch("cios.core.bridge.resolve_unknown_intent", return_value=None):
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
        with patch("cios.core.handlers.system.execute_session_action") as mock_exec:
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
        with patch("cios.core.bridge.parse_intent", side_effect=RuntimeError("boom")):
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


class TestBridgeStreamingProgress:
    """Streaming progress: on_step callbacks and topbar transitions."""

    def test_execute_streaming_calls_on_step_for_plan_steps(self, bridge):
        """execute_streaming calls on_step for each humanized plan step."""
        steps_received = []

        def on_step(text, index, total):
            steps_received.append((text, index, total))

        result = bridge.execute_streaming(
            "run echo hello", confirmed=True, on_step=on_step,
        )
        assert result["status"] == "success"
        # Should have received at least the "Entendendo…" and "Executando…"
        # phase callbacks plus at least one plan step
        texts = [s[0] for s in steps_received]
        assert "Entendendo…" in texts
        assert "Executando…" in texts
        # Plan steps come after "Executando…"
        plan_steps = [s for s in steps_received if s[0] not in ("Entendendo…", "Executando…", "Classificando…", "Consultando IA…")]
        assert len(plan_steps) >= 1, "on_step should be called for at least one plan step"

    def test_execute_streaming_step_indices_are_1_based(self, bridge):
        """Plan step indices start at 1 and go up to total."""
        steps_received = []

        def on_step(text, index, total):
            steps_received.append((text, index, total))

        bridge.execute_streaming(
            "run echo hello", confirmed=True, on_step=on_step,
        )
        # Filter to plan steps only (not phase callbacks)
        plan_steps = [s for s in steps_received if s[0] not in ("Entendendo…", "Executando…", "Classificando…", "Consultando IA…")]
        if plan_steps:
            # First plan step index should be 1
            assert plan_steps[0][1] == 1
            # Total should be consistent
            total = plan_steps[0][2]
            assert all(s[2] == total for s in plan_steps)

    def test_streaming_topbar_transitions(self, bridge):
        """Topbar signals transition: Entendendo… → Executando… → idle."""
        topbar_calls = []

        with patch("cios.ui.topbar.signal_topbar_processing") as mock_proc, \
             patch("cios.ui.topbar.signal_topbar_idle") as mock_idle:
            mock_proc.side_effect = lambda msg: topbar_calls.append(("processing", msg))
            mock_idle.side_effect = lambda: topbar_calls.append(("idle",))

            bridge.execute_streaming(
                "run echo hello", confirmed=True, on_step=lambda *a: None,
            )

        # Verify the transition sequence
        assert len(topbar_calls) >= 3, f"Expected at least 3 topbar calls, got {topbar_calls}"
        assert topbar_calls[0] == ("processing", "Entendendo…")
        # "Executando…" should appear before idle
        processing_msgs = [c[1] for c in topbar_calls if c[0] == "processing"]
        assert "Entendendo…" in processing_msgs
        assert "Executando…" in processing_msgs
        # Last call should be idle
        assert topbar_calls[-1] == ("idle",)

    def test_streaming_topbar_idle_on_unknown_intent(self, bridge):
        """Topbar returns to idle when intent is unknown."""
        with patch("cios.ui.topbar.signal_topbar_processing"), \
             patch("cios.ui.topbar.signal_topbar_idle") as mock_idle, \
             patch("cios.core.bridge.resolve_unknown_intent", return_value=None), \
             patch("cios.core.bridge.classify_intent", return_value=None):
            bridge.execute_streaming("asdfghjkl", on_step=lambda *a: None)
            mock_idle.assert_called()

    def test_streaming_topbar_idle_on_confirmation(self, bridge):
        """Topbar returns to idle when confirmation is needed."""
        with patch("cios.ui.topbar.signal_topbar_processing"), \
             patch("cios.ui.topbar.signal_topbar_idle") as mock_idle:
            result = bridge.execute_streaming(
                "organize my downloads", on_step=lambda *a: None,
            )
            assert result["confirm"] is not None
            mock_idle.assert_called()

    def test_streaming_topbar_idle_on_clarification(self, bridge):
        """Topbar returns to idle when clarification is needed."""
        with patch("cios.ui.topbar.signal_topbar_processing"), \
             patch("cios.ui.topbar.signal_topbar_idle") as mock_idle:
            # "abrir" without app name triggers clarification
            result = bridge.execute_streaming(
                "abrir", on_step=lambda *a: None,
            )
            # Should have called idle
            mock_idle.assert_called()

    def test_streaming_empty_command(self, bridge):
        """Empty command returns immediately without streaming."""
        steps_received = []
        result = bridge.execute_streaming(
            "", on_step=lambda t, i, n: steps_received.append(t),
        )
        assert result["status"] == "success"
        assert result["steps"] == []
        assert len(steps_received) == 0

    def test_streaming_on_step_none_does_not_crash(self, bridge):
        """execute_streaming works fine when on_step is None."""
        result = bridge.execute_streaming(
            "run echo hello", confirmed=True, on_step=None,
        )
        assert result["status"] == "success"
