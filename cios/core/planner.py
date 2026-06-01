"""Planner — converts intents into executable plans and runs them.

Keeps plans to 2-5 steps. Handles one retry on failure.
Delegates execution to domain-specific handlers in cios.core.handlers/.
"""

import logging
import time

from cios.core.executor import Executor

# Re-export PlanResult for backward compatibility
from cios.core.handlers._common import PlanResult
from cios.core.handlers.apps import handle_app_launch, handle_explore_system, handle_list_apps
from cios.core.handlers.audio import handle_audio

# Import all handlers
from cios.core.handlers.dev import (  # noqa: F401
    _find_project,
    _scan_project_dirs,
    handle_close_project,
    handle_continue_project,
    handle_dev_start,
    handle_workflow_start,
)
from cios.core.handlers.disk import handle_disk
from cios.core.handlers.files import handle_file_organize, handle_files_open, handle_files_search
from cios.core.handlers.gallery import handle_gallery_manage
from cios.core.handlers.logs import handle_fix_last_error, handle_log_analysis
from cios.core.handlers.media import handle_intent_browse, handle_intent_media, handle_intent_write
from cios.core.handlers.misc import handle_command_exec, handle_intelligence, handle_self_update
from cios.core.handlers.network import handle_network
from cios.core.handlers.packages import handle_package
from cios.core.handlers.peripherals import (
    handle_bluetooth,
    handle_clipboard,
    handle_monitor,
    handle_window,
)
from cios.core.handlers.process import handle_process_control, handle_status
from cios.core.handlers.screen_capture import handle_screen_capture
from cios.core.handlers.spreadsheet import handle_spreadsheet
from cios.core.handlers.google_workspace import (
    handle_email,
    handle_drive,
    handle_calendar,
    handle_gchat,
)
from cios.core.handlers.desktop import handle_theming, handle_scheduler, handle_vpn, handle_firewall, handle_trash
from cios.core.handlers.system import handle_power, handle_session, handle_system_health
from cios.core.intent_parser import Intent, IntentType
from cios.core.mcp import context as mcp
from cios.core.memory import Memory, MemoryRecord
from cios.skills import audio as audio_skill  # noqa: F401
from cios.skills import bluetooth as bt_skill  # noqa: F401
from cios.skills import clipboard as clipboard_skill  # noqa: F401
from cios.skills import network as network_skill  # noqa: F401
from cios.skills import package_manager as pkg_skill  # noqa: F401
from cios.skills import power as power_skill  # noqa: F401
from cios.skills import self_update as update_skill  # noqa: F401
from cios.skills import window_control as window_skill  # noqa: F401
from cios.skills.app_launcher import find_app, launch_app  # noqa: F401

# ═══════════════════════════════════════════════════════════════════════════
#  BACKWARD-COMPATIBLE RE-EXPORTS
#  Tests patch "cios.core.planner.<name>", so we re-export the symbols
#  that handlers use. This keeps existing tests working without changes.
# ═══════════════════════════════════════════════════════════════════════════
from cios.skills.dev_start import (  # noqa: F401
    _detect_editor,
    _is_port_in_use,
    _open_browser,
    _open_editor,
    detect_project,
    execute_dev_start,
)
from cios.skills.disk_analysis import analyze_disk, clean_safe  # noqa: F401
from cios.skills.explore_system import (  # noqa: F401
    format_capabilities,
    list_installed_apps_grouped,
)
from cios.skills.file_organize import organize_directory  # noqa: F401
from cios.skills.file_search import find_and_open, search_files  # noqa: F401
from cios.skills.log_analysis import analyze_text  # noqa: F401
from cios.skills.process_control import (  # noqa: F401
    find_process_on_port,
    kill_process_on_port,
    list_listening_ports,
)
from cios.skills.session_control import (  # noqa: F401
    execute_session_action,
    get_session_action,
)
from cios.skills.system_health import check_system_health  # noqa: F401

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  INTENT → HANDLER ROUTING TABLE
# ═══════════════════════════════════════════════════════════════════════════

