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
import time
from collections.abc import Callable

from cios.core.config import ensure_dirs
from cios.core.conversation import (
    ConversationManager,
    GuidedFlow,  # noqa: F401 — re-exported for backward compat
    GuidedFlowStep,
    PendingQuestion,
)
from cios.core.error_recovery import enrich_error, is_retryable
from cios.core.executor import Executor
from cios.core.humanizer import humanize_error, humanize_result
from cios.core.intent_classifier import classify_intent, learn_from_success
from cios.core.intent_parser import Intent, IntentType, parse_intent
from cios.core.memory import Memory
from cios.core.plan_executor import PlanExecutor
from cios.core.planner import Planner, PlanResult
from cios.core.privilege import PrivilegeManager
from cios.core.thread_manager import (
    ConversationTurn,
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
        # Conversation logic (answer routing, pronoun resolution)
        self._conversation = ConversationManager(self._thread_manager)
        # Background task execution
        from cios.core.task_queue import TaskManager

        self._task_manager = TaskManager(on_task_complete=self._on_task_complete)
        # Privilege escalation and plan execution
        self._privilege = PrivilegeManager()
        self._plan_executor = PlanExecutor(self._executor, self._privilege, self._task_manager)
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

        # Start periodic history sync (every 5 minutes, background)
        self._start_periodic_sync()

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

            # Priority 1: Ask Intelligence (fastest path when logged in)
            from cios.ui.topbar import signal_topbar_idle, signal_topbar_processing

            signal_topbar_processing("Consultando inteligência…")
            intelligence_result = self._resolve_via_intelligence(resolved_input, context)
            signal_topbar_idle()

            if intelligence_result:
                return intelligence_result

            # Priority 2: Try local classifier (cache + Ollama for CLASSIFICATION only)
            from cios.core.intelligence import intelligence

            signal_topbar_processing("Classificando…")
            classified = classify_intent(resolved_input)
            if classified:
                intent = classified
            else:
                # Neither Intelligence nor local classifier could resolve
                signal_topbar_idle()
                if not intelligence.is_logged_in:
                    return {
                        "steps": [],
                        "result": "Não consegui entender como comando. "
                        "Para perguntas e conversas, conecte ao CIOS Intelligence "
                        "(área de login na sidebar).",
                        "status": "info",
                        "confirm": None,
                        "voice_mode": "full",
                    }
                # Intelligence is logged in but query failed (network, server error)
                return {
                    "steps": [],
                    "result": "Não consegui entender este comando. Tente reformular.",
                    "status": "error",
                    "confirm": None,
                    "voice_mode": "full",
                }

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
                # Set pending question so "sim" re-executes with confirmed=True
                self._thread_manager.set_pending_question(
                    PendingQuestion(
                        intent=intent,
                        question_type="confirm_action",
                        options=["sim", "não"],
                        timestamp=time.time(),
                    )
                )
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
            # Priority 1: Ask Intelligence (shared method, no duplication)
            if on_step:
                on_step("Consultando inteligência…", 1, 0)
            intelligence_result = self._resolve_via_intelligence(resolved_input, context)
            signal_topbar_idle()

            if intelligence_result:
                return intelligence_result

            # Priority 2: Try classifier (cache + Ollama)
            from cios.core.intelligence import intelligence

            if on_step:
                on_step("Classificando…", 1, 0)
            classified = classify_intent(resolved_input)
            if classified:
                intent = classified
            else:
                # Neither Intelligence nor local classifier could resolve
                signal_topbar_idle()
                if not intelligence.is_logged_in:
                    return {
                        "steps": [],
                        "result": "Não consegui entender como comando. "
                        "Para perguntas e conversas, conecte ao CIOS Intelligence "
                        "(área de login na sidebar).",
                        "status": "info",
                        "confirm": None,
                        "voice_mode": "full",
                    }
                return {
                    "steps": [],
                    "result": "Não consegui entender este comando. Tente reformular.",
                    "status": "error",
                    "confirm": None,
                    "voice_mode": "full",
                }

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
                self._thread_manager.set_pending_question(
                    PendingQuestion(
                        intent=intent,
                        question_type="confirm_action",
                        options=["sim", "não"],
                        timestamp=time.time(),
                    )
                )
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

    def _execute_plan_steps(self, cmd: dict, original_input: str) -> dict:
        """Execute an execution plan from the Intelligence planner.

        The planner returns concrete shell steps that we run sequentially.
        If any step needs root, we ask for password first via pending_question.
        Delegates to PlanExecutor for actual execution.
        """
        params = cmd.get("params", cmd)
        steps = params.get("steps", [])
        explanation = params.get("explanation", "")

        if not steps:
            return {
                "steps": ["Plano recebido"],
                "result": explanation or "Nenhum comando a executar.",
                "status": "info",
                "confirm": None,
                "voice_mode": "full",
            }

        # Check if any step needs root
        needs_root = any(self._privilege.needs_elevation(s) for s in steps)

        if needs_root:
            if self._privilege.password_required():
                # Check if password was provided (from pending_question answer)
                sudo_password = cmd.get("params", {}).get("sudo_password", "")
                if not sudo_password:
                    # Ask for password — store plan for continuation
                    from cios.core.intent_parser import Intent, IntentType

                    plan_intent = Intent(
                        type=IntentType.COMMAND_EXEC,
                        params={
                            "_plan_steps": steps,
                            "_plan_explanation": explanation,
                            "action": "plan_execution",
                        },
                        raw_input=original_input,
                        confidence=1.0,
                    )
                    self._thread_manager.set_pending_question(
                        PendingQuestion(
                            intent=plan_intent,
                            question_type="sudo_password",
                            timestamp=time.time(),
                        )
                    )
                    return {
                        "steps": [],
                        "result": f"{explanation}\n\nPreciso da tua senha pra executar:",
                        "status": "success",
                        "confirm": None,
                        "voice_mode": "full",
                        "password_prompt": True,
                    }
            else:
                sudo_password = ""
        else:
            sudo_password = ""

        return self._run_plan_steps(steps, explanation, sudo_password)

    def _run_plan_steps(self, steps: list, explanation: str, sudo_password: str) -> dict:
        """Execute plan steps in background via PlanExecutor.

        Liberates the prompt immediately. Shows red feedback in history.
        Steps execute asynchronously with progress updates.
        Delegates entirely to PlanExecutor.
        """
        # Use sync execution for simple plans (<=3 steps, no sudo needed)
        needs_root = any(self._privilege.needs_elevation(s) for s in steps)
        if len(steps) <= 3 and not needs_root and not sudo_password:
            result = self._plan_executor.execute_sync(steps, explanation, password=sudo_password)
        else:
            result = self._plan_executor.execute(steps, explanation, password=sudo_password)

        # For sync results, show actual command output
        if result.status in ("success", "error") and result.step_results:
            output_parts = [r.output for r in result.step_results if r.output]
            display_result = "\n".join(output_parts) if output_parts else result.summary
        else:
            display_result = result.summary or f"Executando: {explanation[:80]}"

        return {
            "steps": result.steps or [f"⟳ {explanation[:60]}"],
            "result": display_result,
            "status": result.status,
            "confirm": None,
            "voice_mode": "brief",
            "task_id": result.task_id,
        }

    def _execute_multi_step(self, first_cmd: dict, original_input: str) -> dict:
        """Execute a multi-step orchestrated command sequence.

        Loop:
        1. Execute current step locally
        2. Report result back to Maestro (via intelligence.query with exec_result)
        3. Maestro returns next step, or a question for the user, or done
        4. If question → pause, set pending_question, resume on user answer
        5. Repeat until no more steps
        """
        from cios.core.intelligence import intelligence

        cmd = first_cmd
        all_steps = []
        max_steps = 10  # Safety limit

        for iteration in range(max_steps):
            step_num = cmd.get("step", iteration + 1)
            total = cmd.get("total_steps", "?")
            intent_name = cmd.get("intent", "exec")
            display_mode = cmd.get("display_mode", "foreground")

            logger.info("Multi-step [%s/%s]: intent=%s", step_num, total, intent_name)

            # Execute this step locally
            try:
                cmd_type = IntentType(intent_name)
            except ValueError:
                cmd_type = IntentType.UNKNOWN

            params = cmd.get("params", {})
            params["_display_mode"] = display_mode

            intent = Intent(
                type=cmd_type,
                params=params,
                raw_input=original_input,
                confidence=1.0,
            )

            # Execute via planner
            plan_result = self._execute_with_retry(intent)
            steps, summary, outcome, voice_mode = humanize_result(plan_result)
            all_steps.extend(steps)

            # If this was the last step, we're done
            if not cmd.get("has_next"):
                return {
                    "steps": all_steps,
                    "result": summary or cmd.get("explanation", "Concluído."),
                    "status": outcome,
                    "confirm": None,
                    "voice_mode": voice_mode,
                    "display_mode": display_mode,
                }

            # Report result back to Maestro for next step
            exec_result_msg = (
                f"[exec_result] step={step_num} outcome={outcome} output={summary[:200]}"
            )

            try:
                next_result = intelligence.query(exec_result_msg, intent="chat")
                if next_result.os_command:
                    cmd = next_result.os_command
                    # Continue loop with next step
                elif next_result.success and next_result.text:
                    text = next_result.text.strip()

                    # Detect if Maestro is asking the user a question
                    is_question = (
                        text.endswith("?")
                        or "qual " in text.lower()
                        or "escolha" in text.lower()
                        or "deseja" in text.lower()
                        or "informe" in text.lower()
                        or "which " in text.lower()
                    )

                    if is_question:
                        # Pause execution — ask user, resume when they answer
                        orchestrator_intent = Intent(
                            type=IntentType.UNKNOWN,
                            params={
                                "_orchestrator_resume": True,
                                "_steps_done": all_steps,
                                "_original_input": original_input,
                            },
                            raw_input=original_input,
                            confidence=1.0,
                        )
                        self._thread_manager.set_pending_question(
                            PendingQuestion(
                                intent=orchestrator_intent,
                                question_type="orchestrator_input",
                                timestamp=time.time(),
                            )
                        )
                        return {
                            "steps": all_steps,
                            "result": text,
                            "status": "question",
                            "confirm": None,
                            "voice_mode": "full",
                        }
                    else:
                        # Final text from Maestro (summary, no more steps)
                        return {
                            "steps": all_steps,
                            "result": text,
                            "status": "success",
                            "confirm": None,
                        }
                else:
                    # Maestro returned nothing useful
                    return {
                        "steps": all_steps,
                        "result": summary or "Concluído parcialmente.",
                        "status": outcome,
                        "confirm": None,
                    }
            except Exception as e:
                logger.warning("Multi-step: failed to get next step: %s", e)
                return {
                    "steps": all_steps,
                    "result": f"Completei {step_num} etapa(s). Erro ao continuar: {summary}",
                    "status": outcome,
                    "confirm": None,
                }

        # Safety: hit max iterations
        return {
            "steps": all_steps,
            "result": "Execução multi-step atingiu limite de segurança.",
            "status": "error",
            "confirm": None,
        }

    def _execute_intent(self, intent: Intent, context) -> dict:
        """Execute an intent with retry, validation, and error enrichment.

        Long-running intents (package install, upgrades) are dispatched to
        the background TaskManager and return immediately with a task reference.
        """
        from cios.core.task_queue import Task, get_task_context, should_run_background

        context.notify_activity()

        # Plan execution — resume after password was provided
        if intent.params.get("action") == "plan_execution" and intent.params.get("_plan_steps"):
            steps = intent.params["_plan_steps"]
            explanation = intent.params.get("_plan_explanation", "")
            sudo_password = intent.params.get("sudo_password", "")
            return self._run_plan_steps(steps, explanation, sudo_password)

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
                "result": f"Executando em background: {task.description}",
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

        # Pass display_mode and step_info from orchestrator to the UI
        display_mode = intent.params.get("_display_mode")
        step_info = intent.params.get("_step_info")
        if display_mode:
            result["display_mode"] = display_mode
        if step_info:
            result["step_info"] = step_info

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
                    # Skip ambiguity if parser already confident (>= 0.9)
                    if intent.type == IntentType.AUDIO and intent.confidence >= 0.9:
                        pass  # Parser is confident — no ambiguity needed
                    else:
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

        Delegates answer classification to ConversationManager, then acts
        on the returned AnswerAction (execute, ask_next, orchestrator, etc.).
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

        # Delegate classification to ConversationManager
        action = self._conversation.classify_answer(answer, question)

        # Act on the routing decision
        if action.action == "delegate_process":
            return self._process(answer, confirmed)

        if action.action == "cancelled":
            return action.response

        if action.action == "ask_next":
            self._thread_manager.set_pending_question(action.pending_question)
            return action.response

        if action.action == "execute_confirmed":
            result = self._execute_intent(action.intent, context)
            self._record_turn(action.answer_text, action.intent, result)
            return result

        if action.action == "orchestrator_resume":
            return self._handle_orchestrator_resume(action.intent, action.answer_text)

        if action.action == "execute":
            result = self._execute_intent(action.intent, context)
            self._record_turn(action.answer_text, action.intent, result)
            return result

        # Fallback — shouldn't happen
        return self._process(answer, confirmed)

    def _handle_orchestrator_resume(self, intent: Intent, answer: str) -> dict:
        """Handle resuming an orchestrated multi-step flow after user answered a question."""
        from cios.core.intelligence import intelligence

        try:
            result = intelligence.query(answer, intent="chat")
            if result.os_command:
                cmd = result.os_command
                if cmd.get("has_next"):
                    return self._execute_multi_step(
                        cmd, intent.params.get("_original_input", answer)
                    )
                # Single step — execute directly
                try:
                    cmd_type = IntentType(cmd.get("intent", "unknown"))
                except ValueError:
                    cmd_type = IntentType.UNKNOWN
                params = cmd.get("params", {})
                params["_display_mode"] = cmd.get("display_mode", "foreground")
                exec_intent = Intent(type=cmd_type, params=params, raw_input=answer, confidence=1.0)
                plan_result = self._execute_with_retry(exec_intent)
                steps, summary, outcome, voice_mode = humanize_result(plan_result)
                prev_steps = intent.params.get("_steps_done", [])
                return {
                    "steps": prev_steps + steps,
                    "result": summary or "Concluído.",
                    "status": outcome,
                    "confirm": None,
                    "voice_mode": voice_mode,
                }
            elif result.success and result.text:
                return {
                    "steps": intent.params.get("_steps_done", []),
                    "result": result.text,
                    "status": "success",
                    "confirm": None,
                }
        except Exception as e:
            logger.warning("Orchestrator resume failed: %s", e)
        return {
            "steps": [],
            "result": "Não consegui continuar a execução.",
            "status": "error",
            "confirm": None,
        }

    # ═══════════════════════════════════════════════════════════════════
    #  SUDO PASSWORD (#sudo)
    # ═══════════════════════════════════════════════════════════════════

    def _needs_sudo_password(self, intent: Intent) -> dict | None:
        """Check if intent needs sudo and password isn't provided yet.

        Called BEFORE confirmation. Entering the password serves as
        implicit confirmation for the action.
        Returns a password prompt response, or None to proceed.
        Delegates to PrivilegeManager for the password check.
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

        if not self._privilege.password_required():
            return None  # NOPASSWD configured, no need to ask

        # Build a contextual message so the user knows what the password is for
        action_desc = ""
        if intent.type == IntentType.PACKAGE:
            action = intent.params.get("action", "")
            package = intent.params.get("package", "")
            if action == "install":
                action_desc = f"Pra instalar o {package}, "
            elif action == "remove":
                action_desc = f"Pra remover o {package}, "
            elif action in ("update", "upgrade"):
                action_desc = "Pra atualizar os pacotes, "
        elif intent.type == IntentType.SELF_UPDATE:
            action_desc = "Pra atualizar o CIOS, "

        self._thread_manager.set_pending_question(
            PendingQuestion(
                intent=intent,
                question_type="sudo_password",
                timestamp=time.time(),
            )
        )
        return {
            "steps": [],
            "result": f"{action_desc}preciso da tua senha:",
            "status": "success",
            "confirm": None,
            "voice_mode": "full",
            "password_prompt": True,
        }

    def _fuzzy_match_option(self, answer: str, options: list[str]) -> str | None:
        """Fuzzy match user answer against available options. Delegates to ConversationManager."""
        return ConversationManager.fuzzy_match_option(answer, options)

    # ═══════════════════════════════════════════════════════════════════
    #  PRONOUN RESOLUTION (#76)
    # ═══════════════════════════════════════════════════════════════════

    def _resolve_pronouns(self, user_input: str) -> str:
        """Replace pronouns with concrete references from conversation context."""
        return self._conversation.resolve_pronouns(user_input)

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

    def _resolve_via_intelligence(self, user_input: str, context) -> dict | None:
        """Resolve an UNKNOWN intent via Intelligence API.

        Shared between _process() and _process_streaming() to avoid duplication.

        Returns:
            dict result if resolved (os_command executed or text response), or
            None if Intelligence couldn't resolve (caller should try local classifier).
        """
        from cios.core.intelligence import intelligence

        if not intelligence.is_logged_in:
            logger.info("_resolve_via_intelligence: not logged in, skipping")
            return None

        try:
            import time as _time

            t0 = _time.time()
            intel_result = intelligence.query(user_input, intent="chat")
            elapsed = _time.time() - t0
            logger.info(
                "_resolve_via_intelligence: success=%s elapsed=%.1fs os_cmd=%s",
                intel_result.success,
                elapsed,
                intel_result.os_command is not None,
            )

            # Maestro returned an OS command → execute locally
            if intel_result.os_command:
                cmd = intel_result.os_command
                logger.info("Intelligence resolved: os_command=%s", cmd.get("intent"))

                # Execution plan: sequential shell steps with confirmation
                if (
                    cmd.get("intent") == "execution_plan"
                    or cmd.get("type") == "plan"
                    or cmd.get("steps")
                ):
                    return self._execute_plan_steps(cmd, user_input)

                # Multi-step execution loop
                if cmd.get("has_next"):
                    return self._execute_multi_step(cmd, user_input)

                # Single-step: execute immediately
                display_mode = cmd.get("display_mode", "foreground")
                try:
                    cmd_type = IntentType(cmd.get("intent", "unknown"))
                except ValueError:
                    cmd_type = IntentType.UNKNOWN

                params = cmd.get("params", {})
                params["_display_mode"] = display_mode

                intent = Intent(
                    type=cmd_type,
                    params=params,
                    raw_input=user_input,
                    confidence=1.0,
                )
                result = self._execute_intent(intent, context)
                if result.get("status") in ("success", "recovered"):
                    learn_from_success(user_input, intent)
                return result

            # Maestro returned a text response (explanation, opinion, etc.)
            elif intel_result.success and intel_result.text:
                return {
                    "steps": ["Consultando inteligência"],
                    "result": intel_result.text,
                    "status": "success",
                    "confirm": None,
                }

        except Exception as e:
            logger.warning("_resolve_via_intelligence failed: %s: %s", type(e).__name__, e)

        return None  # Couldn't resolve — caller should try local classifier

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

    def _start_periodic_sync(self) -> None:
        """Start background thread that syncs history every 5 minutes."""
        import threading

        def _sync_loop():
            while True:
                time.sleep(300)  # 5 minutes
                try:
                    result = self._thread_store.full_sync()
                    if result.get("error"):
                        logger.debug("Periodic sync: %s", result["error"])
                    elif result["pushed"] or result["pulled"]:
                        logger.info(
                            "Periodic sync: pushed=%d, pulled=%d",
                            result["pushed"],
                            result["pulled"],
                        )
                except Exception as e:
                    logger.debug("Periodic sync failed: %s", e)

        t = threading.Thread(target=_sync_loop, daemon=True, name="history-sync")
        t.start()

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
