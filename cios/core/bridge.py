"""Bridge — clean interface between UI and backend.

Exposes:
    execute_command(command: str) -> dict
    execute_streaming(command: str, on_step: callback) -> dict

Features:
- Conversation context (3-turn memory for follow-ups)
- Clarification questions ("Qual rede?" / "Senha?")
- Pronoun resolution ("fecha esse" → last app)
- MCP activity notification (adaptive polling)
- Post-action validation (force re-scan + verify state changed)
- Error enrichment (every error gets a recovery suggestion)
- Retry on transient failures (timeout, busy → auto-retry once)
"""

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from cios.core.config import ensure_dirs
from cios.core.error_recovery import enrich_error, is_retryable
from cios.core.executor import Executor
from cios.core.humanizer import humanize_error, humanize_result
from cios.core.intent_classifier import classify_intent, learn_from_success
from cios.core.intent_parser import Intent, IntentType, parse_intent
from cios.core.memory import Memory
from cios.core.model_router import resolve_unknown_intent
from cios.core.planner import Planner, PlanResult
from cios.core.thread_manager import (
    ThreadManager,
    ThreadStore,
)

logger = logging.getLogger(__name__)


class _CancelledError(Exception):
    """Raised when user cancels the current operation."""

    pass


# Intents that change system state (need post-action validation)
_STATE_CHANGING_INTENTS = frozenset(
    [
        IntentType.NETWORK,
        IntentType.AUDIO,
        IntentType.POWER,
        IntentType.SESSION,
        IntentType.PACKAGE,
        IntentType.BLUETOOTH,
    ]
)


# ═══════════════════════════════════════════════════════════════════════════
#  CONVERSATION CONTEXT (#74)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""

    user_input: str
    intent_type: str  # IntentType.value
    params: dict = field(default_factory=dict)
    result_summary: str = ""
    outcome: str = ""
    timestamp: float = 0.0


@dataclass
class GuidedFlowStep:
    """A single step in a multi-step guided flow."""

    question: str  # Human-readable question
    question_type: str  # "choice", "text", "password"
    options: list[str] = field(default_factory=list)  # Available choices (for "choice" type)
    param_key: str = ""  # Which intent param this fills


@dataclass
class GuidedFlow:
    """State for a multi-step guided conversation flow."""

    intent: Intent  # The original intent being built
    steps: list[GuidedFlowStep] = field(default_factory=list)  # All steps
    current_step: int = 0  # Index of current step
    collected: dict = field(default_factory=dict)  # Params collected so far


@dataclass
class PendingQuestion:
    """A question waiting for user's answer."""

    intent: Intent
    question_type: str  # "ssid", "password", "target", "app", "port", "confirm_action"
    options: list[str] = field(default_factory=list)  # available choices
    timestamp: float = 0.0
    # Multi-step guided flow support
    flow_steps: list[GuidedFlowStep] | None = None
    flow_collected: dict = field(default_factory=dict)


# Pronouns that reference previous context
_PRONOUNS_PT = {
    "esse",
    "essa",
    "isso",
    "este",
    "esta",
    "nesse",
    "nessa",
    "nisso",
    "dele",
    "dela",
    "aquele",
    "aquela",
}
_PRONOUNS_EN = {"that", "this", "it", "those", "the same", "that one"}
_ALL_PRONOUNS = _PRONOUNS_PT | _PRONOUNS_EN


