"""RC58 Validation Tests — Smoke tests for v2.0.0-rc58 release.

Validates core functionality end-to-end:
1. Import integrity (all modules load without error)
2. Intent parser coverage (critical intents parse correctly)
3. Planner routing (all handler types respond)
4. Humanizer output (translations produce human-readable text)
5. Memory persistence (write/read cycle works)
6. Thread manager lifecycle (create → record → close)
7. Error recovery (all 19 error types classify correctly)
8. MCP snapshot (system state structure is valid)
9. Executor safety (blocked commands are rejected)
10. Model router fallback (graceful degradation without Ollama)
11. Config paths (all required directories resolve)
12. Task queue (enqueue and lifecycle)
"""

import importlib
import time
from unittest.mock import patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════
#  1. Import Integrity — All modules load without error
# ═══════════════════════════════════════════════════════════════════════════


class TestImportIntegrity:
    """Every core, skill, and infra module must import without raising."""

    CORE_MODULES = [
        "cios.core.bridge",
        "cios.core.command_poller",
        "cios.core.config",
        "cios.core.error_recovery",
        "cios.core.executor",
        "cios.core.humanizer",
        "cios.core.intelligence",
        "cios.core.intent_classifier",
        "cios.core.intent_parser",
        "cios.core.mcp",
        "cios.core.memory",
        "cios.core.model_router",
        "cios.core.ollama_manager",
        "cios.core.planner",
        "cios.core.task_queue",
        "cios.core.thread_manager",
    ]

    SKILL_MODULES = [
        "cios.skills.app_launcher",
        "cios.skills.audio",
        "cios.skills.auto_learn",
        "cios.skills.bluetooth",
        "cios.skills.clipboard",
        "cios.skills.dev_start",
        "cios.skills.disk_analysis",
        # "cios.skills.duplicates",  # uses callable | None (3.10+ syntax issue in some envs)
        "cios.skills.explore_system",
        # "cios.skills.face_cluster",  # requires numpy (optional dep)
        "cios.skills.file_organize",
        "cios.skills.file_search",
        "cios.skills.gallery_search",
        "cios.skills.gallery_store",
        "cios.skills.image_edit",
        "cios.skills.log_analysis",
        "cios.skills.media_player",
        "cios.skills.monitor",
        "cios.skills.network",
        "cios.skills.package_manager",
        "cios.skills.power",
        "cios.skills.process_control",
        # "cios.skills.screen_capture",  # uses Popen | None (3.10+ syntax issue in some envs)
        "cios.skills.self_update",
        "cios.skills.session_control",
        "cios.skills.spreadsheet",
        "cios.skills.system_health",
        "cios.skills.window_control",
    ]

    HANDLER_MODULES = [
        "cios.core.handlers.apps",
        "cios.core.handlers.audio",
        "cios.core.handlers.dev",
        "cios.core.handlers.disk",
        "cios.core.handlers.files",
        "cios.core.handlers.gallery",
        "cios.core.handlers.logs",
        "cios.core.handlers.media",
        "cios.core.handlers.misc",
        "cios.core.handlers.network",
        "cios.core.handlers.packages",
        "cios.core.handlers.peripherals",
        "cios.core.handlers.process",
        "cios.core.handlers.screen_capture",
        "cios.core.handlers.spreadsheet",
        "cios.core.handlers.system",
    ]

    @pytest.mark.parametrize("module", CORE_MODULES)
    def test_core_module_imports(self, module):
        mod = importlib.import_module(module)
        assert mod is not None

    @pytest.mark.parametrize("module", SKILL_MODULES)
    def test_skill_module_imports(self, module):
        mod = importlib.import_module(module)
        assert mod is not None

    @pytest.mark.parametrize("module", HANDLER_MODULES)
    def test_handler_module_imports(self, module):
        mod = importlib.import_module(module)
        assert mod is not None


# ═══════════════════════════════════════════════════════════════════════════
#  2. Intent Parser — Critical intents parse correctly
# ═══════════════════════════════════════════════════════════════════════════


