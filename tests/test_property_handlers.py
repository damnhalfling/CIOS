"""Property-based tests for all skill handlers feedback.

Feature: produto-percebido
Property 12: All skill handlers produce at least one feedback message

Validates: Requirements 7.4
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.executor import ExecResult, Executor
from cios.core.intent_parser import Intent, IntentType
from cios.core.memory import Memory
from cios.core.planner import Planner, PlanResult

# ── All IntentType values that have registered handlers in the Planner ───

HANDLED_INTENT_TYPES = [
    IntentType.DEV_START,
    IntentType.PROCESS_CONTROL,
    IntentType.LOG_ANALYSIS,
    IntentType.FIX_LAST_ERROR,
    IntentType.COMMAND_EXEC,
    IntentType.STATUS,
    IntentType.FILE_ORGANIZE,
    IntentType.SYSTEM_HEALTH,
    IntentType.APP_LAUNCH,
    IntentType.SESSION,
    IntentType.NETWORK,
    IntentType.AUDIO,
    IntentType.DISK_ANALYSIS,
    IntentType.POWER,
    IntentType.PACKAGE,
    IntentType.CLIPBOARD,
    IntentType.WINDOW,
    IntentType.BLUETOOTH,
    IntentType.SELF_UPDATE,
    IntentType.EXPLORE_SYSTEM,
    IntentType.LIST_APPS,
    IntentType.WORKFLOW_START,
    IntentType.CONTINUE_PROJECT,
    IntentType.INTENT_MEDIA,
    IntentType.INTENT_BROWSE,
    IntentType.INTENT_WRITE,
    IntentType.FILES_SEARCH,
    IntentType.FILES_OPEN,
]


def _minimal_params_for(intent_type: IntentType) -> dict:
    """Return minimal valid params for each intent type so the handler
    can execute without crashing due to missing required params.
    """
    params_map = {
        IntentType.DEV_START: {"directory": "/tmp/fake-project"},
        IntentType.PROCESS_CONTROL: {"port": 3000, "action": "query"},
        IntentType.LOG_ANALYSIS: {},
        IntentType.FIX_LAST_ERROR: {},
        IntentType.COMMAND_EXEC: {"command": "echo hello"},
        IntentType.STATUS: {},
        IntentType.FILE_ORGANIZE: {"target": "/tmp/fake-dir"},
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
        IntentType.FILES_OPEN: {"query": "readme.md"},
    }
    return params_map.get(intent_type, {})


def _make_mock_executor() -> MagicMock:
    """Create a mock Executor that returns successful results."""
    executor = MagicMock(spec=Executor)
    executor.run.return_value = ExecResult(
        command="mock",
        returncode=0,
        stdout="ok",
        stderr="",
        duration=0.1,
    )
    mock_proc = MagicMock()
    mock_proc.pid = 42
    mock_proc.poll.return_value = None
    executor.run_background.return_value = mock_proc
    executor.kill_by_port.return_value = ExecResult(
        command="kill",
        returncode=0,
        stdout="",
        stderr="",
        duration=0.1,
    )
    return executor


def _make_mock_memory() -> MagicMock:
    """Create a mock Memory that returns safe defaults."""
    memory = MagicMock(spec=Memory)
    memory.last_failure.return_value = None
    memory.recent.return_value = []
    memory.get_session.return_value = None
    memory.get_latest_session.return_value = None
    memory.list_sessions.return_value = []
    memory.store.return_value = None
    memory.save_session.return_value = None
    return memory


def _make_mock_mcp():
    """Create a mock MCP context with safe default states."""
    mock_mcp = MagicMock()

    # WifiState
    mock_mcp.wifi.connected = False
    mock_mcp.wifi.ssid = ""
    mock_mcp.wifi.signal = 0
    mock_mcp.wifi.ip = ""

    # AudioState
    mock_mcp.audio.volume = 50
    mock_mcp.audio.muted = False

    # BatteryState
    mock_mcp.battery.present = True
    mock_mcp.battery.percent = 75
    mock_mcp.battery.charging = False
    mock_mcp.battery.time_remaining = "2h30m"

    # SystemState
    mock_mcp.system.cpu_percent = 15.0
    mock_mcp.system.cpu_cores = 4
    mock_mcp.system.mem_percent = 45.0
    mock_mcp.system.mem_used_gb = 3.6
    mock_mcp.system.mem_total_gb = 8.0
    mock_mcp.system.disk_percent = 55.0
    mock_mcp.system.disk_free_gb = 100.0

    # BluetoothState
    mock_mcp.bluetooth.available = False
    mock_mcp.bluetooth.powered = False
    mock_mcp.bluetooth.connected_devices = []

    # Known networks
    mock_mcp.known_networks = []

    # Snapshot
    from cios.core.mcp import (
        AudioState,
        BatteryState,
        BluetoothState,
        ContextSnapshot,
        SystemState,
        WifiState,
    )

    mock_mcp.snapshot.return_value = ContextSnapshot(
        wifi=WifiState(connected=False),
        audio=AudioState(volume=50, muted=False),
        battery=BatteryState(present=True, percent=75),
        system=SystemState(
            cpu_percent=15.0,
            cpu_cores=4,
            mem_percent=45.0,
            mem_used_gb=3.6,
            mem_total_gb=8.0,
            disk_percent=55.0,
            disk_free_gb=100.0,
        ),
        bluetooth=BluetoothState(available=False, powered=False),
    )

    return mock_mcp


def _execute_handler(intent_type: IntentType) -> PlanResult:
    """Execute a handler for the given intent type with fully mocked dependencies."""
    import contextlib

    executor = _make_mock_executor()
    memory = _make_mock_memory()
    mock_mcp = _make_mock_mcp()

    params = _minimal_params_for(intent_type)
    intent = Intent(
        type=intent_type,
        confidence=0.95,
        params=params,
        raw_input=f"test {intent_type.value}",
    )

    from cios.skills.dev_start import ProjectInfo

    mock_project = ProjectInfo(
        type="node",
        root="/tmp/test",
        start_command="npm run dev",
        install_command="npm install",
        port=3000,
        package_manager="npm",
    )

    # Mock insight for log analysis
    mock_insight = MagicMock()
    mock_insight.root_cause = "No errors detected"
    mock_insight.suggestion = "System looks healthy"
    mock_insight.error_lines = []

    # Mock file organize result
    mock_org_result = MagicMock()
    mock_org_result.plan_steps = ["Organizing files"]
    mock_org_result.moved = 0
    mock_org_result.errors = []
    mock_org_result.folders_created = []

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
        "cios.core.handlers.network.mcp": mock_mcp,
        "cios.core.handlers.audio.mcp": mock_mcp,
        "cios.core.handlers.system.mcp": mock_mcp,
        "cios.core.planner.mcp": mock_mcp,
        "cios.core.handlers.dev.detect_project": MagicMock(return_value=mock_project),
        "cios.core.handlers.dev.execute_dev_start": MagicMock(
            return_value=(
                ["Detecting project", "Starting server", "Server running on :3000"],
                [
                    ExecResult(
                        command="npm run dev", returncode=0, stdout="", stderr="", duration=0.5
                    )
                ],
                42,
            )
        ),
        "cios.core.handlers.process.find_process_on_port": MagicMock(return_value=None),
        "cios.core.handlers.process.kill_process_on_port": MagicMock(
            return_value=(
                ["Killing process on port 3000"],
                ExecResult(command="kill", returncode=0, stdout="", stderr="", duration=0.1),
            )
        ),
        "cios.core.handlers.process.list_listening_ports": MagicMock(return_value=[]),
        "cios.core.handlers.logs.analyze_text": MagicMock(return_value=mock_insight),
        "cios.core.handlers.dev.analyze_text": MagicMock(return_value=mock_insight),
        "cios.core.handlers.files.organize_directory": MagicMock(return_value=mock_org_result),
        "cios.core.handlers.system.check_system_health": MagicMock(return_value=mock_health_report),
        "cios.core.handlers.apps.find_app": MagicMock(return_value=None),
        "cios.core.handlers.apps.launch_app": MagicMock(return_value=(["Launching"], True, "")),
        "cios.core.handlers.dev.find_app": MagicMock(return_value=None),
        "cios.core.handlers.media.find_app": MagicMock(return_value=None),
        "cios.core.handlers.media.launch_app": MagicMock(return_value=(["Launching"], True, "")),
        "cios.core.handlers.system.execute_session_action": MagicMock(
            return_value=(["Locking screen"], True, "")
        ),
        "cios.core.handlers.system.get_session_action": MagicMock(return_value=mock_action),
        "cios.core.handlers.disk.analyze_disk": MagicMock(return_value=mock_disk_report),
        "cios.core.handlers.disk.clean_safe": MagicMock(return_value=(["Cleaning"], 0, [])),
        "cios.core.handlers.apps.format_capabilities": MagicMock(
            return_value=(["Listing capabilities"], "I can help with many things")
        ),
        "cios.core.handlers.apps.list_installed_apps_grouped": MagicMock(
            return_value=(["Listing apps"], "Apps: Firefox, Code")
        ),
        "cios.core.handlers.files.search_files": MagicMock(return_value=mock_search_report),
        "cios.core.handlers.files.find_and_open": MagicMock(
            return_value=(["Searching for file"], False, "File not found")
        ),
        "cios.core.handlers.dev._scan_project_dirs": MagicMock(return_value=[]),
        "cios.core.handlers.dev._find_project": MagicMock(return_value=None),
        "cios.core.handlers.dev._is_port_in_use": MagicMock(return_value=False),
        "cios.core.handlers.dev.time.sleep": MagicMock(),
        "cios.core.handlers.logs.time.sleep": MagicMock(),
        "os.path.exists": MagicMock(return_value=True),
        "os.path.isdir": MagicMock(return_value=False),
    }

    # Configure skill module mocks
    mock_net = MagicMock()
    mock_net.list_networks.return_value = []
    mock_net.connect.return_value = (["Connecting"], True, "Connected")
    mock_net.disconnect.return_value = (["Disconnecting"], True, "Disconnected")
    patches["cios.core.handlers.network.network_skill"] = mock_net

    mock_audio = MagicMock()
    mock_audio.change_volume.return_value = (["Adjusting volume"], True, "Volume: 60%")
    mock_audio.set_volume.return_value = (["Setting volume"], True, "Volume: 50%")
    mock_audio.mute.return_value = (["Muting"], True, "Muted")
    patches["cios.core.handlers.audio.audio_skill"] = mock_audio

    mock_power = MagicMock()
    mock_power.get_brightness.return_value = 70
    mock_power.change_brightness.return_value = (["Adjusting brightness"], True, "Brightness: 80%")
    mock_power.set_brightness.return_value = (["Setting brightness"], True, "Brightness: 50%")
    mock_power.enable_power_saving.return_value = (
        ["Enabling power saving"],
        True,
        "Power saving enabled",
    )
    patches["cios.core.handlers.system.power_skill"] = mock_power

    mock_pkg = MagicMock()
    mock_pkg.search_packages.return_value = mock_pkg_result
    mock_pkg.install_package.return_value = mock_pkg_result
    mock_pkg.remove_package.return_value = mock_pkg_result
    mock_pkg.update_lists.return_value = mock_pkg_result
    mock_pkg.upgrade_packages.return_value = mock_pkg_result
    patches["cios.core.handlers.packages.pkg_skill"] = mock_pkg

    mock_clip = MagicMock()
    mock_cb = MagicMock()
    mock_cb.get_current.return_value = "some text"
    mock_cb.suggest_actions.return_value = []
    mock_cb.get_history.return_value = []
    mock_clip.CognitiveClipboard.return_value = mock_cb
    mock_clip.detect_content_type.return_value = "text"
    patches["cios.core.handlers.peripherals.clipboard_skill"] = mock_clip

    mock_window = MagicMock()
    mock_window.list_windows.return_value = []
    mock_window.find_window.return_value = None
    mock_window.get_active_window.return_value = None
    patches["cios.core.handlers.peripherals.window_skill"] = mock_window

    mock_bt = MagicMock()
    mock_bt.is_available.return_value = False
    mock_bt.is_powered.return_value = False
    mock_bt.list_connected.return_value = []
    mock_bt.list_paired.return_value = []
    mock_bt.scan.return_value = []
    patches["cios.core.handlers.peripherals.bt_skill"] = mock_bt

    mock_update = MagicMock()
    mock_update.get_current_version.return_value = "1.0.0"
    mock_update.check_update_summary.return_value = (["Checking updates"], "Up to date (v1.0.0)")
    patches["cios.core.handlers.misc.update_skill"] = mock_update

    with contextlib.ExitStack() as stack:
        for target, mock_obj in patches.items():
            stack.enter_context(patch(target, mock_obj))

        planner = Planner(executor=executor, memory=memory)
        result = planner.execute(intent)

    return result


# ── Property Test ────────────────────────────────────────────────────────


class TestAllSkillHandlersFeedback:
    """Property 12: All skill handlers produce at least one feedback message.

    Feature: produto-percebido, Property 12: All skill handlers produce at least one feedback message
    """

    @given(intent_type=st.sampled_from(HANDLED_INTENT_TYPES))
    @settings(max_examples=100)
    def test_all_handlers_produce_feedback(self, intent_type: IntentType):
        """For any IntentType that has a registered handler in the Planner,
        executing that handler with mocked dependencies returns a PlanResult
        with at least one plan_step and a non-empty summary.

        **Validates: Requirements 7.4**
        """
        result = _execute_handler(intent_type)

        # (a) At least one entry in plan_steps
        assert len(result.plan_steps) >= 1, (
            f"Handler for {intent_type.value} returned empty plan_steps.\n"
            f"Result: outcome={result.outcome}, summary={result.summary!r}"
        )

        # (b) Non-empty summary string
        assert result.summary is not None and len(result.summary.strip()) > 0, (
            f"Handler for {intent_type.value} returned empty summary.\n"
            f"Result: outcome={result.outcome}, plan_steps={result.plan_steps}"
        )
