"""Thread Manager — structured conversation threading for CIOS.

Provides:
- Thread data model (conversation unit with turns, lifecycle, persistence)
- ThreadClassifier (deterministic signal-based continuation detection)
- ThreadManager (coordination layer — owns all conversation state)
- ThreadStore (SQLite persistence for completed threads)

All thread-related logic lives in this single module to keep the change
surface minimal and the dependency graph simple.
"""

import enum
import json
import logging
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from cios.core import config as _config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  CONFIGURATION CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

PENDING_QUESTION_TIMEOUT = 120  # seconds before pending question expires
THREAD_INACTIVITY_TIMEOUT = 180  # seconds before idle thread auto-closes
MAX_LOCAL_THREADS = 50  # SQLite storage limit
THREAD_CONTEXT_TURNS = 5  # Turns kept for pronoun resolution
CLASSIFICATION_TEMPORAL_WINDOW = 90  # seconds for "recent enough" signal


# ═══════════════════════════════════════════════════════════════════════════
#  DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════


class Classification(enum.Enum):
    """Result of thread classification — continue or start new."""

    CONTINUE = "continue"
    NEW_THREAD = "new_thread"


@dataclass
class ConversationTurn:
    """A single turn in a conversation thread."""

    user_input: str
    intent_type: str
    params: dict = field(default_factory=dict)
    result_summary: str = ""
    outcome: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class PendingQuestion:
    """A system-generated question awaiting user response within a thread."""

    question: str
    timestamp: float = field(default_factory=time.time)
    timeout: float = PENDING_QUESTION_TIMEOUT


@dataclass
class Thread:
    """A conversation thread — the unit of conversational continuity."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    closed_at: float | None = None
    summary: str = ""
    status: str = "active"  # "active" | "completed" | "expired"
    turns: list[ConversationTurn] = field(default_factory=list)
    pending_question: PendingQuestion | None = None
    dominant_intent: str = ""
    outcome: str = ""  # "success" | "error" | "incomplete"


@dataclass
class RoutingDecision:
    """Result of ThreadManager.route_input()."""

    action: str  # "answer_pending" | "continue_thread" | "new_thread"
    thread: Thread
    pending_question: PendingQuestion | None = None


# ═══════════════════════════════════════════════════════════════════════════
#  THREAD STORE — SQLite persistence for completed threads
# ═══════════════════════════════════════════════════════════════════════════

_THREAD_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    closed_at REAL,
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    dominant_intent TEXT DEFAULT '',
    outcome TEXT DEFAULT '',
    synced INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_threads_created ON threads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_threads_status ON threads(status);
CREATE INDEX IF NOT EXISTS idx_threads_intent ON threads(dominant_intent);

CREATE TABLE IF NOT EXISTS thread_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    user_input TEXT NOT NULL,
    intent_type TEXT NOT NULL,
    params TEXT DEFAULT '{}',
    result_summary TEXT DEFAULT '',
    outcome TEXT DEFAULT '',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_thread ON thread_turns(thread_id, turn_index);
"""