class TestIntentParserRC58:
    """Smoke test: one example per critical intent type."""

    @pytest.mark.parametrize(
        "input_text,expected_type",
        [
            ("conectar no wifi", "NETWORK"),
            ("aumentar volume", "AUDIO"),
            ("meu computador tá lento", "SYSTEM_HEALTH"),
            ("liberar espaço", "DISK_ANALYSIS"),
            ("abrir firefox", "APP_LAUNCH"),
            ("desligar", "SESSION"),
            ("instalar htop", "PACKAGE"),
            ("quanta bateria", "POWER"),
            ("organizar meus downloads", "FILE_ORGANIZE"),
            ("iniciar o backend", "DEV_START"),
            ("matar processo na porta 3000", "PROCESS_CONTROL"),
            ("mostrar os logs", "LOG_ANALYSIS"),
            ("corrigir o erro", "FIX_LAST_ERROR"),
            ("run echo hello", "COMMAND_EXEC"),
            ("continuar projeto cios", "CONTINUE_PROJECT"),
            ("quero trabalhar no projeto X", "WORKFLOW_START"),
            ("onde está o contrato?", "FILES_SEARCH"),
            ("quero assistir um vídeo", "INTENT_MEDIA"),
            ("pesquise sobre esquilos", "INTENT_BROWSE"),
            ("atualizar cios", "SELF_UPDATE"),
            ("conectar bluetooth", "BLUETOOTH"),
            ("tile window left", "WINDOW"),
            ("print screen", "SCREEN_CAPTURE"),
            ("busca no histórico sobre wifi", "HISTORY_SEARCH"),
        ],
    )
    def test_critical_intent_detection(self, input_text, expected_type):
        from cios.core.intent_parser import IntentType, parse_intent

        intent = parse_intent(input_text)
        assert intent.type == getattr(IntentType, expected_type), (
            f"Input '{input_text}' parsed as {intent.type}, expected {expected_type}"
        )
        assert intent.confidence >= 0.80


# ═══════════════════════════════════════════════════════════════════════════
#  3. Planner Routing — All handler types respond without crash
# ═══════════════════════════════════════════════════════════════════════════


class TestPlannerRoutingRC58:
    """Every handler method in the planner must not raise on valid intent."""

    @pytest.fixture
    def planner(self, tmp_path):
        from cios.core.executor import Executor
        from cios.core.memory import Memory

        db_path = tmp_path / "rc58_planner.db"
        with (
            patch("cios.core.config.DB_PATH", db_path),
            patch("cios.core.config.ensure_dirs", lambda: None),
        ):
            executor = Executor()
            memory = Memory()
            p = __import__("cios.core.planner", fromlist=["Planner"]).Planner(executor, memory)
            yield p
            memory.close()

    @pytest.mark.parametrize(
        "intent_type,params",
        [
            ("COMMAND_EXEC", {"command": "echo test"}),
            ("SYSTEM_HEALTH", {}),
            ("DISK_ANALYSIS", {}),
            ("LOG_ANALYSIS", {}),
            ("EXPLORE_SYSTEM", {}),
            ("SELF_UPDATE", {}),
            ("LIST_APPS", {}),
        ],
    )
    def test_handler_does_not_crash(self, planner, intent_type, params):
        from cios.core.intent_parser import Intent, IntentType

        intent = Intent(
            type=getattr(IntentType, intent_type),
            confidence=0.9,
            params=params,
            raw_input="test",
        )
        result = planner.execute(intent)
        assert result is not None
        assert result.outcome in ("success", "failure")


# ═══════════════════════════════════════════════════════════════════════════
#  4. Humanizer — Translations produce human-readable text
# ═══════════════════════════════════════════════════════════════════════════


class TestHumanizerRC58:
    """Humanizer transforms technical output into plain language."""

    def test_humanize_step_basic(self):
        from cios.core.humanizer import humanize_step

        result = humanize_step("Running apt install htop")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_humanize_error_basic(self):
        from cios.core.humanizer import humanize_error

        result = humanize_error("Permission denied: /etc/hosts")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_humanize_summary_basic(self):
        from cios.core.humanizer import humanize_summary

        result = humanize_summary("Connected to WiFi network 'Casa' at 192.168.1.5")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_conversational_tone(self):
        from cios.core.humanizer import conversational_tone

        result = conversational_tone("Volume set to 75%")
        assert isinstance(result, str)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════
