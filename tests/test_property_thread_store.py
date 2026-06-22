"""Property-based tests for ThreadStore persistence.

Feature: conversation-threads
"""

import tempfile
import uuid
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.thread_manager import (
    ConversationTurn,
    Thread,
    ThreadStore,
)

# --- Strategies ---

# Generate valid UUID4 hex strings (32 hex chars)
_uuid_hex = st.uuids(version=4).map(lambda u: u.hex)

# Generate reasonable timestamps (positive floats, not too large for SQLite)
_timestamp = st.floats(
    min_value=1_000_000_000.0, max_value=2_000_000_000.0, allow_nan=False, allow_infinity=False
)

# Generate non-empty text for user inputs and summaries
_text = st.text(min_size=1, max_size=200, alphabet=st.characters(blacklist_categories=("Cs",)))

# Generate intent types
_intent_type = st.sampled_from(["network", "system", "app", "media", "file", "general", "search"])

# Generate outcome values
_outcome = st.sampled_from(["success", "error", "incomplete", ""])

# Generate simple JSON-serializable params dicts
_params = st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    values=st.one_of(
        st.text(max_size=50), st.integers(min_value=-1000, max_value=1000), st.booleans()
    ),
    max_size=5,
)

# Generate a ConversationTurn
_turn = st.builds(
    ConversationTurn,
    user_input=_text,
    intent_type=_intent_type,
    params=_params,
    result_summary=st.text(max_size=200, alphabet=st.characters(blacklist_categories=("Cs",))),
    outcome=_outcome,
    timestamp=_timestamp,
)

# Generate a Thread with status="completed" (for persistence round-trip)
_thread = st.builds(
    Thread,
    id=_uuid_hex,
    created_at=_timestamp,
    closed_at=st.one_of(st.none(), _timestamp),
    summary=_text,
    status=st.just("completed"),
    turns=st.lists(_turn, min_size=0, max_size=10),
    dominant_intent=_intent_type,
    outcome=_outcome,
)


# --- Property Tests ---