class CIOSBridge:
    """Single entry point for all UI → backend communication."""

    def __init__(self, on_progress: Callable[[str, int, int], None] | None = None) -> None:
        """Initialize bridge with all subsystems.

        Args:
            on_progress: Optional callback(stage, current, total) for boot progress.
                         Used by splash screen to show real loading stages.
        """
        _t0 = time.monotonic()
        self._boot_times: dict[str, float] = {}

        ensure_dirs()
        self._executor = Executor()
        self._memory = Memory()
        self._planner = Planner(self._executor, self._memory)
        # Conversation state — delegated to ThreadManager
        self._thread_store = ThreadStore()
        self._thread_manager = ThreadManager(self._thread_store)
        # Background task execution
        from cios.core.task_queue import TaskManager

        self._task_manager = TaskManager(on_task_complete=self._on_task_complete)
        # Cancellation flag — checked by long-running operations
        self._cancelled = False

        self._boot_times["init_core"] = (time.monotonic() - _t0) * 1000

        # Check and auto-install missing system dependencies
        _t_deps = time.monotonic()
        if on_progress:
            on_progress("Verificando dependências…", 1, 14)
        try:
            from cios.infra.deps import check_and_install_deps

            missing = check_and_install_deps()
            if missing:
                logger.warning("Missing deps after check: %s", missing)
        except Exception as e:
            logger.debug("Dep check failed (non-critical): %s", e)
        self._boot_times["deps_check"] = (time.monotonic() - _t_deps) * 1000

        # Ensure Ollama is running (if configured as provider)
        _t_ollama = time.monotonic()
        if on_progress:
            on_progress("Verificando IA local…", 2, 14)
        from cios.core.ollama_manager import ensure_ollama_running

        self._ollama_ok = ensure_ollama_running()
        self._boot_times["ollama_check"] = (time.monotonic() - _t_ollama) * 1000

        # Start MCP (system context polling + watchers) with progress
        _t1 = time.monotonic()
        if on_progress:
            on_progress("Detectando sistema…", 3, 14)
        from cios.core.mcp import context

        context.start(on_progress=self._mcp_progress_adapter(on_progress))
        self._boot_times["mcp_start"] = (time.monotonic() - _t1) * 1000

        self._boot_times["total"] = (time.monotonic() - _t0) * 1000
        logger.info(
            "Bridge initialized in %.0fms (core: %.0fms, deps: %.0fms, mcp: %.0fms)",
            self._boot_times["total"],
            self._boot_times["init_core"],
            self._boot_times.get("deps_check", 0),
            self._boot_times["mcp_start"],
        )

    @property
    def _pending_question(self) -> PendingQuestion | None:
        """Proxy to ThreadManager's pending question for backward compatibility.

        Tests and external code can read bridge._pending_question to inspect
        the current pending question state without reaching into ThreadManager
        internals.
        """
        if self._thread_manager._active_thread is not None:
            return self._thread_manager._active_thread.pending_question
        return None

    @staticmethod
    def _mcp_progress_adapter(
        on_progress: Callable[[str, int, int], None] | None,
    ) -> Callable[[str, int, int], None] | None:
        """Adapt MCP progress to splash progress (offset stage numbers)."""
        if not on_progress:
            return None

        def adapter(stage: str, current: int, total: int) -> None:
            # MCP stages are 0-7 (7 scanners), mapped to splash positions 2-9 out of 14
            on_progress(stage, 2 + current, 14)

        return adapter

    @property
    def boot_times(self) -> dict[str, float]:
        """Boot timing data (ms). Includes MCP sub-timings."""
        from cios.core.mcp import context

        combined = dict(self._boot_times)
        for k, v in context.boot_times.items():
            combined[f"mcp.{k}"] = v
        return combined

    # ═══════════════════════════════════════════════════════════════════
    #  PUBLIC API
    # ═══════════════════════════════════════════════════════════════════

    def execute_command(self, command: str, confirmed: bool = False) -> dict:
        """Execute a natural language command."""
        command = command.strip()
        if not command:
            return self._empty_response()

        self._cancelled = False
        try:
            return self._process(command, confirmed)
        except _CancelledError:
            return {
                "steps": [],
                "result": "Cancelado",
                "status": "success",
                "confirm": None,
                "voice_mode": "full",
            }
        except Exception as e:
            logger.exception("Unhandled error in execute_command")
            return self._graceful_error(e)

    def cancel(self) -> None:
        """Cancel the current execution. Thread-safe."""
        self._cancelled = True

    def execute_streaming(
        self,
        command: str,
        confirmed: bool = False,
        on_step: Callable[[str, int, int], None] | None = None,
    ) -> dict:
        """Execute a command with real-time step streaming."""
        command = command.strip()
        if not command:
            return self._empty_response()

        try:
            return self._process_streaming(command, confirmed, on_step)
        except Exception as e:
            logger.exception("Unhandled error in execute_streaming")
            return self._graceful_error(e)

    # ═══════════════════════════════════════════════════════════════════
    #  CORE PROCESSING
    # ═══════════════════════════════════════════════════════════════════

    def _process(self, user_input: str, confirmed: bool) -> dict:
        from cios.core.mcp import context
        from cios.ui.topbar import signal_topbar_idle, signal_topbar_processing

        # ThreadManager handles routing (replaces manual _pending_question check)
        decision = self._thread_manager.route_input(user_input)

        if decision.action == "answer_pending":
            return self._handle_answer(user_input, confirmed, decision.pending_question)

        # (#76) Resolve pronouns using conversation context
        resolved_input = self._resolve_pronouns(user_input)

        signal_topbar_processing("Entendendo…")
        intent = parse_intent(resolved_input)

        # LLM fallback for unknown intents — hybrid model:
        # 1. Try lightweight classifier (cache + LLM classification)
        # 2. Fall back to full resolve_unknown_intent only if classifier fails
        # 3. If still unknown, try external API for execution plan
        if intent.type == IntentType.UNKNOWN:
            if self._cancelled:
                raise _CancelledError()
            from cios.core.model_router import (
                has_external_provider,
                is_any_provider_available,
                request_execution_plan,
            )

            # Try classifier first (cache hit is instant, LLM call is lightweight)
            signal_topbar_processing("Classificando…")
            classified = classify_intent(resolved_input)
            if classified:
                intent = classified
            elif is_any_provider_available():
                if self._cancelled:
                    raise _CancelledError()
                # Full LLM fallback as last resort
                signal_topbar_processing("Consultando IA…")
                resolved = resolve_unknown_intent(resolved_input)
                if self._cancelled:
                    raise _CancelledError()
                if resolved:
                    intent = resolved
                else:
                    # Ollama couldn't resolve — try external API for execution plan
                    if has_external_provider():
                        signal_topbar_processing("Gerando plano…")
                        plan = request_execution_plan(resolved_input)
                        if self._cancelled:
                            raise _CancelledError()
                        if plan:
                            signal_topbar_idle()
                            return self._execution_plan_response(plan)
                    signal_topbar_idle()
                    return self._unknown_intent_response()
            else:
                # No local LLM available — check if external API can help
                if has_external_provider():
                    signal_topbar_processing("Gerando plano…")
                    plan = request_execution_plan(resolved_input)
                    if self._cancelled:
                        raise _CancelledError()
                    if plan:
                        signal_topbar_idle()
                        return self._execution_plan_response(plan)
                signal_topbar_idle()
                return self._no_provider_response()

        # (#75) Check if intent needs clarification
        clarification = self._needs_clarification(intent)
        if clarification:
            signal_topbar_idle()
            return clarification

        # Sudo password check BEFORE confirmation — entering the password
        # already serves as implicit confirmation (no need to ask twice)
        sudo_check = self._needs_sudo_password(intent)
        if sudo_check:
            signal_topbar_idle()
            return sudo_check

        # Confirmation check for destructive actions (skipped if sudo
        # password was already provided — that counts as confirmation)
        if not confirmed:
            confirm_msg = self._needs_confirmation(intent)
            if confirm_msg:
                signal_topbar_idle()
                return self._confirm_response(confirm_msg)

        # Execute
        signal_topbar_processing("Executando…")
        result = self._execute_intent(intent, context)
        signal_topbar_idle()

        # (#74) Record turn in conversation
        self._record_turn(user_input, intent, result)

        # Learn from successful executions (feeds the classifier cache)
        if result.get("status") in ("success", "recovered"):
            learn_from_success(user_input, intent)

        return result

    def _process_streaming(
        self,
        user_input: str,
        confirmed: bool,
        on_step: Callable[[str, int, int], None] | None,
    ) -> dict:
        """Process with real-time step callbacks.

        Ensures topbar transitions: "Entendendo…" → "Executando…" → idle.
        Streams each humanized plan step via on_step as it's produced.
        Always calls signal_topbar_idle() before returning, even on
        early-exit paths (unknown intent, clarification, confirmation).
        """
        from cios.core.mcp import context
        from cios.ui.topbar import signal_topbar_idle, signal_topbar_processing

        signal_topbar_processing("Entendendo…")
        if on_step:
            on_step("Entendendo…", 0, 0)

        # ThreadManager handles routing (replaces manual _pending_question check)
        decision = self._thread_manager.route_input(user_input)

        if decision.action == "answer_pending":
            signal_topbar_idle()
            return self._handle_answer(user_input, confirmed, decision.pending_question)

        # (#76) Resolve pronouns
        resolved_input = self._resolve_pronouns(user_input)

        intent = parse_intent(resolved_input)

        # LLM fallback — hybrid model (same as _process)
        if intent.type == IntentType.UNKNOWN:
            from cios.core.model_router import is_any_provider_available

            # Try classifier first
            if on_step:
                on_step("Classificando…", 1, 0)
            classified = classify_intent(resolved_input)
            if classified:
                intent = classified
            elif is_any_provider_available():
                if on_step:
                    on_step("Consultando IA…", 1, 0)
                resolved = resolve_unknown_intent(resolved_input)
                if resolved:
                    intent = resolved
                else:
                    signal_topbar_idle()
                    return self._unknown_intent_response()
            else:
                signal_topbar_idle()
                return self._unknown_intent_response()

        # (#75) Clarification
        clarification = self._needs_clarification(intent)
        if clarification:
            signal_topbar_idle()
            return clarification

        # Sudo password check BEFORE confirmation — entering the password
        # already serves as implicit confirmation (no need to ask twice)
        sudo_check = self._needs_sudo_password(intent)
        if sudo_check:
            signal_topbar_idle()
            return sudo_check

        # Confirmation (skipped if sudo password was already provided)
        if not confirmed:
            confirm_msg = self._needs_confirmation(intent)
            if confirm_msg:
                signal_topbar_idle()
                return self._confirm_response(confirm_msg)

        if on_step:
            on_step("Executando…", 1, 0)

        # Execute
        signal_topbar_processing("Executando…")
        context.notify_activity()
        plan_result = self._execute_with_retry(intent)

        # Post-action validation
        if plan_result.outcome == "success" and intent.type in _STATE_CHANGING_INTENTS:
            self._validate_post_action(intent, plan_result, context)

        steps, summary, outcome, voice_mode = humanize_result(plan_result)

        # Stream each humanized step to the UI as it's produced
        if on_step and steps:
            total = len(steps)
            for i, step in enumerate(steps):
                on_step(step, i + 1, total)

        status = "error" if outcome == "failure" else outcome
        if status == "error" and summary:
            summary = enrich_error(summary, context={"intent": intent.type.value})

        signal_topbar_idle()

        result = {
            "steps": steps,
            "result": summary,
            "status": status,
            "confirm": None,
            "voice_mode": voice_mode,
        }

        # Merge extra structured data (e.g., gallery signal) into response
        if plan_result.data:
            result.update(plan_result.data)

        # Record turn
        self._record_turn(user_input, intent, result)

        # Learn from successful executions (feeds the classifier cache)
        if result.get("status") in ("success", "recovered"):
            learn_from_success(user_input, intent)

        return result

    def _execute_intent(self, intent: Intent, context) -> dict:
        """Execute an intent with retry, validation, and error enrichment.

        Long-running intents (package install, upgrades) are dispatched to
        the background TaskManager and return immediately with a task reference.
        """
        from cios.core.task_queue import Task, get_task_context, should_run_background

        context.notify_activity()

        # History search — handled directly (no planner needed)
        if intent.type == IntentType.HISTORY_SEARCH:
            query = intent.params.get("query", "")
            if not query:
                return {
                    "steps": [],
                    "result": "O que você quer buscar no histórico?",
                    "status": "success",
                    "confirm": None,
                    "voice_mode": "full",
                }
            results = self.search_history(query)
            if not results:
                return {
                    "steps": [],
                    "result": f"Não encontrei nada sobre '{query}' no histórico.",
                    "status": "success",
                    "confirm": None,
                    "voice_mode": "full",
                }
            # Format results conversationally
            lines = [f"Encontrei {len(results)} conversa(s) sobre '{query}':\n"]
            for r in results[:5]:
                summary = r["summary"][:60]
                lines.append(f"  • {summary}")
                if r["turns"]:
                    first_result = r["turns"][0].get("result", "")
                    if first_result:
                        lines.append(f"    → {first_result[:50]}")
            return {
                "steps": [],
                "result": "\n".join(lines),
                "status": "success",
                "confirm": None,
                "voice_mode": "brief",
            }

        # Check if this should run in background
        if should_run_background(intent.type.value, intent.params):
            task = Task(
                description=self._describe_intent(intent),
                context=get_task_context(intent.type.value),
            )

            # Capture intent and dependencies for background execution
            planner = self._planner

            def execute_fn(t: Task) -> dict:
                t.add_progress(f"Executando: {t.description}", 10.0)
                plan_result = planner.execute(intent)
                t.add_progress("Finalizando...", 90.0)

                steps, summary, outcome, voice_mode = humanize_result(plan_result)
                return {
                    "steps": steps,
                    "result": summary,
                    "status": "error" if outcome == "failure" else outcome,
                    "voice_mode": voice_mode,
                }

            task._execute_fn = execute_fn
            task_id = self._task_manager.submit(task)

            return {
                "steps": [f"⟳ {task.description}"],
                "result": f"Executando em background... (task {task_id})",
                "status": "background",
                "confirm": None,
                "voice_mode": "brief",
                "task_id": task_id,
            }

        # Synchronous execution for fast operations
        plan_result = self._execute_with_retry(intent)

        # Post-action validation
        if plan_result.outcome == "success" and intent.type in _STATE_CHANGING_INTENTS:
            self._validate_post_action(intent, plan_result, context)

        steps, summary, outcome, voice_mode = humanize_result(plan_result)
        status = "error" if outcome == "failure" else outcome

        if status == "error" and summary:
            summary = enrich_error(summary, context={"intent": intent.type.value})

        result = {
            "steps": steps,
            "result": summary,
            "status": status,
            "confirm": None,
            "voice_mode": voice_mode,
        }

        # Merge extra structured data (e.g., gallery signal) into response
        if plan_result.data:
            result.update(plan_result.data)

        return result

    def _describe_intent(self, intent: Intent) -> str:
        """Generate a human-readable description of an intent for task display."""
        action = intent.params.get("action", "")
        package = intent.params.get("package", "")

        if intent.type == IntentType.PACKAGE:
            descriptions = {
                "install": f"Instalando {package}",
                "remove": f"Removendo {package}",
                "update": "Atualizando listas de pacotes",
                "upgrade": "Atualizando sistema",
            }
            return descriptions.get(action, f"package: {action}")
        elif intent.type == IntentType.SELF_UPDATE:
            return "Atualizando CIOS"

        return f"{intent.type.value}: {action}"

    def _on_task_complete(self, task) -> None:
        """Called when a background task completes."""
        from cios.core.task_queue import TaskStatus

        status = "✓" if task.status == TaskStatus.COMPLETED else "✗"
        logger.info(
            "Background task %s %s: %s (%.1fs)",
            status,
            task.id,
            task.description,
            task.duration,
        )

    # ═══════════════════════════════════════════════════════════════════
    #  CONVERSATION CONTEXT (#74)
    # ═══════════════════════════════════════════════════════════════════

    def _record_turn(self, user_input: str, intent: Intent, result: dict) -> None:
        """Record a conversation turn for context. Delegates to ThreadManager."""
        self._thread_manager.record_turn(user_input, intent, result)

    def _get_last_turn(self) -> ConversationTurn | None:
        """Get the most recent conversation turn."""
        context_turns = self._thread_manager.get_conversation_context()
        return context_turns[-1] if context_turns else None

    # ═══════════════════════════════════════════════════════════════════
    #  CLARIFICATION QUESTIONS (#75)
    # ═══════════════════════════════════════════════════════════════════

    def _needs_clarification(self, intent: Intent) -> dict | None:
        """Check if intent is missing required info and ask for it.

        For multi-step scenarios (e.g. network connect without SSID and
        no known networks), builds a GuidedFlow with all steps upfront
        and stores them in PendingQuestion.flow_steps so _handle_answer
        can advance through them one at a time.
        """

        # AMBIGUITY: "volume" can mean audio or disk
        if intent.type in (IntentType.AUDIO, IntentType.DISK_ANALYSIS, IntentType.UNKNOWN):
            raw = intent.raw_input.lower() if hasattr(intent, "raw_input") else ""
            if not raw:
                raw = (intent.params.get("_raw", "") or "").lower()
            if "volume" in raw:
                # Check if there's a clear audio verb (aumentar, diminuir, mutar, etc.)
                audio_verbs = (
                    "aumentar",
                    "subir",
                    "diminuir",
                    "abaixar",
                    "baixar",
                    "mutar",
                    "silenciar",
                    "mute",
                    "louder",
                    "raise",
                    "lower",
                )
                has_audio_context = any(v in raw for v in audio_verbs)
                # Check if there's a clear disk context
                disk_words = ("disco", "disk", "ssd", "hd", "armazenamento", "storage", "parti")
                has_disk_context = any(w in raw for w in disk_words)

                if not has_audio_context and not has_disk_context:
                    # Ambiguous — ask user
                    self._thread_manager.set_pending_question(
                        PendingQuestion(
                            intent=intent,
                            question_type="choice",
                            options=["audio", "disco"],
                            timestamp=time.time(),
                        )
                    )
                    return {
                        "steps": [],
                        "result": "Volume de áudio ou espaço em disco?",
                        "status": "success",
                        "confirm": None,
                        "voice_mode": "full",
                    }

        # NETWORK: connect without SSID
        if intent.type == IntentType.NETWORK:
            action = intent.params.get("action", "")
            if action == "connect" and not intent.params.get("ssid"):
                from cios.core.mcp import context as mcp
                from cios.skills import network as net_skill

                # Check if already connected
                if mcp.wifi.connected:
                    return None  # MCO will handle "already connected"
                # List available networks
                networks = net_skill.list_networks()
                if networks:
                    options = [n.ssid for n in networks[:8]]
                    lines = [f"  {n.ssid} — {n.signal}%" for n in networks[:8]]
                    # Build guided flow: step 1 = pick SSID, step 2 = password (if needed)
                    flow_steps = [
                        GuidedFlowStep(
                            question="Qual rede?\n" + "\n".join(lines),
                            question_type="choice",
                            options=options,
                            param_key="ssid",
                        ),
                        GuidedFlowStep(
                            question="Senha para {ssid}?",
                            question_type="password",
                            options=[],
                            param_key="password",
                        ),
                    ]

                    self._thread_manager.set_pending_question(
                        PendingQuestion(
                            intent=intent,
                            question_type="ssid",
                            options=options,
                            timestamp=time.time(),
                            flow_steps=flow_steps,
                            flow_collected={},
                        )
                    )
                    return {
                        "steps": ["Scanning networks"],
                        "result": flow_steps[0].question,
                        "status": "success",
                        "confirm": None,
                        "voice_mode": "full",
                    }

        # APP_LAUNCH: no app specified
        if intent.type == IntentType.APP_LAUNCH:
            if not intent.params.get("app"):
                self._thread_manager.set_pending_question(
                    PendingQuestion(
                        intent=intent,
                        question_type="app",
                        timestamp=time.time(),
                    )
                )
                return {
                    "steps": [],
                    "result": "Qual app você quer abrir?",
                    "status": "success",
                    "confirm": None,
                    "voice_mode": "full",
                }

        # PROCESS_CONTROL: no port
        if intent.type == IntentType.PROCESS_CONTROL:
            if intent.params.get("port") is None and intent.params.get("action") == "kill":
                self._thread_manager.set_pending_question(
                    PendingQuestion(
                        intent=intent,
                        question_type="port",
                        timestamp=time.time(),
                    )
                )
                return {
                    "steps": [],
                    "result": "Qual porta?",
                    "status": "success",
                    "confirm": None,
                    "voice_mode": "full",
                }

        # FILE_ORGANIZE: no target
        if intent.type == IntentType.FILE_ORGANIZE:
            if not intent.params.get("target"):
                self._thread_manager.set_pending_question(
                    PendingQuestion(
                        intent=intent,
                        question_type="target",
                        options=["downloads", "desktop", "documentos"],
                        timestamp=time.time(),
                    )
                )
                return {
                    "steps": [],
                    "result": "Qual pasta? (downloads, desktop, documentos)",
                    "status": "success",
                    "confirm": None,
                    "voice_mode": "full",
                }

        # PACKAGE / SELF_UPDATE: need sudo password
        # Only ask for password AFTER confirmation (confirmed=True means user already said yes)
        if intent.type in (IntentType.PACKAGE, IntentType.SELF_UPDATE):
            action = intent.params.get("action", "")
            needs_sudo = action in ("install", "remove", "update", "upgrade")
            if intent.type == IntentType.SELF_UPDATE:
                needs_sudo = action == "update"
            if needs_sudo and not intent.params.get("sudo_password"):
                # Don't ask for password yet — let confirmation happen first
                # This method is called before confirmation check, so we skip here
                # Password will be asked via _needs_sudo_clarification after confirm
                pass

        return None

    def _handle_answer(self, answer: str, confirmed: bool, pending_question=None) -> dict:
        """Process user's answer to a pending question.

        When the pending question has flow_steps, advances through the
        guided flow one step at a time, collecting params into
        flow_collected.  Once all steps are consumed (or a step is
        skipped because it's not needed), executes the completed intent.

        Args:
            answer: The user's answer text.
            confirmed: Whether the action has been confirmed.
            pending_question: The pending question from the routing decision,
                              or None to retrieve from thread manager.
        """
        from cios.core.mcp import context

        # Get the pending question — either passed from routing decision or cleared from thread manager
        question = pending_question
        if question is None:
            question = self._thread_manager.clear_pending_question()
        else:
            # Clear it from the thread manager since we're handling it now
            self._thread_manager.clear_pending_question()

        if not question:
            return self._process(answer, confirmed)

        # Check if answer is too old (>60s)
        if time.time() - question.timestamp > 60:
            # Expired — treat as new command
            return self._process(answer, confirmed)

        intent = question.intent
        answer_clean = answer.strip()

        # --- Multi-step guided flow path ---
        if question.flow_steps is not None:
            return self._advance_guided_flow(question, answer_clean, confirmed)

        # --- Legacy single-question path (backward compatible) ---
        # Inject answer into intent params based on question type
        if question.question_type == "sudo_password":
            intent.params["sudo_password"] = answer_clean
            # Execute directly (already confirmed)
            result = self._execute_intent(intent, context)
            self._record_turn("[senha]", intent, result)
            return result

        elif question.question_type == "ssid":
            # User might say the SSID name or a number (index)
            if answer_clean.isdigit() and question.options:
                idx = int(answer_clean) - 1
                if 0 <= idx < len(question.options):
                    intent.params["ssid"] = question.options[idx]
                else:
                    intent.params["ssid"] = answer_clean
            else:
                # Match against available options (fuzzy)
                matched = self._fuzzy_match_option(answer_clean, question.options)
                intent.params["ssid"] = matched or answer_clean

        elif question.question_type == "password":
            intent.params["password"] = answer_clean

        elif question.question_type == "app":
            intent.params["app"] = answer_clean

        elif question.question_type == "port":
            # Extract number from answer
            port_match = re.search(r"(\d{2,5})", answer_clean)
            if port_match:
                intent.params["port"] = int(port_match.group(1))
            else:
                return {
                    "steps": [],
                    "result": "Não entendi a porta. Diga um número, ex: 3000",
                    "status": "error",
                    "confirm": None,
                    "voice_mode": "full",
                }

        elif question.question_type == "target":
            intent.params["target"] = answer_clean

        elif question.question_type == "choice":
            # Ambiguity resolution — user picks between options
            answer_lower = answer_clean.lower()
            if question.options:
                matched = self._fuzzy_match_option(answer_lower, question.options)
                if matched == "audio" or "áudio" in answer_lower or "som" in answer_lower:
                    # Re-classify as audio status check
                    intent = Intent(
                        type=IntentType.AUDIO,
                        confidence=0.95,
                        params={"action": "status"},
                        raw_input=intent.raw_input,
                    )
                elif matched == "disco" or "disco" in answer_lower or "disk" in answer_lower:
                    # Re-classify as disk analysis
                    intent = Intent(
                        type=IntentType.DISK_ANALYSIS,
                        confidence=0.95,
                        params={"action": "analyze"},
                        raw_input=intent.raw_input,
                    )
                else:
                    # Couldn't resolve — treat answer as new input
                    return self._process(answer_clean, confirmed)

        # Now check if we need password for wifi
        if intent.type == IntentType.NETWORK and intent.params.get("action") == "connect":
            ssid = intent.params.get("ssid", "")
            if ssid and not intent.params.get("password"):
                # Check if it's a known network (no password needed)
                from cios.core.mcp import context as mcp

                known = [n.lower() for n in mcp.known_networks]
                if ssid.lower() not in known:
                    # Ask for password
                    self._thread_manager.set_pending_question(
                        PendingQuestion(
                            intent=intent,
                            question_type="password",
                            timestamp=time.time(),
                        )
                    )
                    return {
                        "steps": [],
                        "result": f"Senha para {ssid}?",
                        "status": "success",
                        "confirm": None,
                        "voice_mode": "full",
                    }

        # Execute with the completed intent
        result = self._execute_intent(intent, context)
        self._record_turn(answer_clean, intent, result)
        return result

    def _advance_guided_flow(
        self,
        question: PendingQuestion,
        answer: str,
        confirmed: bool,
    ) -> dict:
        """Advance through a multi-step guided flow, collecting one param per step.

        After collecting the current step's answer:
        1. Store the param in flow_collected
        2. Check if the next step should be skipped (e.g. known network → skip password)
        3. If more steps remain, set a new PendingQuestion for the next step
        4. If all steps are done, inject collected params and execute
        """
        from cios.core.mcp import context

        intent = question.intent
        flow_steps = question.flow_steps
        collected = dict(question.flow_collected)
        current_idx = 0

        # Determine which step we're answering
        # The current step is the first step whose param_key is not yet collected
        for i, step in enumerate(flow_steps):
            if step.param_key not in collected:
                current_idx = i
                break

        current_step = flow_steps[current_idx]

        # Collect the answer for the current step
        if current_step.question_type == "choice":
            # Support numeric index or fuzzy match
            if answer.isdigit() and current_step.options:
                idx = int(answer) - 1
                if 0 <= idx < len(current_step.options):
                    collected[current_step.param_key] = current_step.options[idx]
                else:
                    collected[current_step.param_key] = answer
            else:
                matched = self._fuzzy_match_option(answer, current_step.options)
                collected[current_step.param_key] = matched or answer
        elif current_step.question_type == "password" or current_step.question_type == "text":
            collected[current_step.param_key] = answer

        # Check remaining steps — skip steps that are no longer needed
        next_idx = current_idx + 1
        while next_idx < len(flow_steps):
            next_step = flow_steps[next_idx]
            if self._should_skip_flow_step(next_step, intent, collected):
                next_idx += 1
                continue
            break

        # If there are more steps, present the next question
        if next_idx < len(flow_steps):
            next_step = flow_steps[next_idx]
            # Interpolate collected values into the question text
            question_text = next_step.question.format(**collected)
            self._thread_manager.set_pending_question(
                PendingQuestion(
                    intent=intent,
                    question_type=next_step.param_key,
                    options=next_step.options,
                    timestamp=time.time(),
                    flow_steps=flow_steps,
                    flow_collected=collected,
                )
            )
            return {
                "steps": [],
                "result": question_text,
                "status": "success",
                "confirm": None,
                "voice_mode": "full",
            }

        # All steps done — inject collected params into intent and execute
        for key, value in collected.items():
            intent.params[key] = value

        result = self._execute_intent(intent, context)
        self._record_turn(answer, intent, result)
        return result

    def _should_skip_flow_step(
        self,
        step: GuidedFlowStep,
        intent: Intent,
        collected: dict,
    ) -> bool:
        """Determine if a guided flow step should be skipped.

        For example, skip the password step if the selected network is
        a known/saved network (no password needed).
        """
        if step.param_key == "password" and intent.type == IntentType.NETWORK:
            ssid = collected.get("ssid", "")
            if ssid:
                from cios.core.mcp import context as mcp

                known = [n.lower() for n in mcp.known_networks]
                if ssid.lower() in known:
                    return True  # Known network — skip password
        return False

    # ═══════════════════════════════════════════════════════════════════
    #  SUDO PASSWORD (#sudo)
    # ═══════════════════════════════════════════════════════════════════

    def _needs_sudo_password(self, intent: Intent) -> dict | None:
        """Check if intent needs sudo and password isn't provided yet.

        Called BEFORE confirmation. Entering the password serves as
        implicit confirmation for the action.
        Returns a password prompt response, or None to proceed.
        """
        if intent.params.get("sudo_password"):
            return None  # already have it

        needs_sudo = False
        if intent.type == IntentType.PACKAGE:
            needs_sudo = intent.params.get("action", "") in (
                "install",
                "remove",
                "update",
                "upgrade",
            )
        elif intent.type == IntentType.SELF_UPDATE:
            needs_sudo = intent.params.get("action", "") == "update"

        if not needs_sudo:
            return None

        from cios.skills.package_manager import needs_sudo_password

        if not needs_sudo_password():
            return None  # NOPASSWD configured, no need to ask

        # Build a contextual message so the user knows what the password is for
        action_desc = ""
        if intent.type == IntentType.PACKAGE:
            action = intent.params.get("action", "")
            package = intent.params.get("package", "")
            if action == "install":
                action_desc = f"Para instalar '{package}', "
            elif action == "remove":
                action_desc = f"Para remover '{package}', "
            elif action in ("update", "upgrade"):
                action_desc = "Para atualizar os pacotes, "
        elif intent.type == IntentType.SELF_UPDATE:
            action_desc = "Para atualizar o CIOS, "

        self._thread_manager.set_pending_question(
            PendingQuestion(
                intent=intent,
                question_type="sudo_password",
                timestamp=time.time(),
            )
        )
        return {
            "steps": [],
            "result": f"{action_desc}digite a senha de administrador:",
            "status": "success",
            "confirm": None,
            "voice_mode": "full",
            "password_prompt": True,
        }

    def _fuzzy_match_option(self, answer: str, options: list[str]) -> str | None:
        """Fuzzy match user answer against available options."""
        answer_lower = answer.lower()
        # Exact match
        for opt in options:
            if opt.lower() == answer_lower:
                return opt
        # Substring match
        for opt in options:
            if answer_lower in opt.lower() or opt.lower() in answer_lower:
                return opt
        return None

    # ═══════════════════════════════════════════════════════════════════
    #  PRONOUN RESOLUTION (#76)
    # ═══════════════════════════════════════════════════════════════════

    def _resolve_pronouns(self, user_input: str) -> str:
        """Replace pronouns with concrete references from conversation context."""
        context_turns = self._thread_manager.get_conversation_context()
        if not context_turns:
            return user_input

        # Check if input contains a pronoun
        words = set(user_input.lower().split())
        has_pronoun = bool(words & _ALL_PRONOUNS)
        if not has_pronoun:
            return user_input

        last = context_turns[-1] if context_turns else None
        if not last:
            return user_input

        # Extract the "object" from the last turn
        obj = self._extract_object(last)
        if not obj:
            return user_input

        # Replace the pronoun with the object
        result = user_input
        for pronoun in _ALL_PRONOUNS:
            # Word boundary replacement
            pattern = re.compile(r"\b" + re.escape(pronoun) + r"\b", re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(obj, result, count=1)
                logger.debug("Pronoun resolved: '%s' → '%s' (object: %s)", user_input, result, obj)
                break

        return result

    def _extract_object(self, turn: ConversationTurn) -> str | None:
        """Extract the main object/target from a conversation turn."""
        params = turn.params

        # App launch → app name
        if turn.intent_type == "app_launch":
            return params.get("app", "")

        # Network → SSID
        if turn.intent_type == "network":
            return params.get("ssid", "")

        # File organize → target folder
        if turn.intent_type == "file_organize":
            return params.get("target", "")

        # Process control → port
        if turn.intent_type == "process_control":
            port = params.get("port")
            return str(port) if port else ""

        # Package → package name
        if turn.intent_type == "package":
            return params.get("package", "")

        # Window → target
        if turn.intent_type == "window":
            return params.get("target", "")

        # Workflow → project name
        if turn.intent_type == "workflow_start":
            return params.get("project", "")

        # File search → query
        if turn.intent_type in ("files_search", "files_open"):
            return params.get("query", "")

        # Audio → try to extract from input
        if turn.intent_type == "audio":
            return ""

        # Fallback: try to extract a noun from the original input
        # Simple heuristic: last word that's not a verb/preposition
        return ""

    # ═══════════════════════════════════════════════════════════════════
    #  RETRY, VALIDATION, ERROR HANDLING
    # ═══════════════════════════════════════════════════════════════════

    def _execute_with_retry(self, intent: Intent) -> PlanResult:
        """Execute intent with automatic retry on transient failures."""
        result = self._planner.execute(intent)

        if result.outcome == "failure" and result.error and is_retryable(result.error):
            logger.info("Transient failure detected, retrying: %s", result.error[:80])
            time.sleep(0.5)
            retry_result = self._planner.execute(intent)
            if retry_result.outcome != "failure":
                retry_result.outcome = "recovered"
                return retry_result
            return result

        return result

    def _validate_post_action(self, intent: Intent, result: PlanResult, context) -> None:
        """After a state-changing action, verify MCP reflects the change."""
        time.sleep(0.3)

        if intent.type == IntentType.NETWORK:
            context.force_update_wifi()
            action = intent.params.get("action", "")
            if action == "connect" and not context.wifi.connected:
                time.sleep(1.0)
                context.force_update_wifi()
                if not context.wifi.connected:
                    result.summary += "\n⚠ Conexão pode estar instável."
                    result.outcome = "recovered"
            elif action == "disconnect" and context.wifi.connected:
                time.sleep(0.5)
                context.force_update_wifi()

        elif intent.type == IntentType.AUDIO:
            context.force_update_audio()

        elif intent.type == IntentType.POWER:
            context.force_update()

    def _graceful_error(self, e: Exception) -> dict:
        """Never show traceback. Always human message + suggestion."""
        msg = humanize_error(str(e))
        enriched = enrich_error(msg, context={"intent": "unknown"})
        return {
            "steps": [],
            "result": enriched,
            "status": "error",
            "confirm": None,
            "voice_mode": "full",
        }

    # ═══════════════════════════════════════════════════════════════════
    #  RESPONSE HELPERS
    # ═══════════════════════════════════════════════════════════════════

    def _empty_response(self) -> dict:
        return {
            "steps": [],
            "result": "",
            "status": "success",
            "confirm": None,
            "voice_mode": "full",
        }

    def _unknown_intent_response(self) -> dict:
        return {
            "steps": [],
            "result": enrich_error("Não entendi o que você quer.", context={"intent": "unknown"}),
            "status": "error",
            "confirm": None,
            "voice_mode": "full",
        }

    def _no_provider_response(self) -> dict:
        """Shown when no external API is configured and local can't resolve."""
        from cios.core.model_router import get_no_provider_message

        return {
            "steps": [],
            "result": get_no_provider_message(),
            "status": "info",
            "confirm": None,
            "voice_mode": "full",
        }

    def _execution_plan_response(self, plan: dict) -> dict:
        """Shown when external API returns an execution plan.

        The plan has: explanation, steps (shell commands), confirm (bool).
        If confirm=True, we ask the user before executing.
        If confirm=False, we could auto-execute (but for safety, always confirm).
        """
        explanation = plan.get("explanation", "")
        steps = plan.get("steps", [])
        steps_display = "\n".join(f"  $ {s}" for s in steps)

        result_text = f"{explanation}\n\n{steps_display}"

        return {
            "steps": [],
            "result": result_text,
            "status": "success",
            "confirm": {
                "message": f"{explanation}\n\nExecutar {len(steps)} comando(s)?",
                "action": "execution_plan",
                "data": {"steps": steps},
            },
            "voice_mode": "full",
        }

    def _confirm_response(self, msg: str) -> dict:
        return {
            "steps": [],
            "result": "",
            "status": "success",
            "confirm": msg,
            "voice_mode": "full",
        }

    # ═══════════════════════════════════════════════════════════════════
    #  CONFIRMATION
    # ═══════════════════════════════════════════════════════════════════

    def _needs_confirmation(self, intent) -> str | None:
        if intent.type == IntentType.FILE_ORGANIZE:
            target = intent.params.get("target", "folder")
            return f"Organize files in {target}? This will move files into folders by type."
        if intent.type == IntentType.DISK_ANALYSIS:
            if intent.params.get("action") == "clean":
                return "Clean cache and trash? This will free up disk space."
        if intent.type == IntentType.SESSION:
            from cios.skills.session_control import get_session_action, is_destructive

            action_name = intent.params.get("action", "")
            if is_destructive(action_name):
                action = get_session_action(action_name)
                desc = action.description if action else action_name
                return f"{desc}? This cannot be undone."
        if intent.type == IntentType.PACKAGE:
            action = intent.params.get("action", "")
            package = intent.params.get("package", "")
            # If we already have the sudo password, skip confirmation
            # (the password prompt already serves as confirmation)
            if intent.params.get("sudo_password"):
                return None
            if action == "install":
                return f"Instalar '{package}'?"
            if action == "remove":
                return f"Remover '{package}'?"
            if action == "upgrade":
                return "Atualizar todos os pacotes do sistema?"
        if intent.type == IntentType.SELF_UPDATE:
            action = intent.params.get("action", "")
            if action == "update":
                return "Atualizar o CIOS? Vai baixar e instalar a nova versão."
        return None

    # ═══════════════════════════════════════════════════════════════════
    #  LIFECYCLE & STATUS
    # ═══════════════════════════════════════════════════════════════════

    def close(self) -> None:
        from cios.core.mcp import context

        context.stop()
        self._memory.close()
        # Close thread manager and store
        self._thread_manager.close_active_thread()
        self._thread_store.close()

    def get_active_tasks(self) -> list[dict]:
        """Get all active background tasks with their progress."""
        tasks = self._task_manager.get_active_tasks()
        return [
            {
                "id": t.id,
                "description": t.description,
                "status": t.status.value,
                "progress": t.latest_progress,
                "duration": t.duration,
            }
            for t in tasks
        ]

    def search_history(self, query: str, limit: int = 10) -> list[dict]:
        """Search conversation history for a query string.

        Returns matching threads with their turns, ordered by recency.
        """
        threads = self._thread_store.search(query, limit=limit)
        results = []
        for t in threads:
            turns_summary = []
            for turn in t.turns[:5]:  # Max 5 turns per thread in results
                turns_summary.append(
                    {
                        "input": turn.user_input,
                        "result": turn.result_summary[:100] if turn.result_summary else "",
                    }
                )
            results.append(
                {
                    "id": t.id,
                    "summary": t.summary or (t.turns[0].user_input if t.turns else ""),
                    "created_at": t.created_at,
                    "turns": turns_summary,
                    "outcome": t.outcome,
                }
            )
        return results

    def get_task_result(self, task_id: str) -> dict | None:
        """Get the status/result of a task (running, completed, or failed)."""
        task = self._task_manager.get_task(task_id)
        if task is None:
            return None
        return {
            "id": task.id,
            "description": task.description,
            "status": task.status.value,
            "result": task.result,
            "duration": task.duration,
            "progress": task.latest_progress,
        }

    def get_system_status(self) -> dict:
        """Return current system metrics for the status panel.

        Uses MCP cached state for instant response. Falls back to
        direct psutil only for fields MCP doesn't track.
        """
        import os
        import platform

        import psutil

        # Use MCP cache for fast reads (no subprocess, no blocking)
        from cios.core.mcp import context

        state = context.snapshot()

        # Only call psutil for net counters (not cached in MCP)
        net = psutil.net_io_counters()

        return {
            "cpu_percent": round(state.system.cpu_percent, 1),
            "cpu_cores": state.system.cpu_cores,
            "mem_percent": round(state.system.mem_percent, 1),
            "mem_used_gb": round(state.system.mem_used_gb, 1),
            "mem_total_gb": round(state.system.mem_total_gb, 1),
            "disk_percent": round(state.system.disk_percent, 1),
            "disk_free_gb": round(state.system.disk_free_gb, 1),
            "disk_total_gb": round(psutil.disk_usage("/").total / (1024**3), 1),
            "net_sent_mb": round(net.bytes_sent / (1024**2), 1),
            "net_recv_mb": round(net.bytes_recv / (1024**2), 1),
            "hostname": platform.node(),
            "kernel": platform.release(),
            "user": os.environ.get("USER", "user"),
        }

    def get_recent_activity(self) -> list[dict]:
        """Return recent memory records for the activity timeline.

        Includes thread info when available.
        """
        import time as _time

        records = self._memory.recent(5)
        items = []
        for r in records:
            t = _time.strftime("%H:%M", _time.localtime(r.timestamp))
            icon = "✓" if r.outcome == "success" else ("⟳" if r.outcome == "recovered" else "✗")
            items.append(
                {
                    "time": t,
                    "text": r.user_input[:50],
                    "outcome": r.outcome,
                    "icon": icon,
                }
            )

        # Include recent thread summaries if available
        try:
            recent_threads = self._thread_manager.get_recent_threads(limit=5)
            for thread in recent_threads:
                if thread.summary:
                    t = _time.strftime("%H:%M", _time.localtime(thread.created_at))
                    icon = (
                        "✓"
                        if thread.outcome == "success"
                        else ("⟳" if thread.outcome == "recovered" else "✗")
                    )
                    items.append(
                        {
                            "time": t,
                            "text": thread.summary[:50],
                            "outcome": thread.outcome,
                            "icon": icon,
                            "thread_id": thread.id,
                        }
                    )
        except Exception:
            pass  # Thread info is optional, don't break activity feed

        return items
