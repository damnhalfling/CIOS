"""Intent types and data structures — shared across parser and pattern modules.

This module exists to avoid circular imports between intent_parser.py
and the pattern modules under cios/core/patterns/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IntentType(Enum):
    DEV_START = "dev_start"
    PROCESS_CONTROL = "process_control"
    LOG_ANALYSIS = "log_analysis"
    FIX_LAST_ERROR = "fix_last_error"
    COMMAND_EXEC = "command_exec"
    STATUS = "status"
    FILE_ORGANIZE = "file_organize"
    SYSTEM_HEALTH = "system_health"
    APP_LAUNCH = "app_launch"
    SESSION = "session"
    NETWORK = "network"
    AUDIO = "audio"
    DISK_ANALYSIS = "disk_analysis"
    POWER = "power"
    PACKAGE = "package"
    CLIPBOARD = "clipboard"
    WINDOW = "window"
    BLUETOOTH = "bluetooth"
    SELF_UPDATE = "self_update"
    EXPLORE_SYSTEM = "explore_system"
    LIST_APPS = "list_apps"
    CONTINUE_PROJECT = "continue_project"
    CLOSE_PROJECT = "close_project"
    WORKFLOW_START = "workflow_start"
    INTENT_MEDIA = "intent_media"
    INTENT_BROWSE = "intent_browse"
    INTENT_WRITE = "intent_write"
    FILES_SEARCH = "files_search"
    FILES_OPEN = "files_open"
    INTELLIGENCE = "intelligence"
    GALLERY_MANAGE = "gallery_manage"
    SCREEN_CAPTURE = "screen_capture"
    HISTORY_SEARCH = "history_search"
    SPREADSHEET = "spreadsheet"
    MONITOR = "monitor"
    EMAIL = "email"
    DRIVE = "drive"
    CALENDAR = "calendar"
    GCHAT = "gchat"
    THEMING = "theming"
    SCHEDULER = "scheduler"
    VPN = "vpn"
    FIREWALL = "firewall"
    TRASH = "trash"
    BRIEFING = "briefing"
    MEDIA_PLAY = "media_play"
    FILE_OPS = "file_ops"
    MEDIA_CONTROL = "media_control"
    TODO = "todo"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    type: IntentType
    confidence: float  # 0.0 – 1.0
    params: dict = field(default_factory=dict)
    raw_input: str = ""
    requires_complex_reasoning: bool = False


def _normalize_position(pos: str) -> str:
    """Normalize position names from PT/EN to internal format."""
    mapping = {
        "esquerda": "left",
        "direita": "right",
        "cima": "top",
        "baixo": "bottom",
        "left": "left",
        "right": "right",
        "top": "top",
        "bottom": "bottom",
    }
    return mapping.get(pos.lower(), pos.lower())
