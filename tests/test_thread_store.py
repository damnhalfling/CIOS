"""Unit tests for ThreadStore cloud sync behavior.

Tests that sync is not triggered when user is not logged in,
sync with mocked HTTP endpoint (success case), and sync failure
silently caught (network error, timeout, HTTP 500).

Requirements: 8.1, 8.2, 8.4, 8.5
"""

import json
import threading
import time
import urllib.error
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from cios.core.thread_manager import (
    ConversationTurn,
    Thread,
    ThreadStore,
)


@pytest.fixture
def store(tmp_path):
    """Provide a ThreadStore backed by a temporary database."""
    db_path = tmp_path / "test_memory.db"
    return ThreadStore(db_path=db_path)


@pytest.fixture
def sample_thread():
    """Provide a sample completed thread for sync tests."""
    return Thread(
        id="abc123",
        created_at=1700000000.0,
        closed_at=1700000180.0,
        summary="Connect to WiFi",
        status="completed",
        turns=[
            ConversationTurn(
                user_input="connect to wifi",
                intent_type="network",
                params={"ssid": "secret_network", "password": "hunter2"},
                result_summary="Which network?",
                outcome="success",
                timestamp=1700000000.0,
            ),
            ConversationTurn(
                user_input="home_network",
                intent_type="network",
                params={},
                result_summary="Connected to home_network",
                outcome="success",
                timestamp=1700000060.0,
            ),
        ],
        dominant_intent="network",
        outcome="success",
    )


def _wait_for_sync_thread(timeout=2.0):
    """Wait for the daemon sync thread to complete."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        sync_threads = [
            t for t in threading.enumerate() if t.daemon and t.is_alive() and t.name != "MainThread"
        ]
        if not sync_threads:
            return
        time.sleep(0.05)


# ═══════════════════════════════════════════════════════════════════════════
#  Sync Not Triggered When User Is Not Logged In
# ═══════════════════════════════════════════════════════════════════════════


class TestSyncNotTriggeredWhenNotLoggedIn:
    """Validates: Requirements 8.1, 8.2"""

    def test_sync_skipped_when_not_logged_in(self, store, sample_thread):
        """sync_to_cloud should return immediately without HTTP call when not logged in."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=False)

        store.save_thread(sample_thread)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch("urllib.request.urlopen") as mock_urlopen,
        ):
            store.sync_to_cloud(sample_thread)
            # Give a moment for any thread to start (it shouldn't)
            time.sleep(0.1)
            # urlopen should never be called
            mock_urlopen.assert_not_called()

    def test_sync_skipped_when_no_token(self, store, sample_thread):
        """sync_to_cloud should return immediately when logged in but token is empty."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        mock_user = MagicMock()
        mock_user.token = ""
        type(mock_intelligence).user = PropertyMock(return_value=mock_user)

        store.save_thread(sample_thread)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch("urllib.request.urlopen") as mock_urlopen,
        ):
            store.sync_to_cloud(sample_thread)
            time.sleep(0.1)
            mock_urlopen.assert_not_called()

    def test_sync_skipped_when_user_is_none(self, store, sample_thread):
        """sync_to_cloud should return immediately when user object is None."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        type(mock_intelligence).user = PropertyMock(return_value=None)

        store.save_thread(sample_thread)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch("urllib.request.urlopen") as mock_urlopen,
        ):
            store.sync_to_cloud(sample_thread)
            time.sleep(0.1)
            mock_urlopen.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