# Feature: conversation-threads, Property 5: Thread persistence round-trip
class TestThreadPersistenceRoundTrip:
    """Property 5: Thread persistence round-trip.

    For any valid Thread object (with arbitrary turns, summary, timestamps,
    and outcome), saving it to ThreadStore and then retrieving it SHALL produce
    a Thread with identical field values.

    **Validates: Requirements 3.5, 5.1**
    """

    @given(thread=_thread)
    @settings(max_examples=30, deadline=None)
    def test_save_and_retrieve_preserves_all_fields(self, thread: Thread):
        """Save a thread to ThreadStore, retrieve it, verify all fields match.

        **Validates: Requirements 3.5, 5.1**
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            # Save the thread
            store.save_thread(thread)

            # Retrieve it via get_recent (which filters by status='completed')
            retrieved_threads = store.get_recent(limit=1)

            assert len(retrieved_threads) == 1, f"Expected 1 thread, got {len(retrieved_threads)}"

            retrieved = retrieved_threads[0]

            # Verify all persisted fields match
            assert retrieved.id == thread.id, f"ID mismatch: {retrieved.id!r} != {thread.id!r}"
            assert (
                retrieved.created_at == thread.created_at
            ), f"created_at mismatch: {retrieved.created_at} != {thread.created_at}"
            assert (
                retrieved.closed_at == thread.closed_at
            ), f"closed_at mismatch: {retrieved.closed_at} != {thread.closed_at}"
            assert (
                retrieved.summary == thread.summary
            ), f"summary mismatch: {retrieved.summary!r} != {thread.summary!r}"
            assert (
                retrieved.status == thread.status
            ), f"status mismatch: {retrieved.status!r} != {thread.status!r}"
            assert (
                retrieved.dominant_intent == thread.dominant_intent
            ), f"dominant_intent mismatch: {retrieved.dominant_intent!r} != {thread.dominant_intent!r}"
            assert (
                retrieved.outcome == thread.outcome
            ), f"outcome mismatch: {retrieved.outcome!r} != {thread.outcome!r}"

            # Verify turns count
            assert len(retrieved.turns) == len(
                thread.turns
            ), f"turns count mismatch: {len(retrieved.turns)} != {len(thread.turns)}"

            # Verify each turn's fields
            for i, (orig_turn, ret_turn) in enumerate(
                zip(thread.turns, retrieved.turns, strict=False)
            ):
                assert (
                    ret_turn.user_input == orig_turn.user_input
                ), f"Turn {i} user_input mismatch: {ret_turn.user_input!r} != {orig_turn.user_input!r}"
                assert (
                    ret_turn.intent_type == orig_turn.intent_type
                ), f"Turn {i} intent_type mismatch: {ret_turn.intent_type!r} != {orig_turn.intent_type!r}"
                assert (
                    ret_turn.params == orig_turn.params
                ), f"Turn {i} params mismatch: {ret_turn.params!r} != {orig_turn.params!r}"
                assert (
                    ret_turn.result_summary == orig_turn.result_summary
                ), f"Turn {i} result_summary mismatch: {ret_turn.result_summary!r} != {orig_turn.result_summary!r}"
                assert (
                    ret_turn.outcome == orig_turn.outcome
                ), f"Turn {i} outcome mismatch: {ret_turn.outcome!r} != {orig_turn.outcome!r}"
                assert (
                    ret_turn.timestamp == orig_turn.timestamp
                ), f"Turn {i} timestamp mismatch: {ret_turn.timestamp} != {orig_turn.timestamp}"
        finally:
            store.close()


# --- Lightweight strategy for storage limit tests (no turns, minimal fields) ---

_lightweight_thread = st.builds(
    Thread,
    id=_uuid_hex,
    created_at=_timestamp,
    closed_at=st.none(),
    summary=st.just("test thread"),
    status=st.just("completed"),
    turns=st.just([]),
    dominant_intent=st.just("general"),
    outcome=st.just("success"),
)


# Feature: conversation-threads, Property 6: Storage limit invariant
class TestStorageLimitInvariant:
    """Property 6: Storage limit invariant.

    For any sequence of thread saves to ThreadStore, the total number of
    stored threads SHALL never exceed 50. When a save would exceed the limit,
    the oldest thread(s) SHALL be deleted first.

    **Validates: Requirements 5.2**
    """

    @given(
        num_threads=st.integers(min_value=51, max_value=70),
    )
    @settings(max_examples=30, deadline=None)
    def test_stored_count_never_exceeds_limit(self, num_threads: int):
        """Save more than 50 threads, verify stored count never exceeds 50.

        **Validates: Requirements 5.2**
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            # Create and save threads with distinct timestamps
            for i in range(num_threads):
                thread = Thread(
                    id=uuid.uuid4().hex,
                    created_at=1_000_000_000.0 + i,
                    summary=f"thread {i}",
                    status="completed",
                    turns=[],
                    dominant_intent="general",
                    outcome="success",
                )
                store.save_thread(thread)

            # Verify stored count does not exceed 50
            stored = store.get_by_date_range(0.0, 3_000_000_000.0)
            assert (
                len(stored) <= 50
            ), f"Storage limit violated: {len(stored)} threads stored, expected <= 50"
        finally:
            store.close()

    @given(
        num_threads=st.integers(min_value=51, max_value=70),
    )
    @settings(max_examples=30, deadline=None)
    def test_oldest_threads_deleted_first(self, num_threads: int):
        """Save more than 50 threads, verify oldest are evicted first.

        **Validates: Requirements 5.2**
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            # Create threads with distinct timestamps and track their IDs
            all_threads = []
            for i in range(num_threads):
                thread = Thread(
                    id=uuid.uuid4().hex,
                    created_at=1_000_000_000.0 + i,
                    summary=f"thread {i}",
                    status="completed",
                    turns=[],
                    dominant_intent="general",
                    outcome="success",
                )
                all_threads.append(thread)
                store.save_thread(thread)

            # Retrieve all stored threads
            stored = store.get_by_date_range(0.0, 3_000_000_000.0)
            stored_ids = {t.id for t in stored}

            # The 50 most recent threads (by created_at) should be the ones kept
            expected_kept = all_threads[-50:]
            expected_kept_ids = {t.id for t in expected_kept}

            assert stored_ids == expected_kept_ids, (
                f"Expected the 50 most recent threads to be kept. "
                f"Missing: {expected_kept_ids - stored_ids}, "
                f"Unexpected: {stored_ids - expected_kept_ids}"
            )
        finally:
            store.close()


# Feature: conversation-threads, Property 7: Filter query correctness
class TestFilterQueryCorrectness:
    """Property 7: Filter query correctness.

    For any set of stored threads and for any date range filter [start, end],
    all returned threads SHALL have created_at within that range, and no thread
    within that range SHALL be excluded. Similarly, for any intent category
    filter, all returned threads SHALL have a matching dominant_intent.

    **Validates: Requirements 5.5**
    """

    @given(
        threads=st.lists(
            st.builds(
                Thread,
                id=_uuid_hex,
                created_at=_timestamp,
                closed_at=st.none(),
                summary=st.just("filter test"),
                status=st.just("completed"),
                turns=st.just([]),
                dominant_intent=_intent_type,
                outcome=st.just("success"),
            ),
            min_size=1,
            max_size=20,
        ),
        range_start=_timestamp,
        range_end=_timestamp,
    )
    @settings(max_examples=30, deadline=None)
    def test_date_range_filter_returns_exactly_matching_threads(
        self, threads: list, range_start: float, range_end: float
    ):
        """All returned threads are within [start, end] and none within range are excluded.

        **Validates: Requirements 5.5**
        """
        # Ensure start <= end
        start = min(range_start, range_end)
        end = max(range_start, range_end)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            # Save all threads
            for thread in threads:
                store.save_thread(thread)

            # Query by date range
            results = store.get_by_date_range(start, end)
            result_ids = {t.id for t in results}

            # Determine which threads should be in range
            # (accounting for the 50-thread limit — only the 50 most recent are kept)
            # First figure out which threads survived the limit enforcement
            all_sorted = sorted(threads, key=lambda t: t.created_at, reverse=True)
            surviving = all_sorted[:50]
            surviving_ids = {t.id for t in surviving}

            expected_ids = {
                t.id for t in surviving if t.created_at >= start and t.created_at <= end
            }

            # Property 1: All returned threads have created_at within [start, end]
            for result in results:
                assert start <= result.created_at <= end, (
                    f"Thread {result.id} has created_at={result.created_at} "
                    f"which is outside range [{start}, {end}]"
                )

            # Property 2: No thread within [start, end] is excluded from results
            assert result_ids == expected_ids, (
                f"Missing threads: {expected_ids - result_ids}, "
                f"Unexpected threads: {result_ids - expected_ids}"
            )
        finally:
            store.close()

    @given(
        threads=st.lists(
            st.builds(
                Thread,
                id=_uuid_hex,
                created_at=_timestamp,
                closed_at=st.none(),
                summary=st.just("intent test"),
                status=st.just("completed"),
                turns=st.just([]),
                dominant_intent=_intent_type,
                outcome=st.just("success"),
            ),
            min_size=1,
            max_size=20,
        ),
        filter_intent=_intent_type,
    )
    @settings(max_examples=30, deadline=None)
    def test_intent_filter_returns_exactly_matching_threads(
        self, threads: list, filter_intent: str
    ):
        """All returned threads have matching dominant_intent and none with that intent are excluded.

        **Validates: Requirements 5.5**
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            # Save all threads
            for thread in threads:
                store.save_thread(thread)

            # Query by intent
            results = store.get_by_intent(filter_intent)
            result_ids = {t.id for t in results}

            # Determine which threads survived the limit enforcement
            all_sorted = sorted(threads, key=lambda t: t.created_at, reverse=True)
            surviving = all_sorted[:50]

            expected_ids = {t.id for t in surviving if t.dominant_intent == filter_intent}

            # Property 1: All returned threads have matching dominant_intent
            for result in results:
                assert result.dominant_intent == filter_intent, (
                    f"Thread {result.id} has dominant_intent={result.dominant_intent!r} "
                    f"which does not match filter {filter_intent!r}"
                )

            # Property 2: No thread with matching intent is excluded from results
            assert result_ids == expected_ids, (
                f"Missing threads: {expected_ids - result_ids}, "
                f"Unexpected threads: {result_ids - expected_ids}"
            )
        finally:
            store.close()


