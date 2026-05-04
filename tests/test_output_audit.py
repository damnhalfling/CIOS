"""Output audit test — verifies no technical content leaks through humanization.

Iterates all IntentType values, creates minimal valid intents, executes through
the planner with mocked executor, humanizes output via humanize_result, and
asserts none of the forbidden patterns appear in humanized steps, summary, or error.

Requirements: 8.1, 8.3, 8.5
"""

import re
import contextlib
from unittest.mock import patch, MagicMock

import pytest

from harmoni.core.executor import ExecResult
from harmoni.core.intent_parser import Intent, IntentType
from harmoni.core.humanizer import humanize_result, humanize_error
from harmoni.core.planner import Planner

# Import the shared test helpers from test_property_handlers
from tests.test_property_handlers import (
    HANDLED_INTENT_TYPES,
    _make_mock_executor,
    _make_mock_memory,
    _make_mock_mcp,
)


# ── Forbidden patterns that must NEVER appear in user-facing output ──────

FORBIDDEN_PATTERNS = [
    re.compile(r'/[\w/.-]{3,}'),              # File paths
    re.compile(r'PID \d+'),                   # Process IDs
    re.compile(r'File ".*", line \d+'),        # Tracebacks
    re.compile(r'\b(errno|E[A-Z]{2,})\b'),    # Error codes
    re.compile(r'\w+(Error|Exception):'),      # Python exceptions
    re.compile(r'subprocess\.'),              # Subprocess references
    re.compile(r'Popen|CalledProcessError'),  # Implementation details
    re.compile(r'stderr:'),                   # Raw stderr
]


def _minimal_params_for_audit(intent_type: IntentType) -> dict:
    """Return minimal valid params for each intent type.

    Uses human-friendly values (no file paths) to test that the humanization
    pipeline itself doesn't introduce technical artifacts.
    """
    params_map = {
        IntentType.DEV_START: {"directory": "."},
        IntentType.PROCESS_CONTROL: {"port": 3000, "action": "query"},
        IntentType.LOG_ANALYSIS: {},
        IntentType.FIX_LAST_ERROR: {},
        IntentType.COMMAND_EXEC: {"command": "echo hello"},
        IntentType.STATUS: {},
        IntentType.FILE_ORGANIZE: {"target": "downloads"},
        IntentType.SYSTEM_HEALTH: {},
        IntentType.APP_LAUNCH: {"app": "firefox"},
        IntentType.SESSION: {"action": "lock"},
        IntentType.NETWORK: {"action": "status"},
        IntentType.AUDIO: {"action": "status"},
        IntentType.DISK_ANALYSIS: {"action": "analyze"},
        IntentType.POWER: {"action": "battery_status"},
        IntentType.PACKAGE: {"action": "search", "package": "vim"},
        IntentType.CLIPBOARD: {"action": "current"},
        IntentType.WINDOW: {"action": "list"},
        IntentType.BLUETOOTH: {"action": "status"},
        IntentType.SELF_UPDATE: {"action": "version"},
        IntentType.EXPLORE_SYSTEM: {},
        IntentType.LIST_APPS: {},
        IntentType.WORKFLOW_START: {"project": "my-project"},
        IntentType.CONTINUE_PROJECT: {},
        IntentType.INTENT_MEDIA: {"media_type": "video"},
        IntentType.INTENT_BROWSE: {},
        IntentType.INTENT_WRITE: {"doc_type": "document"},
        IntentType.FILES_SEARCH: {"query": "readme"},
        IntentType.FILES_OPEN: {"query": "readme"},
    }
    return params_map.get(intent_type, {})


