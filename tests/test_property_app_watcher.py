"""Property-based tests for App Watcher — thread safety and cache invalidation.

Feature: app-watcher
"""

import concurrent.futures
import threading
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.skills.app_launcher import (
    AppInfo,
    find_app,
    get_installed_apps,
    invalidate_app_cache,
)

# --- Strategies ---

# Generate a list of AppInfo objects to use as controlled cache data
_app_name = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz"),
    min_size=1,
    max_size=12,
)

_app_info = st.builds(
    AppInfo,
    name=_app_name,
    exec_command=_app_name.map(lambda n: f"/usr/bin/{n}"),
    desktop_file=_app_name.map(lambda n: f"/usr/share/applications/{n}.desktop"),
    keywords=st.just([]),
    icon=st.just(""),
)

_app_list = st.lists(_app_info, min_size=1, max_size=10)

# Generate number of concurrent reader threads and invalidation threads
_num_readers = st.integers(min_value=2, max_value=8)
_num_invalidators = st.integers(min_value=1, max_value=4)

# Operations: 'read_all' calls get_installed_apps(), 'find' calls find_app(), 'invalidate' calls invalidate_app_cache()
_operation = st.sampled_from(["read_all", "find", "invalidate"])
_operation_sequence = st.lists(_operation, min_size=4, max_size=20)


def _reset_cache():
    """Reset the app_launcher module-level cache state for test isolation."""
    import cios.skills.app_launcher as al

    with al._cache_lock:
        al._app_cache = []
        al._cache_loaded = False
        al._cache_dirty = False


# --- Property Tests ---


