"""Handler for screen capture intents (screenshot, screen recording)."""

import os

from cios.core.executor import Executor
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.core.handlers._common import PlanResult


def handle_screen_capture(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle screenshot and screen recording actions."""
    from cios.skills.screen_capture import (
        take_screenshot, start_recording, stop_recording, is_recording,
    )

    action = intent.params.get("action", "")

    if action == "screenshot":
        mode = intent.params.get("mode", "full")
        delay = intent.params.get("delay", 0)

        mode_names = {"full": "tela inteira", "window": "janela ativa", "region": "área selecionada"}
        plan_step = f"Capturando {mode_names.get(mode, 'tela')}"

        ok, result = take_screenshot(mode=mode, delay=delay)
        if ok:
            filename = os.path.basename(result)
            return PlanResult(
                plan_steps=[plan_step],
                results=[], outcome="success",
                summary=f"📸 Screenshot salvo: {filename}",
                voice_mode="brief",
            )
        else:
            return PlanResult(
                plan_steps=[plan_step],
                results=[], outcome="failure",
                summary=result,
            )

    elif action == "start_recording":
        if is_recording():
            return PlanResult(
                plan_steps=["Verificando gravação"],
                results=[], outcome="success",
                summary="Já está gravando. Diga 'parar gravação' para finalizar.",
            )

        with_audio = intent.params.get("with_audio", True)
        ok, msg = start_recording(with_audio=with_audio)
        return PlanResult(
            plan_steps=["Iniciando gravação de tela"],
            results=[], outcome="success" if ok else "failure",
            summary=f"🔴 {msg}" if ok else msg,
            voice_mode="brief",
        )

    elif action == "stop_recording":
        ok, msg = stop_recording()
        return PlanResult(
            plan_steps=["Finalizando gravação"],
            results=[], outcome="success" if ok else "failure",
            summary=f"⏹ {msg}" if ok else msg,
            voice_mode="brief",
        )

    return PlanResult(
        plan_steps=["Captura de tela"],
        results=[], outcome="failure",
        summary="Não entendi. Diga 'print screen', 'gravar tela', ou 'parar gravação'.",
    )
