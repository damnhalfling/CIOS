"""Property-based tests for ThreadManager coordination layer.

Feature: conversation-threads
"""

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.thread_manager import (
    PendingQuestion,
    ThreadManager,
    ThreadStore,
)

# --- Strategies ---

# Generate arbitrary user input text (any non-surrogate text)
_user_input = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(blacklist_categories=("Cs",)),
)

# Generate pending question text
_question_text = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(blacklist_categories=("Cs",)),
)


# Feature: conversation-threads, Property 1: Pending question always routes as answer
class TestPendingQuestionAlwaysRoutesAsAnswer:
    """Property 1: Pending question always routes as answer.

    For any active thread with a pending question, and for any user input
    string, ThreadManager.route_input() SHALL return a RoutingDecision with
    action="answer_pending" and the pending question attached.

    **Validates: Requirements 1.1**
    """

    @given(
        initial_input=_user_input,
        question=_question_text,
        answer_input=_user_input,
    )
    @settings(max_examples=30, deadline=None)
    def test_pending_question_always_routes_as_answer(
        self, initial_input: str, question: str, answer_input: str
    ):
        """Regardless of user input content, if there's a pending question,
        it ALWAYS routes as 'answer_pending'.

        **Validates: Requirements 1.1**
        """
        # Set up a ThreadStore with a temp DB
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            # Create a ThreadManager with that store
            manager = ThreadManager(store)

            # First call route_input with initial input to create an active thread
            manager.route_input(initial_input)

            # Set a pending question on the active thread
            pq = PendingQuestion(question=question)
            manager.set_pending_question(pq)

            # Now call route_input with the arbitrary user input
            decision = manager.route_input(answer_input)

            # Verify the result has action="answer_pending"
            assert decision.action == "answer_pending", (
                f"Expected action='answer_pending', got action='{decision.action}' "
                f"for input={answer_input!r} with pending question={question!r}"
            )

            # Verify pending_question is set on the decision
            assert decision.pending_question is not None, (
                f"Expected pending_question to be set on the RoutingDecision, "
                f"but it was None for input={answer_input!r}"
            )

            # Verify the pending question matches what we set
            assert decision.pending_question.question == question, (
                f"Expected pending_question.question={question!r}, "
                f"got {decision.pending_question.question!r}"
            )
        finally:
            store.close()


# Feature: conversation-threads, Property 3: Absence of signals produces NEW_THREAD with old thread closed
class TestAbsenceOfSignalsProducesNewThread:
    """Property 3: Absence of signals produces NEW_THREAD with old thread closed.

    For any user input that contains no continuation signals (no pronoun
    references, different intent category, more than 90 seconds since last
    turn, no continuation phrases), ThreadManager.route_input() SHALL close
    the active thread and return a RoutingDecision with action="new_thread"
    pointing to a freshly created thread.

    **Validates: Requirements 2.3, 2.5, 3.3**
    """

    # Safe words that do NOT contain any pronouns from _ALL_PRONOUNS
    # Avoids: that, this, it, those, the same, that one, esse, essa, isso,
    #         este, esta, nesse, nessa, nisso, dele, dela, aquele, aquela
    _SAFE_WORDS = [
        "open",
        "run",
        "check",
        "start",
        "stop",
        "hello",
        "world",
        "file",
        "folder",
        "network",
        "please",
        "now",
        "scan",
        "build",
        "deploy",
        "clean",
        "show",
        "list",
        "help",
        "menu",
    ]

    @given(
        initial_input=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Zs"),
                blacklist_categories=("Cs",),
            ),
        ),
        safe_words=st.lists(st.sampled_from(_SAFE_WORDS), min_size=1, max_size=5),
    )
    @settings(max_examples=30, deadline=None)
    def test_no_signals_produces_new_thread(self, initial_input: str, safe_words: list[str]):
        """When no continuation signals are present and temporal proximity
        has expired, route_input SHALL close the active thread and return
        action='new_thread' with a different thread ID.

        **Validates: Requirements 2.3, 2.5, 3.3**
        """
        import time as _time

        # Build a user input from safe words (guaranteed no pronouns or
        # continuation phrases)
        new_input = " ".join(safe_words)

        # Set up a ThreadStore with a temp DB
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            manager = ThreadManager(store)

            # Create an active thread with an initial input
            decision1 = manager.route_input(initial_input)
            assert decision1.action == "new_thread"
            old_thread_id = decision1.thread.id

            # Record a turn so the classifier doesn't short-circuit on empty turns
            manager.record_turn(initial_input, "general", {"response": "ok", "status": "success"})

            # Manipulate temporal proximity: set the last turn's timestamp
            # to >90s ago so temporal proximity signal is NOT active
            manager._active_thread.turns[-1].timestamp = _time.time() - 200

            # Also reset the monotonic activity tracker so inactivity timeout
            # doesn't auto-close the thread (180s), but temporal proximity
            # (based on turn timestamp) is expired
            import time as time_mod

            manager._last_activity_mono = time_mod.monotonic()

            # Now route the new input (no pronouns, no continuation phrases,
            # outside temporal window, different/unknown intent)
            decision2 = manager.route_input(new_input)

            # Verify: action should be "new_thread"
            assert decision2.action == "new_thread", (
                f"Expected action='new_thread', got action='{decision2.action}' "
                f"for input={new_input!r} (safe_words={safe_words!r})"
            )

            # Verify: the new thread has a different ID (old thread was closed)
            assert decision2.thread.id != old_thread_id, (
                f"Expected a new thread ID different from {old_thread_id}, "
                f"but got the same ID. Input={new_input!r}"
            )

        finally:
            store.close()


