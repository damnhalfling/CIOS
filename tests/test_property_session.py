"""Property-based tests for Session Context persistence.

Feature: produto-percebido
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.memory import Memory, SessionContext
from cios.core.intent_parser import Intent, IntentType
from cios.core.executor import Executor, ExecResult


# --- Strategies ---

# Generate non-empty, non-null text without NUL bytes for SQLite compatibility
_safe_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",)),
    min_size=1,
    max_size=200,
)

_project_type = st.sampled_from(["node", "python", "rust", "go", "unknown"])

_session_context = st.builds(
    SessionContext,
    project_name=_safe_text,
    project_path=_safe_text,
    project_type=_project_type,
    editor_command=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",)),
        max_size=100,
    ),
    server_pid=st.one_of(st.none(), st.integers(min_value=0, max_value=2**31 - 1)),
    server_port=st.integers(min_value=0, max_value=65535),
    browser_url=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",)),
        max_size=200,
    ),
    start_command=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters=("\x00",)),
        max_size=200,
    ),
    timestamp=st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False),
)


def _make_memory(db_path: Path) -> Memory:
    """Create a Memory instance backed by the given DB path."""
    with patch("cios.core.config.DB_PATH", db_path), \
         patch("cios.core.config.ensure_dirs", lambda: None):
        return Memory()


# --- Property Tests ---

class TestSessionContextRoundTrip:
    """Property 3: Session context round-trip preserves all fields.

    Feature: produto-percebido, Property 3: Session context round-trip preserves all fields
    """

    @given(ctx=_session_context)
    @settings(max_examples=100, deadline=None)
    def test_round_trip_preserves_all_fields(self, ctx: SessionContext):
        """For any valid SessionContext, saving and retrieving preserves all fields.

        **Validates: Requirements 2.1**
        """
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "prop_session.db"
            mem = _make_memory(db_path)
            try:
                mem.save_session(ctx)
                retrieved = mem.get_session(ctx.project_name)

                assert retrieved is not None, "get_session returned None after save_session"
                assert retrieved.project_name == ctx.project_name
                assert retrieved.project_path == ctx.project_path
                assert retrieved.project_type == ctx.project_type
                assert retrieved.editor_command == ctx.editor_command
                assert retrieved.server_pid == ctx.server_pid
                assert retrieved.server_port == ctx.server_port
                assert retrieved.browser_url == ctx.browser_url
                assert retrieved.start_command == ctx.start_command
                assert retrieved.timestamp == ctx.timestamp
            finally:
                mem.close()


class TestMostRecentProjectSelection:
    """Property 5: Most recent project selection is correct.

    Feature: produto-percebido, Property 5: Most recent project selection is correct
    """

    @given(
        data=st.data(),
        n=st.integers(min_value=1, max_value=15),
    )
    @settings(max_examples=100, deadline=None)
    def test_get_latest_session_returns_max_timestamp(self, data, n: int):
        """For any non-empty list of SessionContext records with distinct timestamps,
        get_latest_session() returns the one with the maximum timestamp.

        **Validates: Requirements 2.4**
        """
        # Generate n distinct timestamps
        timestamps = data.draw(
            st.lists(
                st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False),
                min_size=n,
                max_size=n,
                unique=True,
            )
        )

        # Generate n distinct project names
        project_names = data.draw(
            st.lists(
                _safe_text,
                min_size=n,
                max_size=n,
                unique=True,
            )
        )

        # Build SessionContext records with distinct names and timestamps
        contexts = []
        for i in range(n):
            ctx = data.draw(_session_context)
            # Override project_name and timestamp to ensure uniqueness
            ctx = SessionContext(
                project_name=project_names[i],
                project_path=ctx.project_path,
                project_type=ctx.project_type,
                editor_command=ctx.editor_command,
                server_pid=ctx.server_pid,
                server_port=ctx.server_port,
                browser_url=ctx.browser_url,
                start_command=ctx.start_command,
                timestamp=timestamps[i],
            )
            contexts.append(ctx)

        expected_latest = max(contexts, key=lambda c: c.timestamp)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "prop_latest.db"
            mem = _make_memory(db_path)
            try:
                for ctx in contexts:
                    mem.save_session(ctx)

                latest = mem.get_latest_session()

                assert latest is not None, "get_latest_session returned None for non-empty store"
                assert latest.project_name == expected_latest.project_name, (
                    f"Expected project '{expected_latest.project_name}' "
                    f"(timestamp={expected_latest.timestamp}) but got "
                    f"'{latest.project_name}' (timestamp={latest.timestamp})"
                )
                assert latest.timestamp == expected_latest.timestamp
            finally:
                mem.close()


# --- Strategy for Property 4: Session restoration ---

# Session context with realistic port values (> 0) for restoration testing
_session_with_port = st.builds(
    SessionContext,
    project_name=_safe_text,
    project_path=_safe_text,
    project_type=st.sampled_from(["node", "python"]),
    editor_command=st.just("code"),
    server_pid=st.integers(min_value=1000, max_value=65535),
    server_port=st.integers(min_value=1024, max_value=65535),
    browser_url=st.from_regex(r"http://localhost:\d{4,5}", fullmatch=True),
    start_command=st.just("npm run dev"),
    timestamp=st.floats(min_value=1.0, max_value=1e12, allow_nan=False, allow_infinity=False),
)


class TestSessionRestoration:
    """Property 4: Session restoration produces correct plan based on server state.

    Feature: produto-percebido, Property 4: Session restoration produces correct plan based on server state
    """

    @given(ctx=_session_with_port, server_running=st.booleans())
    @settings(max_examples=100, deadline=None)
    def test_session_restoration_plan_based_on_server_state(
        self, ctx: SessionContext, server_running: bool
    ):
        """For any saved SessionContext and server running state, issuing a
        'continuar' intent produces a plan that:
        (a) skips server start if the server port is already in use,
        (b) includes server start if the port is free,
        (c) always includes editor open at the saved project path, and
        (d) always includes browser open at the saved URL.

        **Validates: Requirements 2.2, 2.3**
        """
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "prop_restore.db"
            mem = _make_memory(db_path)
            try:
                mem.save_session(ctx)

                executor = MagicMock(spec=Executor)

                from cios.core.planner import Planner

                planner = Planner(executor=executor, memory=mem)

                intent = Intent(
                    type=IntentType.CONTINUE_PROJECT,
                    raw_input=f"continuar projeto {ctx.project_name}",
                    params={"project": ctx.project_name},
                    confidence=0.95,
                )

                # Build a fake dev_start result that includes editor + browser steps
                fake_dev_plan = [
                    f"Starting server ({ctx.start_command})",
                    f"Server running on port {ctx.server_port}",
                    f"Editor opened (code)",
                    f"Browser opened (http://localhost:{ctx.server_port})",
                    "Session saved",
                ]
                fake_dev_results = [
                    ExecResult(
                        command=ctx.start_command,
                        returncode=0,
                        stdout="ok",
                        stderr="",
                        duration=0.1,
                    )
                ]

                with patch("cios.core.handlers.dev._is_port_in_use", return_value=server_running), \
                     patch("cios.core.handlers.dev._detect_editor", return_value="code"), \
                     patch("cios.core.handlers.dev._open_editor") as mock_editor, \
                     patch("cios.core.handlers.dev._open_browser") as mock_browser, \
                     patch("os.path.exists", return_value=True), \
                     patch("cios.core.handlers.dev.detect_project") as mock_detect, \
                     patch("cios.core.handlers.dev.execute_dev_start", return_value=(fake_dev_plan, fake_dev_results, 12345)) as mock_dev_start:

                    result = planner._handle_continue_project(intent)

                plan_text = " ".join(result.plan_steps).lower()

                if server_running:
                    # (a) Server running → skip start
                    assert "already running" in plan_text, (
                        f"Expected 'already running' in plan when server is up, "
                        f"got: {result.plan_steps}"
                    )
                    # Should NOT have called execute_dev_start
                    mock_dev_start.assert_not_called()
                else:
                    # (b) Server not running → include start
                    assert "starting" in plan_text or "server" in plan_text, (
                        f"Expected server start step in plan when server is down, "
                        f"got: {result.plan_steps}"
                    )
                    # Should have called execute_dev_start
                    mock_dev_start.assert_called_once()

                # (c) Always includes editor open
                assert "editor" in plan_text, (
                    f"Expected editor step in plan, got: {result.plan_steps}"
                )

                # (d) Always includes browser open
                assert "browser" in plan_text, (
                    f"Expected browser step in plan, got: {result.plan_steps}"
                )

                # Outcome should be success
                assert result.outcome == "success", (
                    f"Expected success outcome, got: {result.outcome} "
                    f"(error: {result.error})"
                )
            finally:
                mem.close()