class ThreadStore:
    """SQLite persistence for completed threads. Reuses memory.db.

    Thread-safe: all operations are protected by a threading.Lock.
    All DB operations are wrapped in try/except — errors are logged,
    never propagated to callers.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Connect to SQLite and create tables if needed."""
        _config.ensure_dirs()
        if db_path is None:
            db_path = _config.DB_PATH
        self._db_path = db_path
        self._lock = threading.Lock()
        try:
            self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript(_THREAD_SCHEMA)
        except Exception as e:
            logger.error("ThreadStore: failed to initialize database: %s", e)
            # Create a minimal in-memory fallback so methods don't crash
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_THREAD_SCHEMA)

    def save_thread(self, thread: Thread) -> None:
        """Persist a completed thread and its turns. Enforces 50-thread limit."""
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT OR REPLACE INTO threads
                       (id, created_at, closed_at, summary, status,
                        dominant_intent, outcome, synced)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                    (
                        thread.id,
                        thread.created_at,
                        thread.closed_at,
                        thread.summary,
                        thread.status,
                        thread.dominant_intent,
                        thread.outcome,
                    ),
                )
                # Delete existing turns for this thread (in case of re-save)
                self._conn.execute(
                    "DELETE FROM thread_turns WHERE thread_id = ?",
                    (thread.id,),
                )
                # Insert all turns
                for idx, turn in enumerate(thread.turns):
                    self._conn.execute(
                        """INSERT INTO thread_turns
                           (thread_id, turn_index, user_input, intent_type,
                            params, result_summary, outcome, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            thread.id,
                            idx,
                            turn.user_input,
                            turn.intent_type,
                            json.dumps(turn.params),
                            turn.result_summary,
                            turn.outcome,
                            turn.timestamp,
                        ),
                    )
                self._conn.commit()
                # Enforce storage limit after saving
                self._enforce_limit_unlocked(MAX_LOCAL_THREADS)
            except Exception as e:
                logger.error("ThreadStore: failed to save thread %s: %s", thread.id, e)

    def get_recent(self, limit: int = 10) -> list[Thread]:
        """Load most recent completed threads with their turns."""
        with self._lock:
            try:
                rows = self._conn.execute(
                    """SELECT * FROM threads
                       WHERE status = 'completed'
                       ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
                return [self._load_thread_with_turns(row) for row in rows]
            except Exception as e:
                logger.error("ThreadStore: failed to get recent threads: %s", e)
                return []

    def get_by_date_range(self, start: float, end: float) -> list[Thread]:
        """Filter threads by timestamp range (inclusive on both ends)."""
        with self._lock:
            try:
                rows = self._conn.execute(
                    """SELECT * FROM threads
                       WHERE created_at >= ? AND created_at <= ?
                       ORDER BY created_at DESC""",
                    (start, end),
                ).fetchall()
                return [self._load_thread_with_turns(row) for row in rows]
            except Exception as e:
                logger.error("ThreadStore: failed to get threads by date range: %s", e)
                return []

    def get_by_intent(self, intent_category: str) -> list[Thread]:
        """Filter threads by dominant intent."""
        with self._lock:
            try:
                rows = self._conn.execute(
                    """SELECT * FROM threads
                       WHERE dominant_intent = ?
                       ORDER BY created_at DESC""",
                    (intent_category,),
                ).fetchall()
                return [self._load_thread_with_turns(row) for row in rows]
            except Exception as e:
                logger.error("ThreadStore: failed to get threads by intent: %s", e)
                return []

    def enforce_limit(self, max_threads: int = MAX_LOCAL_THREADS) -> None:
        """Delete oldest threads beyond the limit."""
        with self._lock:
            self._enforce_limit_unlocked(max_threads)

    def _enforce_limit_unlocked(self, max_threads: int) -> None:
        """Internal enforce_limit — caller must hold the lock."""
        try:
            count_row = self._conn.execute("SELECT COUNT(*) as cnt FROM threads").fetchone()
            count = count_row["cnt"] if count_row else 0
            if count > max_threads:
                excess = count - max_threads
                # Delete the oldest threads (by created_at ascending)
                self._conn.execute(
                    """DELETE FROM threads WHERE id IN (
                        SELECT id FROM threads
                        ORDER BY created_at ASC LIMIT ?
                    )""",
                    (excess,),
                )
                self._conn.commit()
        except Exception as e:
            logger.error("ThreadStore: failed to enforce limit: %s", e)

    def _load_thread_with_turns(self, row: sqlite3.Row) -> Thread:
        """Build a Thread object from a DB row, loading its turns."""
        turn_rows = self._conn.execute(
            """SELECT * FROM thread_turns
               WHERE thread_id = ?
               ORDER BY turn_index ASC""",
            (row["id"],),
        ).fetchall()
        turns = [
            ConversationTurn(
                user_input=tr["user_input"],
                intent_type=tr["intent_type"],
                params=json.loads(tr["params"]) if tr["params"] else {},
                result_summary=tr["result_summary"] or "",
                outcome=tr["outcome"] or "",
                timestamp=tr["timestamp"],
            )
            for tr in turn_rows
        ]
        return Thread(
            id=row["id"],
            created_at=row["created_at"],
            closed_at=row["closed_at"],
            summary=row["summary"] or "",
            status=row["status"] or "active",
            turns=turns,
            dominant_intent=row["dominant_intent"] or "",
            outcome=row["outcome"] or "",
        )

    def _build_sync_payload(self, thread: Thread) -> dict:
        """Build a sanitized payload for cloud sync.

        Only includes: thread_id, created_at, closed_at, summary, outcome,
        and turns with user_input, intent_type, result_summary, outcome, timestamp.
        No params, credentials, or system state are included.
        """
        turns_payload = [
            {
                "user_input": turn.user_input,
                "intent_type": turn.intent_type,
                "result_summary": turn.result_summary,
                "outcome": turn.outcome,
                "timestamp": turn.timestamp,
            }
            for turn in thread.turns
        ]
        return {
            "thread_id": thread.id,
            "created_at": thread.created_at,
            "closed_at": thread.closed_at,
            "summary": thread.summary,
            "outcome": thread.outcome,
            "turns": turns_payload,
        }

    def sync_to_cloud(self, thread: Thread) -> None:
        """Upload thread to api.cios-ia.com (async, fire-and-forget).

        Only syncs when the user is logged into CIOS Intelligence.
        Runs in a daemon thread with a 10-second timeout.
        On any failure: silently catches, logs at DEBUG, marks thread synced=0.
        On success: marks thread synced=1.
        """
        from cios.core.intelligence import intelligence

        if not intelligence.is_logged_in:
            return

        token = intelligence.user.token if intelligence.user else ""
        if not token:
            return

        payload = self._build_sync_payload(thread)

        def _do_sync():
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.cios-ia.com/threads",
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp.read()
                # Success — mark synced=1
                self._mark_synced(thread.id, 1)
            except Exception as e:
                logger.debug("ThreadStore: cloud sync failed for %s: %s", thread.id, e)
                self._mark_synced(thread.id, 0)

        t = threading.Thread(target=_do_sync, daemon=True)
        t.start()

    def _mark_synced(self, thread_id: str, synced: int) -> None:
        """Update the synced flag for a thread in the database."""
        with self._lock:
            try:
                self._conn.execute(
                    "UPDATE threads SET synced = ? WHERE id = ?",
                    (synced, thread_id),
                )
                self._conn.commit()
            except Exception as e:
                logger.error("ThreadStore: failed to update synced flag for %s: %s", thread_id, e)

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except Exception as e:
            logger.error("ThreadStore: failed to close connection: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
#  THREAD CLASSIFIER — deterministic signal-based continuation detection
# ═══════════════════════════════════════════════════════════════════════════

# Pronouns that reference previous context (mirrored from bridge.py)
_PRONOUNS_PT = {
    "esse",
    "essa",
    "isso",
    "este",
    "esta",
    "nesse",
    "nessa",
    "nisso",
    "dele",
    "dela",
    "aquele",
    "aquela",
}
_PRONOUNS_EN = {"that", "this", "it", "those", "the same", "that one"}
_ALL_PRONOUNS = _PRONOUNS_PT | _PRONOUNS_EN

# Continuation phrases — explicit markers that the user wants to extend the thread
_CONTINUATION_PHRASES = [
    "e também",
    "além disso",
    "and also",
    "what about",
]


class ThreadClassifier:
    """Determines whether input continues the active thread or starts new.

    Deterministic — no LLM calls, no network, no latency.

    Signal weights:
        High:   pronoun reference, continuation phrase
        Medium: same intent category, temporal proximity (<90s)

    Scoring:
        - Any high-weight signal fires → CONTINUE
        - Two or more medium-weight signals → CONTINUE
        - Otherwise → NEW_THREAD
        - No active thread → always NEW_THREAD
    """

    def classify(self, user_input: str, active_thread: Thread | None) -> Classification:
        """Classify input as CONTINUE or NEW_THREAD.

        Args:
            user_input: The raw user input string.
            active_thread: The currently active thread, or None if no thread
                           is active.

        Returns:
            Classification.CONTINUE if the input should continue the active
            thread, Classification.NEW_THREAD otherwise.
        """
        # Edge case: no active thread → always start new
        if active_thread is None:
            return Classification.NEW_THREAD

        # Edge case: active thread has no turns → always start new
        if not active_thread.turns:
            return Classification.NEW_THREAD

        # --- Detect signals ---
        has_pronoun = self._has_pronoun_reference(user_input)
        has_continuation = self._has_continuation_phrase(user_input)
        has_same_intent = self._has_same_intent(user_input, active_thread)
        has_temporal = self._has_temporal_proximity(active_thread)

        # --- Scoring logic ---
        # Any high-weight signal → CONTINUE
        if has_pronoun or has_continuation:
            return Classification.CONTINUE

        # Count medium-weight signals
        medium_count = sum([has_same_intent, has_temporal])

        # Two or more medium signals → CONTINUE
        if medium_count >= 2:
            return Classification.CONTINUE

        # Otherwise → NEW_THREAD
        return Classification.NEW_THREAD

    def _has_pronoun_reference(self, user_input: str) -> bool:
        """Check if input contains a pronoun referencing previous context."""
        input_lower = user_input.lower()
        # Check multi-word pronouns first (e.g. "the same", "that one")
        for pronoun in _ALL_PRONOUNS:
            if " " in pronoun:
                if pronoun in input_lower:
                    return True
            else:
                # Single-word: check word boundaries
                words = input_lower.split()
                if pronoun in words:
                    return True
        return False

    def _has_continuation_phrase(self, user_input: str) -> bool:
        """Check if input contains an explicit continuation phrase."""
        input_lower = user_input.lower()
        return any(phrase in input_lower for phrase in _CONTINUATION_PHRASES)

    def _has_same_intent(self, user_input: str, active_thread: Thread) -> bool:
        """Check if the parsed intent matches the active thread's dominant intent."""
        if not active_thread.dominant_intent:
            return False

        try:
            from cios.core.intent_parser import IntentType, parse_intent

            intent = parse_intent(user_input)
            # Only consider it a match if the intent was actually recognized
            if intent.type == IntentType.UNKNOWN:
                return False
            return intent.type.value == active_thread.dominant_intent
        except Exception:
            return False

    def _has_temporal_proximity(self, active_thread: Thread) -> bool:
        """Check if the last turn was within the temporal window (<90s)."""
        if not active_thread.turns:
            return False

        last_turn = active_thread.turns[-1]
        elapsed = time.time() - last_turn.timestamp
        return elapsed < CLASSIFICATION_TEMPORAL_WINDOW


# ═══════════════════════════════════════════════════════════════════════════
#  THREAD MANAGER — coordination layer, owns all conversation state
# ═══════════════════════════════════════════════════════════════════════════


class ThreadManager:
    """Manages conversation threads — owns all conversation state.

    The bridge delegates to this class instead of managing _pending_question
    and _conversation directly. A single threading.Lock protects all reads
    and writes to thread state, eliminating race conditions.
    """

    def __init__(self, store: ThreadStore) -> None:
        self._store = store
        self._lock = threading.Lock()
        self._active_thread: Thread | None = None
        self._classifier = ThreadClassifier()
        self._inactivity_timer: threading.Timer | None = None
        # Monotonic timestamps for duration checks
        self._last_activity_mono: float = time.monotonic()
        self._pending_question_mono: float | None = None

    def route_input(self, user_input: str) -> RoutingDecision:
        """Determine how to handle user input relative to thread state.

        Returns a RoutingDecision indicating whether this is:
        - An answer to a pending question ("answer_pending")
        - A continuation of the active thread ("continue_thread")
        - The start of a new thread ("new_thread")

        Thread-safe: acquires lock for the entire read-modify cycle.
        """
        with self._lock:
            # Check for pending question expiration first
            self._check_pending_expiration_unlocked()

            # Check for inactivity timeout
            self._check_inactivity_unlocked()

            # If there's an active thread with a pending question, route as answer
            if self._active_thread is not None and self._active_thread.pending_question is not None:
                pq = self._active_thread.pending_question
                self._update_activity_unlocked()
                return RoutingDecision(
                    action="answer_pending",
                    thread=self._active_thread,
                    pending_question=pq,
                )

            # Delegate to classifier
            classification = self._classifier.classify(user_input, self._active_thread)

            if classification == Classification.CONTINUE and self._active_thread is not None:
                self._update_activity_unlocked()
                return RoutingDecision(
                    action="continue_thread",
                    thread=self._active_thread,
                )

            # NEW_THREAD: close old thread (if any), create new one
            if self._active_thread is not None:
                self._close_thread_unlocked(self._active_thread)

            new_thread = self._create_thread_unlocked(user_input)
            self._active_thread = new_thread
            self._update_activity_unlocked()
            return RoutingDecision(
                action="new_thread",
                thread=new_thread,
            )

    def record_turn(self, user_input: str, intent, result: dict) -> None:
        """Record a completed turn in the active thread.

        Args:
            user_input: The raw user input string.
            intent: Either a string (intent type) or an object with a .type
                    attribute (e.g., Intent dataclass).
            result: The execution result dict.
        """
        with self._lock:
            if self._active_thread is None:
                return

            # Extract intent type string — handle both str and object with .type
            if isinstance(intent, str):
                intent_type = intent
            elif hasattr(intent, "type"):
                intent_val = intent.type
                # Handle enum values (e.g., IntentType.NETWORK → "network")
                if hasattr(intent_val, "value"):
                    intent_type = intent_val.value
                else:
                    intent_type = str(intent_val)
            else:
                intent_type = str(intent)

            # Extract params if available
            params = {}
            if hasattr(intent, "params"):
                params = intent.params if isinstance(intent.params, dict) else {}

            # Build turn
            turn = ConversationTurn(
                user_input=user_input,
                intent_type=intent_type,
                params=params,
                result_summary=result.get("response", ""),
                outcome=result.get("status", ""),
                timestamp=time.time(),
            )
            self._active_thread.turns.append(turn)

            # Update dominant intent
            self._update_dominant_intent_unlocked()

            # Reset inactivity timer
            self._update_activity_unlocked()

    def set_pending_question(self, question: PendingQuestion) -> None:
        """Set a pending question on the active thread atomically."""
        with self._lock:
            if self._active_thread is None:
                return
            self._active_thread.pending_question = question
            self._pending_question_mono = time.monotonic()

    def clear_pending_question(self) -> PendingQuestion | None:
        """Atomically read and clear the pending question.

        Returns the PendingQuestion if one was set, or None.
        """
        with self._lock:
            if self._active_thread is None:
                return None
            pq = self._active_thread.pending_question
            self._active_thread.pending_question = None
            self._pending_question_mono = None
            return pq

    def close_active_thread(self) -> None:
        """Close the active thread and persist it to the store."""
        with self._lock:
            if self._active_thread is None:
                return
            self._close_thread_unlocked(self._active_thread)
            self._active_thread = None

    def get_conversation_context(self) -> list[ConversationTurn]:
        """Get recent turns for pronoun resolution.

        Returns the last THREAD_CONTEXT_TURNS (5) turns from the active
        thread, or an empty list if no active thread.
        """
        with self._lock:
            if self._active_thread is None:
                return []
            return list(self._active_thread.turns[-THREAD_CONTEXT_TURNS:])

    def get_recent_threads(self, limit: int = 10) -> list[Thread]:
        """Get completed threads for UI display. Delegates to store."""
        return self._store.get_recent(limit)

    # ─── Internal helpers (caller must hold the lock) ─────────────────────

    def _check_pending_expiration_unlocked(self) -> None:
        """Expire pending question if it has exceeded the timeout."""
        if (
            self._active_thread is not None
            and self._active_thread.pending_question is not None
            and self._pending_question_mono is not None
        ):
            elapsed = time.monotonic() - self._pending_question_mono
            if elapsed > PENDING_QUESTION_TIMEOUT:
                logger.info(
                    "Pending question expired after %.1fs in thread %s",
                    elapsed,
                    self._active_thread.id,
                )
                self._active_thread.pending_question = None
                self._pending_question_mono = None

    def _check_inactivity_unlocked(self) -> None:
        """Auto-close thread if inactivity timeout has been exceeded."""
        if self._active_thread is None:
            return
        elapsed = time.monotonic() - self._last_activity_mono
        if elapsed > THREAD_INACTIVITY_TIMEOUT:
            logger.info(
                "Thread %s auto-closed after %.1fs of inactivity",
                self._active_thread.id,
                elapsed,
            )
            self._close_thread_unlocked(self._active_thread)
            self._active_thread = None

    def _close_thread_unlocked(self, thread: Thread) -> None:
        """Close a thread: set status, timestamp, persist to store."""
        thread.status = "completed"
        thread.closed_at = time.time()
        # Determine outcome from turns
        if not thread.outcome:
            if thread.turns:
                last_outcome = thread.turns[-1].outcome
                if last_outcome:
                    thread.outcome = last_outcome
                else:
                    thread.outcome = "success"
            else:
                thread.outcome = "incomplete"
        self._store.save_thread(thread)
        # Cancel any inactivity timer
        if self._inactivity_timer is not None:
            self._inactivity_timer.cancel()
            self._inactivity_timer = None
        # Clear pending question state
        self._pending_question_mono = None

    def _create_thread_unlocked(self, user_input: str) -> Thread:
        """Create a new thread from the first user input."""
        summary = user_input.strip()
        if not summary:
            summary = "Nova conversa"
        elif len(summary) > 50:
            summary = summary[:47] + "..."
        return Thread(
            id=uuid.uuid4().hex,
            created_at=time.time(),
            summary=summary,
            status="active",
        )

    def _update_activity_unlocked(self) -> None:
        """Reset the inactivity timer (update last activity time)."""
        self._last_activity_mono = time.monotonic()

    def _update_dominant_intent_unlocked(self) -> None:
        """Update the dominant intent based on turn frequency."""
        if self._active_thread is None or not self._active_thread.turns:
            return
        # Count intent types
        intent_counts: dict[str, int] = {}
        for turn in self._active_thread.turns:
            it = turn.intent_type
            if it and it != "unknown":
                intent_counts[it] = intent_counts.get(it, 0) + 1
        if intent_counts:
            self._active_thread.dominant_intent = max(
                intent_counts,
                key=intent_counts.get,  # type: ignore[arg-type]
            )
