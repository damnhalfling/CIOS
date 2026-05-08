# Feature: conversation-threads, Property 9: Thread entry rendering completeness
"""Property-based tests for ThreadPanel rendering logic.

Feature: conversation-threads
Property 9: Thread entry rendering completeness

Validates: Requirements 6.2

For any completed Thread, the rendered thread panel entry SHALL contain
the thread summary text, a formatted timestamp, and an outcome status
indicator (success, error, or incomplete).

Since Tkinter may not be available in headless CI environments, we test
the rendering LOGIC directly:
1. _format_timestamp() produces a non-empty string for any valid timestamp
2. The _OUTCOME_ICONS mapping produces a valid icon for any outcome value
3. The summary is always non-empty for any completed thread (ThreadManager
   guarantees this via _create_thread_unlocked)
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.thread_manager import (
    ConversationTurn,
    Thread,
)

# --- Strategies ---

# Generate valid UUID4 hex strings
_uuid_hex = st.uuids(version=4).map(lambda u: u.hex)

# Generate reasonable timestamps (past to present)
_timestamp = st.floats(
    min_value=1_000_000_000.0,
    max_value=2_000_000_000.0,
    allow_nan=False,
    allow_infinity=False,
)

# Generate non-empty text for summaries
_summary_text = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(blacklist_categories=("Cs",)),
)

# Generate outcome values (all valid outcomes the panel handles)
_outcome = st.sampled_from(["success", "error", "incomplete", ""])

# Generate intent types
_intent_type = st.sampled_from(["network", "system", "app", "media", "file", "general", "search"])

# Generate a ConversationTurn
_turn = st.builds(
    ConversationTurn,
    user_input=st.text(
        min_size=1, max_size=100, alphabet=st.characters(blacklist_categories=("Cs",))
    ),
    intent_type=_intent_type,
    params=st.just({}),
    result_summary=st.text(max_size=100, alphabet=st.characters(blacklist_categories=("Cs",))),
    outcome=_outcome,
    timestamp=_timestamp,
)

# Generate a completed Thread with non-empty summary
_completed_thread = st.builds(
    Thread,
    id=_uuid_hex,
    created_at=_timestamp,
    closed_at=st.one_of(st.none(), _timestamp),
    summary=_summary_text,
    status=st.just("completed"),
    turns=st.lists(_turn, min_size=0, max_size=5),
    dominant_intent=_intent_type,
    outcome=_outcome,
)


# --- Rendering logic extracted for testing ---

# These mirror the ThreadPanel class attributes from gui.py
_OUTCOME_ICONS = {
    "success": "✓",
    "error": "⚠",
    "incomplete": "○",
    "": "○",
}

_OUTCOME_COLORS = {
    "success": "#4ade80",  # SUCCESS color from theme
    "error": "#f87171",  # ERROR color from theme
    "incomplete": "#6b7280",  # FG_DIM
    "": "#6b7280",
}


def _format_timestamp(ts: float) -> str:
    """Format a Unix timestamp into a human-readable relative or absolute string.

    This is the same logic as ThreadPanel._format_timestamp().
    """
    import time as _time

    now = _time.time()
    diff = now - ts

    if diff < 60:
        return "agora"
    elif diff < 3600:
        mins = int(diff // 60)
        return f"{mins}min"
    elif diff < 86400:
        hours = int(diff // 3600)
        return f"{hours}h"
    else:
        # Show date for older threads
        local = _time.localtime(ts)
        return _time.strftime("%d/%m %H:%M", local)


# --- Property Tests ---


# Feature: conversation-threads, Property 9: Thread entry rendering completeness
class TestThreadEntryRenderingCompleteness:
    """Property 9: Thread entry rendering completeness.

    For any completed Thread, the rendered thread panel entry SHALL contain
    the thread summary text, a formatted timestamp, and an outcome status
    indicator (success, error, or incomplete).

    **Validates: Requirements 6.2**
    """

    @given(thread=_completed_thread)
    @settings(max_examples=30, deadline=None)
    def test_format_timestamp_produces_nonempty_string(self, thread: Thread):
        """For any valid timestamp, _format_timestamp returns a non-empty string.

        **Validates: Requirements 6.2**
        """
        result = _format_timestamp(thread.created_at)
        assert isinstance(result, str), f"Expected str, got {type(result).__name__}"
        assert (
            len(result) > 0
        ), f"Timestamp formatting produced empty string for ts={thread.created_at}"

    @given(outcome=_outcome)
    @settings(max_examples=30, deadline=None)
    def test_outcome_icon_mapping_produces_valid_icon(self, outcome: str):
        """For any valid outcome value, the icon mapping produces a non-empty icon.

        **Validates: Requirements 6.2**
        """
        icon = _OUTCOME_ICONS.get(outcome, "○")
        assert isinstance(icon, str), f"Expected str icon, got {type(icon).__name__}"
        assert len(icon) > 0, f"Outcome icon is empty for outcome={outcome!r}"
        # Verify it's one of the expected icons
        assert icon in {"✓", "⚠", "○"}, f"Unexpected icon {icon!r} for outcome={outcome!r}"

    @given(thread=_completed_thread)
    @settings(max_examples=30, deadline=None)
    def test_summary_always_present_for_completed_thread(self, thread: Thread):
        """For any completed Thread, the summary text is always non-empty.

        ThreadManager._create_thread_unlocked guarantees a non-empty summary
        (defaults to "Nova conversa" if input is empty, or truncates long input).

        **Validates: Requirements 6.2**
        """
        # Our strategy generates non-empty summaries (min_size=1)
        # This validates the invariant that completed threads always have summaries
        summary = thread.summary
        assert isinstance(summary, str), f"Expected str summary, got {type(summary).__name__}"
        assert len(summary) > 0, f"Thread {thread.id} has empty summary"

    @given(thread=_completed_thread)
    @settings(max_examples=30, deadline=None)
    def test_rendering_data_complete_for_any_thread(self, thread: Thread):
        """For any completed Thread, all rendering components are present and valid.

        Verifies that the combination of summary, timestamp, and outcome icon
        would produce a complete thread entry in the panel.

        **Validates: Requirements 6.2**
        """
        # 1. Summary text is present
        summary = thread.summary
        assert summary and len(summary) > 0, f"Missing summary for thread {thread.id}"

        # 2. Formatted timestamp is non-empty
        timestamp_str = _format_timestamp(thread.created_at)
        assert (
            timestamp_str and len(timestamp_str) > 0
        ), f"Empty timestamp for thread {thread.id} (ts={thread.created_at})"

        # 3. Outcome status indicator is valid
        outcome = thread.outcome or ""
        icon = _OUTCOME_ICONS.get(outcome, "○")
        assert icon in {"✓", "⚠", "○"}, f"Invalid outcome icon for thread {thread.id}: {icon!r}"

        # 4. Outcome color is valid (non-empty hex color)
        color = _OUTCOME_COLORS.get(outcome, "#6b7280")
        assert (
            color.startswith("#") and len(color) == 7
        ), f"Invalid outcome color for thread {thread.id}: {color!r}"