# Feature: conversation-threads, Property 4: Thread creation invariants
class TestThreadCreationInvariants:
    """Property 4: Thread creation invariants.

    For any newly created thread, the thread SHALL have a unique identifier
    (UUID4 hex, distinct from all other thread IDs), a creation timestamp
    within 1 second of the current time, and a non-empty summary derived
    from the first user input.

    **Validates: Requirements 3.1, 3.4**
    """

    @given(user_input=_user_input)
    @settings(max_examples=30, deadline=None)
    def test_new_thread_has_valid_uuid4_id(self, user_input: str):
        """A newly created thread SHALL have a valid UUID4 hex id
        (32 hex characters).

        **Validates: Requirements 3.1**
        """
        import re

        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            manager = ThreadManager(store)

            decision = manager.route_input(user_input)

            # Should be a new thread (no prior active thread)
            assert decision.action == "new_thread"

            # Verify the thread ID is a valid UUID4 hex (32 hex characters)
            thread_id = decision.thread.id
            assert (
                len(thread_id) == 32
            ), f"Expected 32-char hex ID, got {len(thread_id)} chars: {thread_id!r}"
            assert re.fullmatch(
                r"[0-9a-f]{32}", thread_id
            ), f"Expected valid hex string, got: {thread_id!r}"
        finally:
            store.close()

    @given(user_input=_user_input)
    @settings(max_examples=30, deadline=None)
    def test_new_thread_has_creation_timestamp_within_1s(self, user_input: str):
        """A newly created thread SHALL have a creation timestamp within
        1 second of the current time.

        **Validates: Requirements 3.1**
        """
        import time as _time

        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            manager = ThreadManager(store)

            before = _time.time()
            decision = manager.route_input(user_input)
            after = _time.time()

            assert decision.action == "new_thread"

            # Verify created_at is within 1 second of current time
            created_at = decision.thread.created_at
            assert (
                before - 1 <= created_at <= after + 1
            ), f"Expected created_at between {before - 1} and {after + 1}, got {created_at}"
        finally:
            store.close()

    @given(
        user_input=st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "S"),
                blacklist_categories=("Cs",),
            ),
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_new_thread_has_non_empty_summary(self, user_input: str):
        """A newly created thread SHALL have a non-empty summary derived
        from the first user input.

        **Validates: Requirements 3.4**
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            manager = ThreadManager(store)

            decision = manager.route_input(user_input)

            assert decision.action == "new_thread"

            # Verify summary is non-empty
            assert decision.thread.summary, (
                f"Expected non-empty summary for input={user_input!r}, "
                f"got summary={decision.thread.summary!r}"
            )

            # Verify summary is derived from user input (it should be a
            # prefix/truncation of the stripped input, or a fallback for whitespace-only)
            stripped = user_input.strip()
            if not stripped:
                # Whitespace-only input gets a fallback summary
                assert decision.thread.summary == "Nova conversa"
            elif len(stripped) <= 50:
                assert decision.thread.summary == stripped
            else:
                # Truncated to 47 chars + "..."
                assert decision.thread.summary == stripped[:47] + "..."
        finally:
            store.close()

    @given(user_inputs=st.lists(_user_input, min_size=2, max_size=10, unique=True))
    @settings(max_examples=30, deadline=None)
    def test_multiple_threads_have_unique_ids(self, user_inputs: list[str]):
        """Multiple newly created threads SHALL have unique IDs (no
        collisions).

        **Validates: Requirements 3.1**
        """

        thread_ids = []

        for user_input in user_inputs:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
                db_path = Path(tmp.name)

            store = ThreadStore(db_path=db_path)
            try:
                manager = ThreadManager(store)
                decision = manager.route_input(user_input)
                assert decision.action == "new_thread"
                thread_ids.append(decision.thread.id)
            finally:
                store.close()

        # Verify all IDs are unique
        assert len(thread_ids) == len(
            set(thread_ids)
        ), f"Expected all unique IDs, but found duplicates in: {thread_ids}"