_HANDLER_MAP = {
    IntentType.DEV_START: handle_dev_start,
    IntentType.PROCESS_CONTROL: handle_process_control,
    IntentType.LOG_ANALYSIS: handle_log_analysis,
    IntentType.FIX_LAST_ERROR: handle_fix_last_error,
    IntentType.COMMAND_EXEC: handle_command_exec,
    IntentType.STATUS: handle_status,
    IntentType.FILE_ORGANIZE: handle_file_organize,
    IntentType.SYSTEM_HEALTH: handle_system_health,
    IntentType.APP_LAUNCH: handle_app_launch,
    IntentType.SESSION: handle_session,
    IntentType.NETWORK: handle_network,
    IntentType.AUDIO: handle_audio,
    IntentType.DISK_ANALYSIS: handle_disk,
    IntentType.POWER: handle_power,
    IntentType.PACKAGE: handle_package,
    IntentType.CLIPBOARD: handle_clipboard,
    IntentType.WINDOW: handle_window,
    IntentType.BLUETOOTH: handle_bluetooth,
    IntentType.MONITOR: handle_monitor,
    IntentType.SELF_UPDATE: handle_self_update,
    IntentType.EXPLORE_SYSTEM: handle_explore_system,
    IntentType.LIST_APPS: handle_list_apps,
    IntentType.WORKFLOW_START: handle_workflow_start,
    IntentType.CONTINUE_PROJECT: handle_continue_project,
    IntentType.CLOSE_PROJECT: handle_close_project,
    IntentType.INTENT_MEDIA: handle_intent_media,
    IntentType.INTENT_BROWSE: handle_intent_browse,
    IntentType.INTENT_WRITE: handle_intent_write,
    IntentType.FILES_SEARCH: handle_files_search,
    IntentType.FILES_OPEN: handle_files_open,
    IntentType.INTELLIGENCE: handle_intelligence,
    IntentType.GALLERY_MANAGE: handle_gallery_manage,
    IntentType.SCREEN_CAPTURE: handle_screen_capture,
    IntentType.SPREADSHEET: handle_spreadsheet,
    IntentType.EMAIL: handle_email,
    IntentType.DRIVE: handle_drive,
    IntentType.CALENDAR: handle_calendar,
    IntentType.GCHAT: handle_gchat,
    IntentType.THEMING: handle_theming,
    IntentType.SCHEDULER: handle_scheduler,
    IntentType.VPN: handle_vpn,
    IntentType.FIREWALL: handle_firewall,
    IntentType.TRASH: handle_trash,
    IntentType.HISTORY_SEARCH: None,  # Handled directly in bridge
}