#  Sync Success Case With Mocked HTTP Endpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestSyncSuccess:
    """Validates: Requirements 8.1, 8.5"""

    def test_sync_success_marks_synced_1(self, store, sample_thread):
        """On successful HTTP POST, thread should be marked synced=1 in DB."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        mock_user = MagicMock()
        mock_user.token = "test-token-abc123"
        type(mock_intelligence).user = PropertyMock(return_value=mock_user)

        # Save thread first
        store.save_thread(sample_thread)

        # Mock urlopen to return a successful response
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen,
        ):
            store.sync_to_cloud(sample_thread)
            _wait_for_sync_thread()

            # Verify urlopen was called
            mock_urlopen.assert_called_once()

            # Verify the request was constructed correctly
            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            assert request.full_url == "https://api.cios-ia.com/threads"
            assert request.get_header("Authorization") == "Bearer test-token-abc123"
            assert request.get_header("Content-type") == "application/json"
            assert request.get_method() == "POST"

        # Verify synced=1 in database
        row = store._conn.execute(
            "SELECT synced FROM threads WHERE id = ?", (sample_thread.id,)
        ).fetchone()
        assert row is not None
        assert row["synced"] == 1

    def test_sync_sends_correct_payload(self, store, sample_thread):
        """The sync payload should contain only allowed fields (no params/credentials)."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        mock_user = MagicMock()
        mock_user.token = "test-token"
        type(mock_intelligence).user = PropertyMock(return_value=mock_user)

        store.save_thread(sample_thread)

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen,
        ):
            store.sync_to_cloud(sample_thread)
            _wait_for_sync_thread()

            # Extract the payload that was sent
            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            payload = json.loads(request.data.decode("utf-8"))

            # Verify payload structure
            assert payload["thread_id"] == "abc123"
            assert payload["created_at"] == 1700000000.0
            assert payload["closed_at"] == 1700000180.0
            assert payload["summary"] == "Connect to WiFi"
            assert payload["outcome"] == "success"
            assert len(payload["turns"]) == 2

            # Verify turns don't contain params
            for turn in payload["turns"]:
                assert "params" not in turn
                assert "user_input" in turn
                assert "intent_type" in turn
                assert "result_summary" in turn
                assert "outcome" in turn
                assert "timestamp" in turn

    def test_sync_runs_in_daemon_thread(self, store, sample_thread):
        """sync_to_cloud should not block — it runs in a daemon thread."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        mock_user = MagicMock()
        mock_user.token = "test-token"
        type(mock_intelligence).user = PropertyMock(return_value=mock_user)

        store.save_thread(sample_thread)

        # Use an event to verify the sync runs asynchronously
        sync_started = threading.Event()
        sync_can_proceed = threading.Event()

        def slow_urlopen(req, **kwargs):
            sync_started.set()
            sync_can_proceed.wait(timeout=5)
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"status": "ok"}'
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch("urllib.request.urlopen", side_effect=slow_urlopen),
        ):
            # sync_to_cloud should return immediately (non-blocking)
            start = time.time()
            store.sync_to_cloud(sample_thread)
            elapsed = time.time() - start

            # Should return almost immediately (< 0.5s)
            assert elapsed < 0.5

            # The sync thread should have started
            assert sync_started.wait(timeout=2)

            # Let it finish
            sync_can_proceed.set()
            _wait_for_sync_thread()


# ═══════════════════════════════════════════════════════════════════════════
#  Sync Failure Silently Caught
# ═══════════════════════════════════════════════════════════════════════════


class TestSyncFailureSilentlyCaught:
    """Validates: Requirements 8.4, 8.5"""

    def test_sync_network_error_marks_synced_0(self, store, sample_thread):
        """URLError (network error) should be caught silently, synced=0."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        mock_user = MagicMock()
        mock_user.token = "test-token"
        type(mock_intelligence).user = PropertyMock(return_value=mock_user)

        store.save_thread(sample_thread)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("Network unreachable"),
            ),
        ):
            store.sync_to_cloud(sample_thread)
            _wait_for_sync_thread()

        # Verify synced=0 in database
        row = store._conn.execute(
            "SELECT synced FROM threads WHERE id = ?", (sample_thread.id,)
        ).fetchone()
        assert row is not None
        assert row["synced"] == 0

    def test_sync_http_500_marks_synced_0(self, store, sample_thread):
        """HTTP 500 error should be caught silently, synced=0."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        mock_user = MagicMock()
        mock_user.token = "test-token"
        type(mock_intelligence).user = PropertyMock(return_value=mock_user)

        store.save_thread(sample_thread)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.HTTPError(
                    url="https://api.cios-ia.com/threads",
                    code=500,
                    msg="Internal Server Error",
                    hdrs={},
                    fp=None,
                ),
            ),
        ):
            store.sync_to_cloud(sample_thread)
            _wait_for_sync_thread()

        row = store._conn.execute(
            "SELECT synced FROM threads WHERE id = ?", (sample_thread.id,)
        ).fetchone()
        assert row is not None
        assert row["synced"] == 0

    def test_sync_timeout_marks_synced_0(self, store, sample_thread):
        """Timeout exception should be caught silently, synced=0."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        mock_user = MagicMock()
        mock_user.token = "test-token"
        type(mock_intelligence).user = PropertyMock(return_value=mock_user)

        store.save_thread(sample_thread)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch(
                "urllib.request.urlopen",
                side_effect=TimeoutError("Connection timed out"),
            ),
        ):
            store.sync_to_cloud(sample_thread)
            _wait_for_sync_thread()

        row = store._conn.execute(
            "SELECT synced FROM threads WHERE id = ?", (sample_thread.id,)
        ).fetchone()
        assert row is not None
        assert row["synced"] == 0

    def test_sync_generic_exception_marks_synced_0(self, store, sample_thread):
        """Any generic exception should be caught silently, synced=0."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        mock_user = MagicMock()
        mock_user.token = "test-token"
        type(mock_intelligence).user = PropertyMock(return_value=mock_user)

        store.save_thread(sample_thread)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch(
                "urllib.request.urlopen",
                side_effect=RuntimeError("Unexpected error"),
            ),
        ):
            store.sync_to_cloud(sample_thread)
            _wait_for_sync_thread()

        row = store._conn.execute(
            "SELECT synced FROM threads WHERE id = ?", (sample_thread.id,)
        ).fetchone()
        assert row is not None
        assert row["synced"] == 0

    def test_sync_failure_does_not_propagate_exception(self, store, sample_thread):
        """Sync failure should never propagate an exception to the caller."""
        mock_intelligence = MagicMock()
        type(mock_intelligence).is_logged_in = PropertyMock(return_value=True)
        mock_user = MagicMock()
        mock_user.token = "test-token"
        type(mock_intelligence).user = PropertyMock(return_value=mock_user)

        store.save_thread(sample_thread)

        with (
            patch("cios.core.intelligence.intelligence", mock_intelligence),
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("DNS resolution failed"),
            ),
        ):
            # This should NOT raise any exception
            try:
                store.sync_to_cloud(sample_thread)
                _wait_for_sync_thread()
            except Exception as e:
                pytest.fail(f"sync_to_cloud propagated an exception: {e}")
