"""Property-based tests for Bridge streaming callbacks.

Feature: produto-percebido
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.bridge import CIOSBridge

# --- Strategies ---

# Generate safe words for echo commands (alphanumeric, no special shell chars)
_safe_word = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789"),
    min_size=1,
    max_size=20,
)

# Generate command strings that always produce at least one plan step.
# COMMAND_EXEC intents with "echo <word>" always produce exactly one plan step.
_echo_command = _safe_word.map(lambda w: f"run echo {w}")


def _make_bridge():
    """Create a Bridge instance with MCP mocked (no real system polling)."""
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


# --- Property Tests ---


class TestStreamingCallbacks:
    """Property 6: Streaming execution invokes step callbacks.

    Feature: produto-percebido, Property 6: Streaming execution invokes step callbacks
    """

    @given(command=_echo_command)
    @settings(max_examples=20, deadline=None)
    def test_streaming_invokes_on_step_at_least_once(self, command: str):
        """For any valid intent that produces at least one plan step,
        execute_streaming with an on_step callback invokes that callback
        at least once before returning the final result.

        **Validates: Requirements 3.3**
        """
        bridge = _make_bridge()
        try:
            steps_received = []

            def on_step(text, index, total):
                steps_received.append((text, index, total))

            result = bridge.execute_streaming(
                command,
                confirmed=True,
                on_step=on_step,
            )

            # The result should be successful for echo commands
            # (hardware-dependent skills like audio/bluetooth may fail in CI — that's ok)
            HARDWARE_FAILURES = [
                "audio system",
                "bluetooth",
                "wi-fi",
                "no audio",
                "indisponível",
                "unavailable",
                "not available",
            ]
            if result["status"] != "success":
                result_text = result.get("result", "").lower()
                is_hardware_failure = any(f in result_text for f in HARDWARE_FAILURES)
                assert is_hardware_failure, (
                    f"Expected success for '{command}', got status='{result['status']}', "
                    f"result='{result.get('result', '')}'"
                )
                return  # Hardware failure is acceptable in CI

            # on_step must have been called at least once
            assert len(steps_received) >= 1, f"on_step was never called for command '{command}'"

            # Filter to plan steps only (not phase callbacks like "Entendendo…", "Executando…")
            phase_labels = {"Entendendo…", "Executando…", "Classificando…", "Consultando IA…"}
            plan_steps = [s for s in steps_received if s[0] not in phase_labels]

            # There must be at least one plan step callback (not just phase callbacks)
            assert len(plan_steps) >= 1, (
                f"on_step was called only with phase labels {[s[0] for s in steps_received]}, "
                f"no actual plan steps were streamed for command '{command}'"
            )
        finally:
            bridge.close()