def _execute_handler_for_audit(intent_type: IntentType):
    """Execute a handler with mocked dependencies using audit-safe params.

    Reuses the mocking approach from test_property_handlers but with
    params that avoid file paths in output.
    """
    from harmoni.skills.dev_start import ProjectInfo

    executor = _make_mock_executor()
    memory = _make_mock_memory()
    mock_mcp = _make_mock_mcp()

    params = _minimal_params_for_audit(intent_type)
    intent = Intent(
        type=intent_type,
        confidence=0.95,
        params=params,
        raw_input=f"test {intent_type.value}",
    )

    mock_project = ProjectInfo(
        type="node", root="/tmp/test", start_command="npm run dev",
        install_command="npm install", port=3000, package_manager="npm",
    )

    # Mock insight for log analysis
    mock_insight = MagicMock()
    mock_insight.root_cause = "No errors detected"
    mock_insight.suggestion = "System looks healthy"
    mock_insight.error_lines = []

    # Mock file organize result
    mock_org_result = MagicMock()
    mock_org_result.plan_steps = ["Organizing files"]
    mock_org_result.moved = 5
    mock_org_result.errors = []
    mock_org_result.folders_created = ["Images", "Documents"]

    # Mock system health report
    mock_health_report = MagicMock()
    mock_health_report.plan_steps = ["Checking system health"]
    mock_health_report.status = "healthy"
    mock_health_report.summary_lines = ["System is healthy"]

    # Mock session action
    mock_action = MagicMock()
    mock_action.description = "Lock screen"

    # Mock disk report
    mock_disk_report = MagicMock()
    mock_disk_report.plan_steps = ["Analyzing disk"]
    mock_disk_report.percent_used = 55
    mock_disk_report.summary_lines = ["Disk: 55% used"]

    # Mock package result
    mock_pkg_result = MagicMock()
    mock_pkg_result.plan_steps = ["Searching packages"]
    mock_pkg_result.success = True
    mock_pkg_result.message = "Found packages"
    mock_pkg_result.packages = []

    # Mock file search report
    mock_search_report = MagicMock()
    mock_search_report.plan_steps = ["Searching files"]
    mock_search_report.results = []

    patches = {
        "harmoni.core.planner.mcp": mock_mcp,
        "harmoni.core.planner.detect_project": MagicMock(return_value=mock_project),
        "harmoni.core.planner.execute_dev_start": MagicMock(return_value=(
            ["Detecting project", "Starting server", "Server running on port 3000 (PID 42)"],
            [ExecResult(command="npm run dev", returncode=0, stdout="", stderr="", duration=0.5)],
            42,
        )),
        "harmoni.core.planner.find_process_on_port": MagicMock(return_value=None),
        "harmoni.core.planner.kill_process_on_port": MagicMock(return_value=(
            ["Killing process on port 3000"],
            ExecResult(command="kill", returncode=0, stdout="", stderr="", duration=0.1),
        )),
        "harmoni.core.planner.list_listening_ports": MagicMock(return_value=[]),
        "harmoni.core.planner.analyze_text": MagicMock(return_value=mock_insight),
        "harmoni.core.planner.organize_directory": MagicMock(return_value=mock_org_result),
        "harmoni.core.planner.check_system_health": MagicMock(return_value=mock_health_report),
        "harmoni.core.planner.find_app": MagicMock(return_value=None),
        "harmoni.core.planner.launch_app": MagicMock(return_value=(["Launching"], True, "")),
        "harmoni.core.planner.execute_session_action": MagicMock(return_value=(["Locking screen"], True, "")),
        "harmoni.core.planner.get_session_action": MagicMock(return_value=mock_action),
        "harmoni.core.planner.analyze_disk": MagicMock(return_value=mock_disk_report),
        "harmoni.core.planner.clean_safe": MagicMock(return_value=(["Cleaning"], 0, [])),
        "harmoni.core.planner.format_capabilities": MagicMock(return_value=(["Listing capabilities"], "I can help with many things")),
        "harmoni.core.planner.list_installed_apps_grouped": MagicMock(return_value=(["Listing apps"], "Apps: Firefox, Code")),
        "harmoni.core.planner.search_files": MagicMock(return_value=mock_search_report),
        "harmoni.core.planner.find_and_open": MagicMock(return_value=(["Searching for file"], False, "File not found")),
        "harmoni.core.planner._scan_project_dirs": MagicMock(return_value=[]),
        "harmoni.core.planner._find_project": MagicMock(return_value=None),
        "harmoni.core.planner._is_port_in_use": MagicMock(return_value=False),
        "harmoni.core.planner.time.sleep": MagicMock(),
        "os.path.exists": MagicMock(return_value=True),
        "os.path.isdir": MagicMock(return_value=False),
    }

    # Configure skill module mocks
    mock_net = MagicMock()
    mock_net.list_networks.return_value = []
    mock_net.connect.return_value = (["Connecting"], True, "Connected")
    mock_net.disconnect.return_value = (["Disconnecting"], True, "Disconnected")
    patches["harmoni.core.planner.network_skill"] = mock_net

    mock_audio = MagicMock()
    mock_audio.change_volume.return_value = (["Adjusting volume"], True, "Volume: 60%")
    mock_audio.set_volume.return_value = (["Setting volume"], True, "Volume: 50%")
    mock_audio.mute.return_value = (["Muting"], True, "Muted")
    patches["harmoni.core.planner.audio_skill"] = mock_audio

    mock_power = MagicMock()
    mock_power.get_brightness.return_value = 70
    mock_power.change_brightness.return_value = (["Adjusting brightness"], True, "Brightness: 80%")
    mock_power.set_brightness.return_value = (["Setting brightness"], True, "Brightness: 50%")
    mock_power.enable_power_saving.return_value = (["Enabling power saving"], True, "Power saving enabled")
    patches["harmoni.core.planner.power_skill"] = mock_power

    mock_pkg = MagicMock()
    mock_pkg.search_packages.return_value = mock_pkg_result
    mock_pkg.install_package.return_value = mock_pkg_result
    mock_pkg.remove_package.return_value = mock_pkg_result
    mock_pkg.update_lists.return_value = mock_pkg_result
    mock_pkg.upgrade_packages.return_value = mock_pkg_result
    patches["harmoni.core.planner.pkg_skill"] = mock_pkg

    mock_clip = MagicMock()
    mock_cb = MagicMock()
    mock_cb.get_current.return_value = "some text"
    mock_cb.suggest_actions.return_value = []
    mock_cb.get_history.return_value = []
    mock_clip.CognitiveClipboard.return_value = mock_cb
    mock_clip.detect_content_type.return_value = "text"
    patches["harmoni.core.planner.clipboard_skill"] = mock_clip

    mock_window = MagicMock()
    mock_window.list_windows.return_value = []
    mock_window.find_window.return_value = None
    mock_window.get_active_window.return_value = None
    patches["harmoni.core.planner.window_skill"] = mock_window

    mock_bt = MagicMock()
    mock_bt.is_available.return_value = False
    mock_bt.is_powered.return_value = False
    mock_bt.list_connected.return_value = []
    mock_bt.list_paired.return_value = []
    mock_bt.scan.return_value = []
    patches["harmoni.core.planner.bt_skill"] = mock_bt

    mock_update = MagicMock()
    mock_update.get_current_version.return_value = "1.0.0"
    mock_update.check_update_summary.return_value = (["Checking updates"], "Up to date (v1.0.0)")
    patches["harmoni.core.planner.update_skill"] = mock_update

    with contextlib.ExitStack() as stack:
        for target, mock_obj in patches.items():
            stack.enter_context(patch(target, mock_obj))

        planner = Planner(executor=executor, memory=memory)
        result = planner.execute(intent)

    return result


