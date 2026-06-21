# Feature: conversation-threads, Property 2: Continuation signals produce CONTINUE classification
"""Property-based tests for ThreadClassifier continuation signal detection.

Feature: conversation-threads
"""

import time

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.thread_manager import (
    _ALL_PRONOUNS,
    _CONTINUATION_PHRASES,
    Classification,
    ConversationTurn,
    Thread,
    ThreadClassifier,
)

# --- Strategies ---

# All pronouns as a list for sampling
_pronouns_list = sorted(_ALL_PRONOUNS)

# All continuation phrases as a list for sampling
_continuation_phrases_list = list(_CONTINUATION_PHRASES)

# Base text that does NOT contain any continuation signals
# Use simple alphabetic words that won't accidentally match pronouns or phrases
_safe_words = st.sampled_from(
    [
        "please",
        "now",
        "run",
        "open",
        "close",
        "start",
        "stop",
        "check",
        "show",
        "list",
        "find",
        "help",
        "update",
        "install",
        "configure",
        "connect",
        "disconnect",
        "restart",
        "status",
        "hello",
        "world",
        "test",
        "file",
        "folder",
        "network",
    ]
)

_base_text = st.lists(_safe_words, min_size=1, max_size=5).map(lambda words: " ".join(words))

# Strategy: generate input with a pronoun injected as a whole word
_input_with_pronoun = st.tuples(
    _base_text,
    st.sampled_from(_pronouns_list),
    st.integers(min_value=0, max_value=5),  # insertion position indicator
).map(lambda t: _inject_pronoun(t[0], t[1], t[2]))


def _inject_pronoun(base: str, pronoun: str, position: int) -> str:
    """Inject a pronoun as a whole word into the base text."""
    words = base.split()
    # Clamp position to valid range
    pos = position % (len(words) + 1)
    words.insert(pos, pronoun)
    return " ".join(words)


# Strategy: generate input with a continuation phrase embedded
_input_with_continuation_phrase = st.tuples(
    _base_text,
    st.sampled_from(_continuation_phrases_list),
    st.booleans(),  # whether to prepend or append
).map(lambda t: f"{t[1]} {t[0]}" if t[2] else f"{t[0]} {t[1]}")


# Strategy: generate input with EITHER a pronoun OR a continuation phrase
_input_with_signal = st.one_of(
    _input_with_pronoun,
    _input_with_continuation_phrase,
)

# Generate a recent timestamp (within 90 seconds of now)
_recent_timestamp = st.floats(min_value=0.0, max_value=60.0).map(
    lambda offset: time.time() - offset
)

# Generate an active thread with at least one turn (recent timestamp)
_active_thread_with_turn = _recent_timestamp.map(
    lambda ts: Thread(
        turns=[
            ConversationTurn(
                user_input="previous command",
                intent_type="general",
                timestamp=ts,
            )
        ],
        dominant_intent="general",
    )
)


# --- Property Test ---


class TestContinuationSignalsProduceContinue:
    """Property 2: Continuation signals produce CONTINUE classification.

    For any user input that contains at least one high-weight continuation
    signal (a pronoun reference as a whole word, OR an explicit continuation
    phrase), the ThreadClassifier.classify() SHALL return CONTINUE.

    **Validates: Requirements 2.2, 2.4**
    """

    @given(
        user_input=_input_with_pronoun,
        active_thread=_active_thread_with_turn,
    )
    @settings(max_examples=30, deadline=None)
    def test_pronoun_reference_produces_continue(self, user_input: str, active_thread: Thread):
        """Input containing a pronoun reference (whole word) produces CONTINUE.

        **Validates: Requirements 2.2, 2.4**
        """
        classifier = ThreadClassifier()
        result = classifier.classify(user_input, active_thread)
        assert result == Classification.CONTINUE, (
            f"Expected CONTINUE for input with pronoun: {user_input!r}, got {result}"
        )

    @given(
        user_input=_input_with_continuation_phrase,
        active_thread=_active_thread_with_turn,
    )
    @settings(max_examples=30, deadline=None)
    def test_continuation_phrase_produces_continue(self, user_input: str, active_thread: Thread):
        """Input containing a continuation phrase produces CONTINUE.

        **Validates: Requirements 2.2, 2.4**
        """
        classifier = ThreadClassifier()
        result = classifier.classify(user_input, active_thread)
        assert result == Classification.CONTINUE, (
            f"Expected CONTINUE for input with continuation phrase: {user_input!r}, got {result}"
        )

    @given(
        user_input=_input_with_signal,
        active_thread=_active_thread_with_turn,
    )
    @settings(max_examples=30, deadline=None)
    def test_any_high_weight_signal_produces_continue(self, user_input: str, active_thread: Thread):
        """Input containing any high-weight signal (pronoun or phrase) produces CONTINUE.

        **Validates: Requirements 2.2, 2.4**
        """
        classifier = ThreadClassifier()
        result = classifier.classify(user_input, active_thread)
        assert result == Classification.CONTINUE, (
            f"Expected CONTINUE for input with signal: {user_input!r}, got {result}"
        )