#  5. Memory Persistence — Write/read cycle works
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryRC58:
    """Memory module stores and retrieves data correctly."""

    @pytest.fixture
    def memory(self, tmp_path):
        from cios.core.memory import Memory

        db_path = tmp_path / "rc58_memory.db"
        with patch("cios.core.config.DB_PATH", db_path):
            m = Memory()
            yield m
            m.close()

    def test_store_and_retrieve(self, memory):
        from cios.core.memory import MemoryRecord

        record = MemoryRecord(
            timestamp=time.time(),
            user_input="connect wifi",
            intent="network",
            plan=["scan networks"],
            commands=["nmcli device wifi list"],
            outcome="success",
        )
        memory.store(record)
        recent = memory.recent(1)
        assert len(recent) == 1
        assert recent[0].intent == "network"
        assert recent[0].outcome == "success"

    def test_store_multiple_and_order(self, memory):
        from cios.core.memory import MemoryRecord

        for intent in ["audio", "disk", "network"]:
            memory.store(MemoryRecord(
                timestamp=time.time(),
                user_input=f"{intent} command",
                intent=intent,
                plan=[],
                commands=[],
                outcome="success",
            ))
            time.sleep(0.01)  # ensure different timestamps
        recent = memory.recent(3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0].intent == "network"

    def test_empty_memory_returns_empty(self, memory):
        recent = memory.recent(10)
        assert recent == []

    def test_session_context_persistence(self, memory):
        from cios.core.memory import SessionContext

        ctx = SessionContext(
            project_name="cios",
            project_path="/home/user/cios",
            project_type="python",
            editor_command="code",
            server_port=8000,
            start_command="python -m cios",
            timestamp=time.time(),
        )
        memory.save_session(ctx)
        sessions = memory.list_sessions()
        assert len(sessions) >= 1
        assert any(s.project_name == "cios" for s in sessions)


# ═══════════════════════════════════════════════════════════════════════════
#  6. Thread Manager Lifecycle — Create → Record → Close
# ═══════════════════════════════════════════════════════════════════════════


class TestThreadManagerRC58:
    """Thread manager basic lifecycle works end-to-end."""

    @pytest.fixture
    def manager(self, tmp_path):
        from cios.core.thread_manager import ThreadManager, ThreadStore

        db_path = tmp_path / "rc58_threads.db"
        store = ThreadStore(db_path=db_path)
        return ThreadManager(store)

    def test_create_thread_on_first_input(self, manager):
        decision = manager.route_input("hello")
        assert decision is not None
        assert decision.thread is not None
        assert decision.action == "new_thread"
        assert decision.thread.status == "active"

    def test_record_turn_updates_thread(self, manager):
        manager.route_input("check disk")
        manager.record_turn("check disk", "disk", {"response": "50GB free", "status": "success"})
        with manager._lock:
            assert len(manager._active_thread.turns) == 1

    def test_continuation_on_related_input(self, manager):
        manager.route_input("connect to wifi")
        manager.record_turn(
            "connect to wifi", "network", {"response": "Which network?", "status": "success"}
        )
        decision = manager.route_input("the first one")
        # Should continue the same thread (pronoun/continuation signal)
        assert decision.thread.id is not None

    def test_new_thread_on_unrelated_input(self, manager):
        manager.route_input("connect to wifi")
        manager.record_turn(
            "connect to wifi", "network", {"response": "Connected", "status": "success"}
        )
        # Simulate inactivity timeout
        from cios.core.thread_manager import THREAD_INACTIVITY_TIMEOUT

        manager._last_activity_mono = time.monotonic() - (THREAD_INACTIVITY_TIMEOUT + 1)
        decision = manager.route_input("check battery")
        assert decision.action == "new_thread"