# Feature: conversation-threads, Property 8: Cloud sync payload sanitization
class TestCloudSyncPayloadSanitization:
    """Property 8: Cloud sync payload sanitization.

    For any Thread object (including turns with arbitrary params containing
    sensitive data), the cloud sync payload SHALL contain only: thread_id,
    created_at, closed_at, summary, outcome, and turns with only user_input,
    intent_type, result_summary, outcome, and timestamp. No params,
    credentials, or system state SHALL appear in the payload.

    **Validates: Requirements 8.3**
    """

    # Strategy: generate turns with params containing sensitive keys.
    # Use a distinctive prefix to avoid false positives from coincidental
    # substring matches with timestamps or other numeric fields.
    _sensitive_value = st.text(
        min_size=8, max_size=50, alphabet=st.characters(whitelist_categories=("L",))
    ).map(lambda v: f"SECRET_{v}")

    _sensitive_params = st.dictionaries(
        keys=st.sampled_from(
            ["password", "token", "api_key", "sudo_password", "secret", "credentials", "auth_token"]
        ),
        values=_sensitive_value,
        min_size=1,
        max_size=5,
    )

    _turn_with_sensitive_params = st.builds(
        ConversationTurn,
        user_input=_text,
        intent_type=_intent_type,
        params=_sensitive_params,
        result_summary=st.text(max_size=100, alphabet=st.characters(blacklist_categories=("Cs",))),
        outcome=_outcome,
        timestamp=_timestamp,
    )

    _thread_with_sensitive_turns = st.builds(
        Thread,
        id=_uuid_hex,
        created_at=_timestamp,
        closed_at=st.one_of(st.none(), _timestamp),
        summary=_text,
        status=st.just("completed"),
        turns=st.lists(_turn_with_sensitive_params, min_size=1, max_size=10),
        dominant_intent=_intent_type,
        outcome=_outcome,
    )

    @given(thread=_thread_with_sensitive_turns)
    @settings(max_examples=30, deadline=None)
    def test_payload_contains_only_allowed_top_level_keys(self, thread: Thread):
        """Verify the sync payload only contains allowed top-level keys.

        **Validates: Requirements 8.3**
        """
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp:
            db_path = Path(tmp.name)

        store = ThreadStore(db_path=db_path)
        try:
            payload = store._build_sync_payload(thread)

            # Allowed top-level keys
            allowed_top_keys = {
                "thread_id",
                "created_at",
                "closed_at",
                "summary",
                "outcome",
                "dominant_intent",
                "turns",
            }
            actual_keys = set(payload.keys())

            assert actual_keys == allowed_top_keys, (
                f"Payload has unexpected top-level keys. "
                f"Extra: {actual_keys - allowed_top_keys}, "
                f"Missing: {allowed_top_keys - actual_keys}"
            )

            # Verify each turn only contains allowed keys
            allowed_turn_keys = {
                "user_input",
                "intent_type",
                "result_summary",
                "outcome",
                "timestamp",
            }
            for i, turn_payload in enumerate(payload["turns"]):
                turn_keys = set(turn_payload.keys())
                assert turn_keys == allowed_turn_keys, (
                    f"Turn {i} has unexpected keys. "
                    f"Extra: {turn_keys - allowed_turn_keys}, "
                    f"Missing: {allowed_turn_keys - turn_keys}"
                )

            # Verify "params" does NOT appear anywhere in the payload
            payload_json = json.dumps(payload)
            assert (
                '"params"' not in payload_json
            ), "Payload contains 'params' key which should be excluded"

            # Verify sensitive values from params do NOT appear in the serialized payload
            for turn in thread.turns:
                for key, value in turn.params.items():
                    assert value not in payload_json, (
                        f"Sensitive param value {value!r} (from key {key!r}) "
                        f"leaked into the sync payload"
                    )
        finally:
            store.close()