class TestThreadSafetyConcurrentReads:
    """Property 5: Thread safety nas leituras concorrentes durante reconstrução.

    Feature: app-watcher, Property 5: Thread safety nas leituras concorrentes
    """

    @given(
        apps=_app_list,
        num_readers=_num_readers,
        num_invalidators=_num_invalidators,
    )
    @settings(max_examples=100, deadline=None)
    def test_concurrent_reads_and_invalidations_no_exceptions(
        self,
        apps: list[AppInfo],
        num_readers: int,
        num_invalidators: int,
    ):
        """For any combination of threads doing reads (find_app(), get_installed_apps())
        and invalidations (invalidate_app_cache()) concurrently, no read should throw
        an exception or return partially constructed data.

        **Validates: Requirements 3.3, 5.1, 5.2**
        """
        _reset_cache()

        with patch(
            "cios.skills.app_launcher._scan_desktop_files",
            return_value=list(apps),
        ):
            errors: list[Exception] = []
            results: list[object] = []
            results_lock = threading.Lock()

            def reader_task():
                """Perform a get_installed_apps() call and validate result."""
                try:
                    result = get_installed_apps()
                    # Result must never be None
                    assert result is not None, "get_installed_apps() returned None"
                    # Result must be a list
                    assert isinstance(result, list), (
                        f"get_installed_apps() returned {type(result)}, expected list"
                    )
                    # Every element must be a complete AppInfo (not partially constructed)
                    for item in result:
                        assert isinstance(item, AppInfo), (
                            f"Expected AppInfo, got {type(item)}"
                        )
                        assert item.name is not None, "AppInfo.name is None"
                        assert item.exec_command is not None, "AppInfo.exec_command is None"
                    with results_lock:
                        results.append(result)
                except Exception as e:
                    with results_lock:
                        errors.append(e)

            def find_task():
                """Perform a find_app() call and validate result."""
                try:
                    # Use the first app name from our test data
                    query = apps[0].name if apps else "nonexistent"
                    result = find_app(query)
                    # find_app can return None (no match) but should never raise
                    if result is not None:
                        assert isinstance(result, AppInfo), (
                            f"find_app() returned {type(result)}, expected AppInfo or None"
                        )
                        assert result.name is not None, "AppInfo.name is None from find_app()"
                    with results_lock:
                        results.append(result)
                except Exception as e:
                    with results_lock:
                        errors.append(e)

            def invalidator_task():
                """Perform invalidate_app_cache() calls."""
                try:
                    invalidate_app_cache()
                except Exception as e:
                    with results_lock:
                        errors.append(e)

            # Run concurrent operations
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=num_readers + num_invalidators
            ) as executor:
                futures = []

                # Submit reader threads
                for _ in range(num_readers):
                    futures.append(executor.submit(reader_task))

                # Submit find threads (half of readers do find_app instead)
                for _ in range(max(1, num_readers // 2)):
                    futures.append(executor.submit(find_task))

                # Submit invalidation threads
                for _ in range(num_invalidators):
                    futures.append(executor.submit(invalidator_task))

                # Wait for all to complete
                concurrent.futures.wait(futures)

            # No exceptions should have been raised in any thread
            assert len(errors) == 0, (
                f"Thread safety violated: {len(errors)} exception(s) raised: "
                f"{[str(e) for e in errors]}"
            )

    @given(
        apps=_app_list,
        operations=_operation_sequence,
    )
    @settings(max_examples=100, deadline=None)
    def test_interleaved_operations_return_valid_data(
        self,
        apps: list[AppInfo],
        operations: list[str],
    ):
        """For any interleaved sequence of read and invalidation operations executed
        concurrently, get_installed_apps() must always return a complete, valid list
        (never partial data).

        **Validates: Requirements 3.3, 5.1, 5.2**
        """
        _reset_cache()

        with patch(
            "cios.skills.app_launcher._scan_desktop_files",
            return_value=list(apps),
        ):
            errors: list[Exception] = []
            invalid_results: list[str] = []
            lock = threading.Lock()

            def execute_op(op: str):
                try:
                    if op == "read_all":
                        result = get_installed_apps()
                        assert result is not None, "get_installed_apps() returned None"
                        assert isinstance(result, list), (
                            f"Expected list, got {type(result)}"
                        )
                        # Validate list is not partially constructed:
                        # length must be 0 (not yet loaded) or equal to len(apps)
                        if len(result) > 0:
                            for item in result:
                                assert isinstance(item, AppInfo), (
                                    f"Partial data: got {type(item)} in list"
                                )
                    elif op == "find":
                        query = apps[0].name if apps else "x"
                        result = find_app(query)
                        # None is acceptable (not found), but should not raise
                        if result is not None:
                            assert isinstance(result, AppInfo)
                    elif op == "invalidate":
                        invalidate_app_cache()
                except AssertionError as e:
                    with lock:
                        invalid_results.append(str(e))
                except Exception as e:
                    with lock:
                        errors.append(e)

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(len(operations), 8)
            ) as executor:
                futures = [executor.submit(execute_op, op) for op in operations]
                concurrent.futures.wait(futures)

            assert len(errors) == 0, (
                f"Exceptions during concurrent operations: {[str(e) for e in errors]}"
            )
            assert len(invalid_results) == 0, (
                f"Invalid/partial data returned: {invalid_results}"
            )



# --- Property 1: Filtro de extensão .desktop ---


class TestDesktopExtensionFilter:
    """Property 1: Filtro de extensão .desktop.

    Feature: app-watcher, Property 1: Filtro de extensão .desktop
    """

    @given(filename=st.text(min_size=0, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_filter_rejects_non_desktop_and_accepts_desktop(self, filename: str):
        """For any randomly generated filename, _on_event must call _reset_debounce
        if and only if the filename ends with '.desktop'.

        **Validates: Requirements 1.5**
        """
        from unittest.mock import MagicMock

        from cios.core.app_watcher import AppWatcher

        watcher = AppWatcher()
        watcher._reset_debounce = MagicMock()

        watcher._on_event(filename)

        if filename.endswith(".desktop"):
            assert watcher._reset_debounce.called, (
                f"Expected _reset_debounce to be called for '{filename}'"
            )
        else:
            assert not watcher._reset_debounce.called, (
                f"Expected _reset_debounce NOT to be called for '{filename}'"
            )

    @given(base=st.text(min_size=0, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_filter_always_accepts_desktop_suffix(self, base: str):
        """For any text with '.desktop' appended, _on_event must always trigger
        _reset_debounce.

        **Validates: Requirements 1.5**
        """
        from unittest.mock import MagicMock

        from cios.core.app_watcher import AppWatcher

        watcher = AppWatcher()
        watcher._reset_debounce = MagicMock()

        filename = base + ".desktop"
        watcher._on_event(filename)

        assert watcher._reset_debounce.called, (
            f"Expected _reset_debounce to be called for '{filename}'"
        )


# --- Property 2: Resiliência a diretórios inexistentes ---

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from cios.core.app_watcher import AppWatcher


class TestDirectoryResilience:
    """Property 2: Resiliência a diretórios inexistentes.

    Feature: app-watcher, Property 2: Resiliência a diretórios inexistentes
    """

    @given(dir_exists=st.lists(st.booleans(), min_size=2, max_size=2))
    @settings(max_examples=100, deadline=None)
    def test_start_resilient_to_nonexistent_directories(
        self,
        dir_exists: list[bool],
    ):
        """For any subset of monitored directories where some don't exist,
        AppWatcher should initialize without throwing an exception and should
        monitor exactly the directories that exist.

        **Validates: Requirements 1.4**
        """
        # Create a temporary directory structure
        tmp_dir = tempfile.mkdtemp()
        tmp_path = Path(tmp_dir)

        dirs = [tmp_path / "dir1", tmp_path / "dir2"]

        # Create only the directories marked True
        for i, exists in enumerate(dir_exists):
            if exists:
                dirs[i].mkdir(parents=True, exist_ok=True)

        # Track which directories get watches added
        watched_dirs: list[str] = []

        def fake_inotify_add_watch(fd: int, path: str, mask: int) -> int:
            watched_dirs.append(path)
            return len(watched_dirs)  # Return a fake wd

        watcher = AppWatcher()

        with (
            patch.object(AppWatcher, "WATCHED_DIRS", dirs),
            patch(
                "cios.core.app_watcher._inotify_init", return_value=999
            ),
            patch(
                "cios.core.app_watcher._inotify_add_watch",
                side_effect=fake_inotify_add_watch,
            ),
            patch("os.close"),
            patch("select.select", return_value=([], [], [])),
        ):
            # start() must NOT raise an exception regardless of which dirs exist
            watcher.start()

            # Verify watches were added only for existing directories
            expected_watched = [
                str(dirs[i]) for i, exists in enumerate(dir_exists) if exists
            ]
            assert sorted(watched_dirs) == sorted(expected_watched), (
                f"Expected watches on {expected_watched}, got {watched_dirs}. "
                f"dir_exists={dir_exists}"
            )

            # Cleanup
            watcher.stop()

        # Cleanup temp directory
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


# --- Property 3: Debounce correto ---

import time

from cios.core.app_watcher import AppWatcher


class TestDebounceCorrectness:
    """Property 3: Debounce correto — único rescan após período de silêncio.

    Feature: app-watcher, Property 3: Debounce correto
    """

    @given(
        intervals=st.lists(
            st.floats(min_value=0.001, max_value=0.05),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_single_rescan_after_burst_of_events(
        self,
        intervals: list[float],
    ):
        """For any sequence of N events (N >= 1) where all occur with less than
        2 second intervals between them, followed by at least 2 seconds of silence,
        the number of rescans triggered must be exactly 1.

        **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
        """
        # Use a very short debounce to keep tests fast
        original_debounce = AppWatcher.DEBOUNCE_SECONDS
        AppWatcher.DEBOUNCE_SECONDS = 0.1

        try:
            watcher = AppWatcher.__new__(AppWatcher)
            # Manually initialize the instance without starting inotify
            watcher._inotify_fd = -1
            watcher._watch_descriptors = {}
            watcher._running = False
            watcher._thread = None
            watcher._debounce_timer = None
            watcher._debounce_lock = threading.Lock()

            with patch(
                "cios.skills.app_launcher.invalidate_app_cache"
            ) as mock_invalidate:
                # Fire events at each interval
                for interval in intervals:
                    watcher._on_event("test.desktop")
                    time.sleep(interval)

                # Wait for debounce to expire (debounce + epsilon)
                time.sleep(0.15)

                # Exactly 1 rescan should have been triggered
                assert mock_invalidate.call_count == 1, (
                    f"Expected exactly 1 call to invalidate_app_cache after burst of "
                    f"{len(intervals)} events, but got {mock_invalidate.call_count}"
                )
        finally:
            # Restore original debounce value
            AppWatcher.DEBOUNCE_SECONDS = original_debounce
            # Clean up any lingering timer
            if watcher._debounce_timer is not None:
                watcher._debounce_timer.cancel()


# --- Property 4: Round-trip de invalidação do cache ---


class TestCacheInvalidationRoundTrip:
    """Property 4: Round-trip de invalidação do cache.

    Feature: app-watcher, Property 4: Round-trip de invalidação do cache
    """

    @given(
        apps_a=_app_list,
        apps_b=_app_list,
    )
    @settings(max_examples=100, deadline=None)
    def test_after_invalidation_next_read_returns_fresh_data(
        self,
        apps_a: list[AppInfo],
        apps_b: list[AppInfo],
    ):
        """After populating cache with set A, calling invalidate_app_cache(),
        and changing the underlying data to set B, get_installed_apps() must
        return set B (not stale set A).

        **Validates: Requirements 3.2**
        """
        _reset_cache()

        with patch(
            "cios.skills.app_launcher._scan_desktop_files",
            return_value=list(apps_a),
        ) as mock_scan:
            # Step 1: Populate cache with set A
            result_a = get_installed_apps()
            assert result_a == apps_a

            # Step 2: Invalidate the cache
            invalidate_app_cache()

            # Step 3: Change mock to return set B (simulates disk change)
            mock_scan.return_value = list(apps_b)

            # Step 4: Next read must return set B (fresh from disk)
            result_b = get_installed_apps()
            assert result_b == apps_b, (
                f"Expected fresh data (set B) after invalidation, got stale data. "
                f"Set A had {len(apps_a)} items, Set B has {len(apps_b)} items, "
                f"got {len(result_b)} items"
            )

            # Step 5: Verify _scan_desktop_files was called exactly 2 times
            # (initial load + post-invalidation rebuild)
            assert mock_scan.call_count == 2, (
                f"Expected _scan_desktop_files to be called exactly 2 times "
                f"(initial + rebuild), but was called {mock_scan.call_count} times"
            )