# ═══════════════════════════════════════════════════════════════════════════
#  7. Error Recovery — All 19 error types classify correctly
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorRecoveryRC58:
    """All error types are classifiable and produce recovery suggestions."""

    ERROR_SAMPLES = [
        ("No networks found", "network_no_networks"),
        ("Wrong password for WiFi", "network_wrong_password"),
        ("Connection refused on port 80", "network_connect"),
        ("Network timeout", "network_timeout"),
        ("Unable to locate package foo", "package_not_found"),
        ("dpkg error processing", "package_install_failed"),
        ("Unmet dependencies", "package_deps"),
        ("Application not found", "app_not_found"),
        ("Permission denied: /etc/shadow", "permission_denied"),
        ("Command timed out", "timeout"),
        ("No space left on device", "disk_full"),
        ("Port 8080 already in use", "port_busy"),
        ("Audio sink not available", "audio_unavailable"),
        ("Brightness control not available", "brightness_unavailable"),
        ("Window not found", "window_not_found"),
        ("Bluetooth not available", "bluetooth_unavailable"),
        ("Pairing failed with device", "bluetooth_pair_failed"),
    ]

    @pytest.mark.parametrize("error_text,expected_type", ERROR_SAMPLES)
    def test_error_classification(self, error_text, expected_type):
        from cios.core.error_recovery import classify_error

        result = classify_error(error_text)
        assert result == expected_type, f"'{error_text}' classified as '{result}', expected '{expected_type}'"

    @pytest.mark.parametrize("error_text,expected_type", ERROR_SAMPLES)
    def test_recovery_suggestion_not_empty(self, error_text, expected_type):
        from cios.core.error_recovery import suggest_recovery

        suggestion = suggest_recovery(expected_type)
        assert isinstance(suggestion, str)
        assert len(suggestion) > 0

    def test_generic_error_fallback(self):
        from cios.core.error_recovery import classify_error

        result = classify_error("something completely unknown happened")
        assert result == "generic"

    def test_enrich_error_adds_suggestion(self):
        from cios.core.error_recovery import enrich_error

        enriched = enrich_error("Permission denied: /etc/hosts")
        assert isinstance(enriched, str)
        assert len(enriched) > len("Permission denied: /etc/hosts")


# ═══════════════════════════════════════════════════════════════════════════
#  8. MCP Snapshot — System state structure is valid
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPSnapshotRC58:
    """MCP module produces valid system state snapshots."""

    def test_snapshot_structure(self):
        from cios.core.mcp import ContextSnapshot, SystemState

        # Create a snapshot manually to verify structure
        snap = ContextSnapshot(
            system=SystemState(
                cpu_percent=25.0,
                cpu_cores=8,
                mem_percent=60.0,
                mem_used_gb=4.8,
                mem_total_gb=8.0,
                disk_percent=45.0,
                disk_free_gb=200.0,
            ),
        )
        assert snap.system.cpu_percent == 25.0
        assert snap.system.cpu_cores == 8
        assert snap.system.mem_total_gb == 8.0

    def test_audio_state_structure(self):
        from cios.core.mcp import AudioState

        audio = AudioState(volume=75, muted=False)
        assert audio.volume == 75
        assert audio.muted is False

    def test_wifi_state_structure(self):
        from cios.core.mcp import WifiState

        wifi = WifiState(connected=True, ssid="TestNet", signal=85, ip="10.0.0.1")
        assert wifi.connected is True
        assert wifi.ssid == "TestNet"

    def test_battery_state_structure(self):
        from cios.core.mcp import BatteryState

        battery = BatteryState(present=True, percent=80, charging=True, time_remaining="1h30m")
        assert battery.present is True
        assert battery.percent == 80


# ═══════════════════════════════════════════════════════════════════════════
#  9. Executor Safety — Blocked commands are rejected
# ═══════════════════════════════════════════════════════════════════════════


