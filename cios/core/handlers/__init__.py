"""Intent handlers — each module handles a group of related intents.

This package decouples the execution logic from the Planner,
keeping each handler focused on a single domain.
"""

from cios.core.handlers.apps import handle_app_launch, handle_explore_system, handle_list_apps
from cios.core.handlers.audio import handle_audio
from cios.core.handlers.dev import handle_continue_project, handle_dev_start, handle_workflow_start
from cios.core.handlers.disk import handle_disk
from cios.core.handlers.files import handle_file_organize, handle_files_open, handle_files_search
from cios.core.handlers.gallery import handle_gallery_manage
from cios.core.handlers.logs import handle_fix_last_error, handle_log_analysis
from cios.core.handlers.media import handle_intent_browse, handle_intent_media, handle_intent_write
from cios.core.handlers.misc import (
    handle_command_exec,
    handle_file_ops,
    handle_intelligence,
    handle_self_update,
)
from cios.core.handlers.network import handle_network
from cios.core.handlers.packages import handle_package
from cios.core.handlers.peripherals import handle_bluetooth, handle_clipboard, handle_window
from cios.core.handlers.process import handle_process_control, handle_status
from cios.core.handlers.screen_capture import handle_screen_capture
from cios.core.handlers.system import handle_power, handle_session, handle_system_health

__all__ = [
    "handle_dev_start",
    "handle_workflow_start",
    "handle_continue_project",
    "handle_process_control",
    "handle_status",
    "handle_log_analysis",
    "handle_fix_last_error",
    "handle_system_health",
    "handle_session",
    "handle_power",
    "handle_file_organize",
    "handle_files_search",
    "handle_files_open",
    "handle_network",
    "handle_audio",
    "handle_disk",
    "handle_app_launch",
    "handle_list_apps",
    "handle_explore_system",
    "handle_package",
    "handle_bluetooth",
    "handle_clipboard",
    "handle_window",
    "handle_intent_media",
    "handle_intent_browse",
    "handle_intent_write",
    "handle_gallery_manage",
    "handle_screen_capture",
    "handle_command_exec",
    "handle_self_update",
    "handle_intelligence",
    "handle_file_ops",
]