def _check_forbidden(text: str, context: str) -> None:
    """Assert that none of the forbidden patterns appear in the given text."""
    if not text:
        return
    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        assert match is None, (
            f"Forbidden pattern {pattern.pattern!r} found in {context}: "
            f"matched {match.group()!r} in text: {text!r}"
        )


class TestOutputAudit:
    """Output audit: no technical content leaks through humanization pipeline.

    Requirements: 8.1, 8.3, 8.5
    """

    @pytest.mark.parametrize("intent_type", HANDLED_INTENT_TYPES, ids=lambda t: t.value)
    def test_no_forbidden_patterns_in_humanized_output(self, intent_type: IntentType):
        """Execute each handler, humanize the result, and verify no technical
        patterns appear in the user-facing output.
        """
        # Execute handler with mocked dependencies
        result = _execute_handler_for_audit(intent_type)

        # Humanize the output
        humanized_steps, humanized_summary, outcome, voice_mode = humanize_result(result)

        # Check humanized steps
        for i, step in enumerate(humanized_steps):
            _check_forbidden(step, f"step[{i}] for {intent_type.value}")

        # Check humanized summary
        _check_forbidden(humanized_summary, f"summary for {intent_type.value}")

        # Check humanized error (if present)
        if result.error:
            humanized_error = humanize_error(result.error)
            _check_forbidden(humanized_error, f"error for {intent_type.value}")