class Planner:
    """Converts intents to actions and executes them.

    Acts as a thin orchestrator: routes intents to handlers,
    manages memory persistence, and applies MCO pre-checks.
    """

    def __init__(self, executor: Executor, memory: Memory) -> None:
        self.executor = executor
        self.memory = memory

    def execute(self, intent: Intent) -> PlanResult:
        """Execute an intent with MCO (context-aware decision layer).

        MCO flow:
        1. Consult MCP for system state
        2. Decide: execute directly / ask / suggest
        3. Route to handler
        """
        handler = _HANDLER_MAP.get(intent.type)

        if handler is None:
            # Unknown intent — try Intelligence (cloud) for knowledge questions
            from cios.core.intelligence import intelligence

            if intelligence.is_logged_in:
                try:
                    intel_result = intelligence.query(intent.raw_input, intent="chat")
                    if intel_result.success and intel_result.text:
                        return PlanResult(
                            plan_steps=["Consultando inteligência"],
                            results=[],
                            outcome="success",
                            summary=intel_result.text,
                        )
                except Exception:
                    pass

            return PlanResult(
                plan_steps=["Unknown intent"],
                results=[],
                outcome="failure",
                summary="Não entendi. Tenta reformular?",
                error="Unknown intent type",
            )

        # MCO: context-aware pre-check
        mco_result = self._mco_precheck(intent)
        if mco_result:
            self.memory.store(
                MemoryRecord(
                    timestamp=time.time(),
                    user_input=intent.raw_input,
                    intent=intent.type.value,
                    plan=mco_result.plan_steps,
                    commands=[],
                    outcome=mco_result.outcome,
                    error=mco_result.error,
                    context=intent.params,
                )
            )
            return mco_result

        # Delegate to the appropriate handler
        result = handler(intent, self.executor, self.memory)

        # Store in memory
        self.memory.store(
            MemoryRecord(
                timestamp=time.time(),
                user_input=intent.raw_input,
                intent=intent.type.value,
                plan=result.plan_steps,
                commands=[r.command for r in result.results],
                outcome=result.outcome,
                error=result.error,
                context=intent.params,
            )
        )

        return result

    def _mco_precheck(self, intent: Intent) -> PlanResult | None:
        """MCO: context-aware decision layer.

        Consults MCP before execution. Returns a PlanResult if the MCO
        can resolve the intent without running the full handler, or None
        to proceed normally.

        Rules:
        - If context is sufficient → resolve directly (instant)
        - If state already matches request → short-circuit
        - Otherwise → proceed to handler
        """
        state = mcp.snapshot()

        # AUDIO: instant responses from MCP state
        if intent.type == IntentType.AUDIO:
            action = intent.params.get("action")
            if action == "mute" and state.audio.muted:
                return PlanResult(
                    plan_steps=["Checking volume"],
                    results=[],
                    outcome="success",
                    summary=f"Already muted (volume at {state.audio.volume}%)",
                )
            if action == "unmute" and not state.audio.muted:
                return PlanResult(
                    plan_steps=["Checking volume"],
                    results=[],
                    outcome="success",
                    summary=f"Already unmuted (volume at {state.audio.volume}%)",
                )

        # NETWORK: already connected short-circuit
        if intent.type == IntentType.NETWORK:
            action = intent.params.get("action")
            if action == "disconnect" and not state.wifi.connected:
                return PlanResult(
                    plan_steps=["Checking Wi-Fi"],
                    results=[],
                    outcome="success",
                    summary="Already disconnected",
                )

        # BLUETOOTH: power already in desired state
        if intent.type == IntentType.BLUETOOTH:
            action = intent.params.get("action")
            if action == "power_on" and state.bluetooth.powered:
                return PlanResult(
                    plan_steps=["Checking Bluetooth"],
                    results=[],
                    outcome="success",
                    summary="Bluetooth is already on",
                )
            if action == "power_off" and not state.bluetooth.powered:
                return PlanResult(
                    plan_steps=["Checking Bluetooth"],
                    results=[],
                    outcome="success",
                    summary="Bluetooth is already off",
                )

        return None

    # ═══════════════════════════════════════════════════════════════════════
    #  BACKWARD-COMPATIBLE METHOD WRAPPERS
    #  Tests call planner._handle_X(intent) directly. These delegate to
    #  the handler functions while preserving the old interface.
    # ═══════════════════════════════════════════════════════════════════════

    def _handle_dev_start(self, intent: Intent) -> PlanResult:
        return handle_dev_start(intent, self.executor, self.memory)

    def _handle_process_control(self, intent: Intent) -> PlanResult:
        return handle_process_control(intent, self.executor, self.memory)

    def _handle_log_analysis(self, intent: Intent) -> PlanResult:
        return handle_log_analysis(intent, self.executor, self.memory)

    def _handle_fix_last_error(self, intent: Intent) -> PlanResult:
        return handle_fix_last_error(intent, self.executor, self.memory)

    def _handle_command_exec(self, intent: Intent) -> PlanResult:
        return handle_command_exec(intent, self.executor, self.memory)

    def _handle_status(self, intent: Intent) -> PlanResult:
        return handle_status(intent, self.executor, self.memory)

    def _handle_file_organize(self, intent: Intent) -> PlanResult:
        return handle_file_organize(intent, self.executor, self.memory)

    def _handle_system_health(self, intent: Intent) -> PlanResult:
        return handle_system_health(intent, self.executor, self.memory)

    def _handle_app_launch(self, intent: Intent) -> PlanResult:
        return handle_app_launch(intent, self.executor, self.memory)

    def _handle_session(self, intent: Intent) -> PlanResult:
        return handle_session(intent, self.executor, self.memory)

    def _handle_network(self, intent: Intent) -> PlanResult:
        return handle_network(intent, self.executor, self.memory)

    def _handle_audio(self, intent: Intent) -> PlanResult:
        return handle_audio(intent, self.executor, self.memory)

    def _handle_disk(self, intent: Intent) -> PlanResult:
        return handle_disk(intent, self.executor, self.memory)

    def _handle_power(self, intent: Intent) -> PlanResult:
        return handle_power(intent, self.executor, self.memory)

    def _handle_package(self, intent: Intent) -> PlanResult:
        return handle_package(intent, self.executor, self.memory)

    def _handle_clipboard(self, intent: Intent) -> PlanResult:
        return handle_clipboard(intent, self.executor, self.memory)

    def _handle_window(self, intent: Intent) -> PlanResult:
        return handle_window(intent, self.executor, self.memory)

    def _handle_bluetooth(self, intent: Intent) -> PlanResult:
        return handle_bluetooth(intent, self.executor, self.memory)

    def _handle_monitor(self, intent: Intent) -> PlanResult:
        return handle_monitor(intent, self.executor, self.memory)

    def _handle_self_update(self, intent: Intent) -> PlanResult:
        return handle_self_update(intent, self.executor, self.memory)

    def _handle_explore_system(self, intent: Intent) -> PlanResult:
        return handle_explore_system(intent, self.executor, self.memory)

    def _handle_list_apps(self, intent: Intent) -> PlanResult:
        return handle_list_apps(intent, self.executor, self.memory)

    def _handle_workflow_start(self, intent: Intent) -> PlanResult:
        return handle_workflow_start(intent, self.executor, self.memory)

    def _handle_continue_project(self, intent: Intent) -> PlanResult:
        return handle_continue_project(intent, self.executor, self.memory)

    def _handle_intent_media(self, intent: Intent) -> PlanResult:
        return handle_intent_media(intent, self.executor, self.memory)

    def _handle_intent_browse(self, intent: Intent) -> PlanResult:
        return handle_intent_browse(intent, self.executor, self.memory)

    def _handle_intent_write(self, intent: Intent) -> PlanResult:
        return handle_intent_write(intent, self.executor, self.memory)

    def _handle_files_search(self, intent: Intent) -> PlanResult:
        return handle_files_search(intent, self.executor, self.memory)

    def _handle_files_open(self, intent: Intent) -> PlanResult:
        return handle_files_open(intent, self.executor, self.memory)

    def _handle_intelligence(self, intent: Intent) -> PlanResult:
        return handle_intelligence(intent, self.executor, self.memory)