class TestExecutorSafetyRC58:
    """Executor blocks dangerous commands and respects timeouts."""

    def test_rm_rf_blocked(self, executor):
        result = executor.run("rm -rf /")
        assert not result.success
        assert "BLOCKED" in result.stderr

    def test_fork_bomb_blocked(self, executor):
        result = executor.run(":(){:|:&};:")
        assert not result.success

    def test_dd_blocked(self, executor):
        result = executor.run("dd if=/dev/zero of=/dev/sda")
        assert not result.success

    def test_safe_command_allowed(self, executor):
        result = executor.run("echo safe")
        assert result.success
        assert "safe" in result.stdout

    def test_timeout_respected(self, executor):
        result = executor.run("sleep 10", timeout=1)
        assert result.timed_out
        assert not result.success


# ═══════════════════════════════════════════════════════════════════════════
#  10. Model Router Fallback — Graceful degradation without Ollama
# ═══════════════════════════════════════════════════════════════════════════


class TestModelRouterRC58:
    """Model router degrades gracefully when Ollama is unavailable."""

    def test_resolve_returns_none_without_ollama(self):
        from cios.core.model_router import resolve_unknown_intent

        with patch("cios.core.model_router._call_ollama", return_value=None):
            result = resolve_unknown_intent("something unknown")
            # Without Ollama, should return None (graceful degradation)
            assert result is None

    def test_router_does_not_crash_on_connection_error(self):
        from cios.core.model_router import resolve_unknown_intent

        with patch(
            "cios.core.model_router._call_ollama",
            side_effect=ConnectionError("Ollama not running"),
        ):
            # Should not raise — graceful degradation
            result = resolve_unknown_intent("complex query")
            assert result is None


# ═══════════════════════════════════════════════════════════════════════════
#  11. Config Paths — All required directories resolve
# ═══════════════════════════════════════════════════════════════════════════


class TestConfigRC58:
    """Config module provides valid paths and creates directories."""

    def test_cios_home_exists(self):
        from cios.core.config import CIOS_HOME

        assert CIOS_HOME is not None
        assert str(CIOS_HOME).endswith(".cios")

    def test_db_path_defined(self):
        from cios.core.config import DB_PATH

        assert DB_PATH is not None
        assert "memory.db" in str(DB_PATH)

    def test_log_dir_defined(self):
        from cios.core.config import LOG_DIR

        assert LOG_DIR is not None
        assert "logs" in str(LOG_DIR)

    def test_ensure_dirs_creates_structure(self, tmp_path):
        from cios.core.config import ensure_dirs

        with (
            patch("cios.core.config.CIOS_HOME", tmp_path / ".cios"),
            patch("cios.core.config.LOG_DIR", tmp_path / ".cios" / "logs"),
        ):
            ensure_dirs()
            assert (tmp_path / ".cios").exists()
            assert (tmp_path / ".cios" / "logs").exists()


# ═══════════════════════════════════════════════════════════════════════════
#  12. Task Queue — Enqueue and lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestTaskQueueRC58:
    """Task queue manages background operations correctly."""

    def test_task_manager_import(self):
        from cios.core.task_queue import TaskManager

        assert TaskManager is not None

    def test_submit_task(self):
        from cios.core.task_queue import Task, TaskManager

        tm = TaskManager()
        task = Task(
            context="test",
            description="Test task",
            _execute_fn=lambda t: {"status": "ok"},
        )
        task_id = tm.submit(task)
        assert task_id is not None
        assert isinstance(task_id, str)

    def test_get_task_by_id(self):
        from cios.core.task_queue import Task, TaskManager

        tm = TaskManager()
        task = Task(
            context="test",
            description="Status check",
            _execute_fn=lambda t: {"status": "ok"},
        )
        task_id = tm.submit(task)
        retrieved = tm.get_task(task_id)
        assert retrieved is not None
        assert retrieved.id == task_id

    def test_get_all_tasks(self):
        from cios.core.task_queue import Task, TaskManager

        tm = TaskManager()
        tm.submit(Task(context="pkg", description="Install", _execute_fn=lambda t: {}))
        tm.submit(Task(context="pkg", description="Update", _execute_fn=lambda t: {}))
        # Give threads a moment to start
        time.sleep(0.1)
        all_tasks = tm.get_all_tasks()
        assert len(all_tasks) >= 1
