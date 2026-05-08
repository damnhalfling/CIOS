"""Handler for audio/volume intents."""

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult, resilient_call
from cios.core.intent_parser import Intent
from cios.core.mcp import context as mcp
from cios.core.memory import Memory
from cios.skills import audio as audio_skill


def handle_audio(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle volume up/down/set/mute/unmute/status."""
    action = intent.params.get("action", "status")

    if action == "status":
        audio = mcp.audio
        if audio.muted:
            return PlanResult(
                plan_steps=["Checking volume"],
                results=[],
                outcome="success",
                summary=f"Audio muted (volume at {audio.volume}%)",
            )
        return PlanResult(
            plan_steps=["Checking volume"],
            results=[],
            outcome="success",
            summary=f"Volume: {audio.volume}%",
        )

    if action == "up":
        delta = intent.params.get("delta", 10)
        steps, ok, msg = resilient_call(audio_skill.change_volume, delta, skill="audio")
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if ok else "failure", summary=msg
        )

    if action == "down":
        delta = intent.params.get("delta", 10)
        steps, ok, msg = resilient_call(audio_skill.change_volume, -delta, skill="audio")
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if ok else "failure", summary=msg
        )

    if action == "set":
        level = intent.params.get("level", 50)
        steps, ok, msg = resilient_call(audio_skill.set_volume, level, skill="audio")
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if ok else "failure", summary=msg
        )

    if action == "mute":
        steps, ok, msg = resilient_call(audio_skill.mute, True, skill="audio")
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if ok else "failure", summary=msg
        )

    if action == "unmute":
        steps, ok, msg = resilient_call(audio_skill.mute, False, skill="audio")
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if ok else "failure", summary=msg
        )

    return PlanResult(
        plan_steps=["Checking volume"],
        results=[],
        outcome="failure",
        summary="Unknown audio action",
    )
