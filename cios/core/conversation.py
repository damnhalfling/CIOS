"""Conversation management — pending questions, answer routing, thread context.

Extracted from bridge.py to keep the bridge focused on orchestration.
This module owns:
- PendingQuestion / GuidedFlowStep / GuidedFlow dataclasses
- Answer classification (what type of answer is this?)
- Guided flow advancement (multi-step question collection)
- Fuzzy option matching
- Pronoun resolution helpers
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from cios.core.intent_parser import Intent, IntentType
from cios.core.thread_manager import ConversationTurn, ThreadManager

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════════════
#  ANSWER ROUTING RESULT
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class AnswerAction:
    """Result of classifying an answer to a pending question.

    The bridge inspects `action` and performs the appropriate side-effect:
    - "cancelled": user said no → return cancel response
    - "execute": intent is ready → call _execute_intent(intent)
    - "execute_confirmed": confirmed action → call _execute_intent(intent)
    - "ask_next": need another answer → set pending + return question response
    - "delegate_process": can't handle here → re-process as new command
    - "orchestrator_resume": send answer back to orchestrator
    - "password_prompt": need password for wifi
    """

    action: str
    intent: Intent | None = None
    response: dict | None = None  # Pre-built response dict (for ask_next, cancelled, etc.)
    pending_question: PendingQuestion | None = None  # New pending question to set (for ask_next)
    answer_text: str = ""  # The (cleaned) answer text for recording


# ═══════════════════════════════════════════════════════════════════════════
#  PRONOUNS
# ═══════════════════════════════════════════════════════════════════════════

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
ALL_PRONOUNS = _PRONOUNS_PT | _PRONOUNS_EN


# ═══════════════════════════════════════════════════════════════════════════
#  CONVERSATION MANAGER
# ═══════════════════════════════════════════════════════════════════════════


class ConversationManager:
    """Manages pending questions, answer routing, and conversation context.

    Pure logic — no execution side-effects. Returns AnswerAction objects
    that bridge interprets and acts upon.
    """

    def __init__(self, thread_manager: ThreadManager) -> None:
        self._thread_manager = thread_manager

    # ─── Answer Classification ────────────────────────────────────────

    def classify_answer(
        self,
        answer: str,
        pending_question: PendingQuestion | None,
    ) -> AnswerAction:
        """Classify an answer to a pending question and return a routing action.

        This handles the pure-logic parts of answer routing:
        - Expiration check
        - Guided flow advancement
        - Param injection by question_type
        - Orchestrator resume detection

        Returns an AnswerAction that the bridge should execute.
        """
        if pending_question is None:
            # No pending question — treat as new command
            return AnswerAction(action="delegate_process", answer_text=answer)

        # Check if answer is too old (>60s)
        if time.time() - pending_question.timestamp > 60:
            return AnswerAction(action="delegate_process", answer_text=answer)

        intent = pending_question.intent
        answer_clean = answer.strip()

        # --- Multi-step guided flow path ---
        if pending_question.flow_steps is not None:
            return self._advance_guided_flow(pending_question, answer_clean)

        # --- Orchestrator mid-execution input ---
        if pending_question.question_type == "orchestrator_input":
            return AnswerAction(
                action="orchestrator_resume",
                intent=intent,
                answer_text=answer_clean,
            )

        # --- Confirmation ---
        if pending_question.question_type == "confirm_action":
            return self._handle_confirmation(intent, answer_clean)

        # --- Sudo password ---
        if pending_question.question_type == "sudo_password":
            intent.params["sudo_password"] = answer_clean
            return AnswerAction(
                action="execute",
                intent=intent,
                answer_text="[senha]",
            )

        # --- Single-question param injection ---
        return self._inject_param(pending_question, intent, answer_clean)

    # ─── Guided Flow ──────────────────────────────────────────────────

    def _advance_guided_flow(
        self,
        question: PendingQuestion,
        answer: str,
    ) -> AnswerAction:
        """Advance through a multi-step guided flow, collecting one param per step.

        After collecting the current step's answer:
        1. Store the param in flow_collected
        2. Check if the next step should be skipped
        3. If more steps remain, return ask_next with new PendingQuestion
        4. If all steps done, inject collected params and return execute
        """
        intent = question.intent
        flow_steps = question.flow_steps
        collected = dict(question.flow_collected)

        # Determine which step we're answering
        current_idx = 0
        for i, step in enumerate(flow_steps):
            if step.param_key not in collected:
                current_idx = i
                break

        current_step = flow_steps[current_idx]

        # Collect the answer for the current step
        if current_step.question_type == "choice":
            if answer.isdigit() and current_step.options:
                idx = int(answer) - 1
                if 0 <= idx < len(current_step.options):
                    collected[current_step.param_key] = current_step.options[idx]
                else:
                    collected[current_step.param_key] = answer
            else:
                matched = self.fuzzy_match_option(answer, current_step.options)
                collected[current_step.param_key] = matched or answer
        elif current_step.question_type in ("password", "text"):
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
            question_text = next_step.question.format(**collected)
            new_pending = PendingQuestion(
                intent=intent,
                question_type=next_step.param_key,
                options=next_step.options,
                timestamp=time.time(),
                flow_steps=flow_steps,
                flow_collected=collected,
            )
            return AnswerAction(
                action="ask_next",
                intent=intent,
                pending_question=new_pending,
                answer_text=answer,
                response={
                    "steps": [],
                    "result": question_text,
                    "status": "success",
                    "confirm": None,
                    "voice_mode": "full",
                },
            )

        # All steps done — inject collected params and execute
        for key, value in collected.items():
            intent.params[key] = value

        return AnswerAction(
            action="execute",
            intent=intent,
            answer_text=answer,
        )

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

    # ─── Confirmation Handling ────────────────────────────────────────

    def _handle_confirmation(self, intent: Intent, answer: str) -> AnswerAction:
        """Handle a confirm_action answer (sim/não)."""
        answer_lower = answer.lower()
        negatives = (
            "não",
            "nao",
            "no",
            "n",
            "cancela",
            "cancelar",
            "cancel",
            "nope",
            "nah",
            "nunca",
            "deixa",
            "esquece",
            "para",
        )
        if (
            answer_lower in negatives
            or answer_lower.startswith("não")
            or answer_lower.startswith("nao")
        ):
            return AnswerAction(
                action="cancelled",
                answer_text=answer,
                response={
                    "steps": [],
                    "result": "Ok, cancelado.",
                    "status": "success",
                    "confirm": None,
                    "voice_mode": "full",
                },
            )
        # Positive confirmation — re-execute with confirmed=True
        return AnswerAction(
            action="execute_confirmed",
            intent=intent,
            answer_text=answer,
        )

    # ─── Param Injection ──────────────────────────────────────────────

    def _inject_param(
        self,
        question: PendingQuestion,
        intent: Intent,
        answer: str,
    ) -> AnswerAction:
        """Inject the answer into intent params based on question_type."""
        if question.question_type == "ssid":
            if answer.isdigit() and question.options:
                idx = int(answer) - 1
                if 0 <= idx < len(question.options):
                    intent.params["ssid"] = question.options[idx]
                else:
                    intent.params["ssid"] = answer
            else:
                matched = self.fuzzy_match_option(answer, question.options)
                intent.params["ssid"] = matched or answer

        elif question.question_type == "password":
            intent.params["password"] = answer

        elif question.question_type == "app":
            intent.params["app"] = answer

        elif question.question_type == "port":
            port_match = re.search(r"(\d{2,5})", answer)
            if port_match:
                intent.params["port"] = int(port_match.group(1))
            else:
                return AnswerAction(
                    action="cancelled",
                    answer_text=answer,
                    response={
                        "steps": [],
                        "result": "Não entendi a porta. Diga um número, ex: 3000",
                        "status": "error",
                        "confirm": None,
                        "voice_mode": "full",
                    },
                )

        elif question.question_type == "target":
            intent.params["target"] = answer

        elif question.question_type == "choice":
            return self._handle_choice_answer(question, intent, answer)

        # Check if wifi connection still needs password
        if intent.type == IntentType.NETWORK and intent.params.get("action") == "connect":
            ssid = intent.params.get("ssid", "")
            if ssid and not intent.params.get("password"):
                from cios.core.mcp import context as mcp

                known = [n.lower() for n in mcp.known_networks]
                if ssid.lower() not in known:
                    new_pending = PendingQuestion(
                        intent=intent,
                        question_type="password",
                        timestamp=time.time(),
                    )
                    return AnswerAction(
                        action="ask_next",
                        intent=intent,
                        pending_question=new_pending,
                        answer_text=answer,
                        response={
                            "steps": [],
                            "result": f"Senha para {ssid}?",
                            "status": "success",
                            "confirm": None,
                            "voice_mode": "full",
                        },
                    )

        return AnswerAction(
            action="execute",
            intent=intent,
            answer_text=answer,
        )

    def _handle_choice_answer(
        self,
        question: PendingQuestion,
        intent: Intent,
        answer: str,
    ) -> AnswerAction:
        """Handle ambiguity resolution — user picks between options."""
        answer_lower = answer.lower()
        if question.options:
            matched = self.fuzzy_match_option(answer_lower, question.options)
            if matched == "audio" or "áudio" in answer_lower or "som" in answer_lower:
                intent = Intent(
                    type=IntentType.AUDIO,
                    confidence=0.95,
                    params={"action": "status"},
                    raw_input=intent.raw_input,
                )
                return AnswerAction(action="execute", intent=intent, answer_text=answer)
            elif matched == "disco" or "disco" in answer_lower or "disk" in answer_lower:
                intent = Intent(
                    type=IntentType.DISK_ANALYSIS,
                    confidence=0.95,
                    params={"action": "analyze"},
                    raw_input=intent.raw_input,
                )
                return AnswerAction(action="execute", intent=intent, answer_text=answer)
            else:
                return AnswerAction(action="delegate_process", answer_text=answer)
        return AnswerAction(action="delegate_process", answer_text=answer)

    # ─── Conversation Context ─────────────────────────────────────────

    def get_thread_context(self) -> list[ConversationTurn]:
        """Get conversation context for pronoun resolution."""
        return self._thread_manager.get_conversation_context()

    def resolve_pronouns(self, user_input: str) -> str:
        """Replace pronouns with concrete references from conversation context."""
        context_turns = self.get_thread_context()
        if not context_turns:
            return user_input

        words = set(user_input.lower().split())
        has_pronoun = bool(words & ALL_PRONOUNS)
        if not has_pronoun:
            return user_input

        last = context_turns[-1] if context_turns else None
        if not last:
            return user_input

        obj = self._extract_object(last)
        if not obj:
            return user_input

        result = user_input
        for pronoun in ALL_PRONOUNS:
            pattern = re.compile(r"\b" + re.escape(pronoun) + r"\b", re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(obj, result, count=1)
                logger.debug("Pronoun resolved: '%s' → '%s' (object: %s)", user_input, result, obj)
                break

        return result

    @staticmethod
    def _extract_object(turn: ConversationTurn) -> str | None:
        """Extract the main object/target from a conversation turn."""
        params = turn.params

        if turn.intent_type == "app_launch":
            return params.get("app", "")
        if turn.intent_type == "network":
            return params.get("ssid", "")
        if turn.intent_type == "file_organize":
            return params.get("target", "")
        if turn.intent_type == "process_control":
            port = params.get("port")
            return str(port) if port else ""
        if turn.intent_type == "package":
            return params.get("package", "")
        if turn.intent_type == "window":
            return params.get("target", "")
        if turn.intent_type == "workflow_start":
            return params.get("project", "")
        if turn.intent_type in ("files_search", "files_open"):
            return params.get("query", "")
        if turn.intent_type == "audio":
            return ""
        return ""

    # ─── Utility ──────────────────────────────────────────────────────

    @staticmethod
    def fuzzy_match_option(answer: str, options: list[str]) -> str | None:
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
