"""Intent pattern rules — split by domain for maintainability.

Order matters! The concatenation order respects priority constraints:
- bluetooth before network/session/status/package
- explore_system/list_apps before app_launch
- gallery before intent_media
- history_search before intent_browse
- intent_browse/write before app_launch
- files_search/open before app_launch
- disk_analysis before file_organize
- screen_capture before session_control
- file_operations before app_launch
- app_launch/command_exec come last (catch-all patterns)
"""

from cios.core.patterns.audio import RULES as _audio_rules
from cios.core.patterns.dev import RULES as _dev_rules
from cios.core.patterns.files import RULES as _files_rules
from cios.core.patterns.gallery import RULES as _gallery_rules
from cios.core.patterns.google import RULES as _google_rules
from cios.core.patterns.intelligence import RULES as _intelligence_rules
from cios.core.patterns.media import RULES as _media_rules
from cios.core.patterns.misc import RULES as _misc_rules
from cios.core.patterns.network import RULES as _network_rules
from cios.core.patterns.packages import RULES as _packages_rules
from cios.core.patterns.peripherals import RULES as _peripherals_rules
from cios.core.patterns.session import RULES as _session_rules
from cios.core.patterns.system import RULES as _system_rules

# Order must respect priority constraints from the original _RULES list.
# Specific patterns come first; catch-all patterns (app_launch) come last.
RULES = (
    _dev_rules  # dev_start, continue_project, close_project, workflow_start
    + _peripherals_rules  # bluetooth (before network/session/status), monitor, clipboard, window, screen_capture (before session)
    + _system_rules  # fix/recover, process_control, log_analysis, system_health, power, status
    + _gallery_rules  # gallery_manage (before intent_media)
    + _media_rules  # intent_media, media_play, media_control
    + _intelligence_rules  # history_search (before browse), intent_browse, intent_write, briefing, intelligence, todo
    + _files_rules  # files_search, files_open, disk_analysis, file_organize, file_ops
    + _network_rules  # network/wifi
    + _audio_rules  # audio/volume
    + _session_rules  # session control
    + _packages_rules  # package management, self_update
    + _google_rules  # email, drive, calendar, gchat
    + _misc_rules  # greetings, explore_system, list_apps, spreadsheet, app_launch, command_exec, theming, scheduler, vpn, firewall, trash
)
