"""Handlers for media, browse, and write intents."""

import subprocess

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult, resilient_call
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.skills.app_launcher import find_app, launch_app


def handle_intent_media(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle media intents: gallery, play, stop."""
    from cios.skills.media_player import GallerySignal, play_media, scan_media, stop_playback

    media_type = intent.params.get("media_type", "video")
    action = intent.params.get("action", "")

    if action == "stop":
        ok, msg = stop_playback()
        return PlanResult(
            plan_steps=["Parando reprodução"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    if action == "gallery":
        result = scan_media(media_type=media_type)

        if result.total == 0:
            type_names = {"image": "fotos", "video": "vídeos", "audio": "músicas"}
            return PlanResult(
                plan_steps=[f"Buscando {type_names.get(media_type, 'mídia')}"],
                results=[],
                outcome="failure",
                summary="Nenhum arquivo encontrado.",
            )

        if len(result.sources) == 1:
            source_path = result.sources[0].path
        else:
            source_path = ", ".join(s.name for s in result.sources)

        signal = GallerySignal(
            source_path=source_path,
            media_type=media_type,
            total_count=result.total,
            files=result.files,
        )
        signal_data = signal.to_dict()

        return PlanResult(
            plan_steps=signal_data["steps"],
            results=[],
            outcome="success",
            summary=f"{result.total} arquivos encontrados",
            voice_mode="brief",
            data=signal_data,
        )

    if action == "play":
        result = scan_media(media_type=media_type)
        if result.total == 0:
            return PlanResult(
                plan_steps=["Buscando mídia"],
                results=[],
                outcome="failure",
                summary="Nenhum arquivo encontrado.",
            )

        ok, name = play_media(result.files[0].path)
        return PlanResult(
            plan_steps=["Reproduzindo"],
            results=[],
            outcome="success" if ok else "failure",
            summary=name if ok else f"Erro: {name}",
        )

    # Legacy: open external player
    app = find_app("vlc") or find_app("mpv") or find_app("browser") or find_app("firefox")

    if not app:
        from cios.core.humanizer import _LANG

        msg = (
            "Nenhum player encontrado. Instale com: instalar mpv"
            if _LANG == "pt"
            else "No player found. Install with: install mpv"
        )
        return PlanResult(
            plan_steps=["Looking for player"], results=[], outcome="failure", summary=msg
        )

    steps, ok, err = resilient_call(launch_app, app, skill="app_launch", retryable=False)
    return PlanResult(
        plan_steps=steps,
        results=[],
        outcome="success" if ok else "failure",
        summary=f"{app.name} aberto" if ok else f"Não consegui abrir {app.name}",
        error=err,
    )


def handle_intent_browse(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Open browser for web browsing or search."""
    query = intent.params.get("query", "")

    app = find_app("browser") or find_app("chrome") or find_app("firefox") or find_app("chromium")

    if not app:
        from cios.core.humanizer import _LANG

        msg = (
            "Nenhum navegador encontrado. Instale um com: instalar firefox"
            if _LANG == "pt"
            else "No browser found. Install one with: install firefox"
        )
        return PlanResult(
            plan_steps=["Looking for browser"], results=[], outcome="failure", summary=msg
        )

    if query:
        from urllib.parse import quote_plus

        url = f"https://www.google.com/search?q={quote_plus(query)}"
        plan_steps = [f"Searching: {query}"]
        try:
            subprocess.Popen(
                [app.exec_command.split()[0], url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return PlanResult(
                plan_steps=plan_steps,
                results=[],
                outcome="success",
                summary="Busca aberta no browser",
            )
        except Exception:
            return PlanResult(
                plan_steps=plan_steps,
                results=[],
                outcome="failure",
                summary="Não consegui abrir o browser",
            )

    steps, ok, err = resilient_call(launch_app, app, skill="app_launch", retryable=False)
    return PlanResult(
        plan_steps=steps,
        results=[],
        outcome="success" if ok else "failure",
        summary=f"{app.name} aberto" if ok else f"Não consegui abrir {app.name}",
        error=err,
    )


def handle_intent_write(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Open a text editor or office app for writing."""
    app = (
        find_app("writer")
        or find_app("libreoffice")
        or find_app("editor")
        or find_app("texto")
        or find_app("gedit")
        or find_app("kate")
    )

    if not app:
        from cios.core.humanizer import _LANG

        msg = (
            "Nenhum editor encontrado. Instale um com: instalar libreoffice"
            if _LANG == "pt"
            else "No editor found. Install one with: install libreoffice"
        )
        return PlanResult(
            plan_steps=["Looking for text editor"], results=[], outcome="failure", summary=msg
        )

    steps, ok, err = resilient_call(launch_app, app, skill="app_launch", retryable=False)
    return PlanResult(
        plan_steps=steps,
        results=[],
        outcome="success" if ok else "failure",
        summary=f"{app.name} opened" if ok else f"Couldn't open {app.name}",
        error=err,
    )


def handle_media_play(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle media_play from the Maestro orchestrator.

    Plays a URL or searches for content via yt-dlp + mpv (no browser dependency).
    Respects display_mode (sidebar/fullscreen). Uses mpv IPC for control.
    """
    from cios.skills.media_player import play_media, play_media_search

    url = intent.params.get("url", "")
    query = intent.params.get("query", "")
    display_mode = intent.params.get("_display_mode", "sidebar")

    # For search queries (music), always default to sidebar PIP
    if not url and query:
        display_mode = "sidebar"

    # Detect if "url" is actually a search query (Maestro sometimes puts search there)
    if url and not url.startswith("http") and not url.startswith("ytdl://"):
        # Maestro put a search term in url field — treat as query
        query = url.replace("ytsearch", "").replace("ytdl://", "")
        # Strip "N:" prefix (e.g., "10:offspring" → "offspring")
        if ":" in query:
            query = query.split(":", 1)[1]
        url = ""

    # If we have a real URL, play directly via mpv
    if url:
        ok, msg = play_media(url, display_mode=display_mode)
        return PlanResult(
            plan_steps=[f"Reproduzindo ({display_mode})"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    # If we have a search query, search via yt-dlp and play as playlist
    if query:
        ok, msg = play_media_search(query, display_mode=display_mode, count=10)
        return PlanResult(
            plan_steps=["Buscando música", "Tocando playlist"],
            results=[],
            outcome="success" if ok else "failure",
            summary=f"♫ {msg}" if ok else msg,
        )

    return PlanResult(
        plan_steps=[],
        results=[],
        outcome="failure",
        summary="Não sei o que tocar. Diga o que quer ouvir.",
    )


def handle_media_control(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle media_control from the Maestro orchestrator.

    Controls active media via mpv IPC: pause, resume, next, stop, fullscreen, volume.
    """
    from cios.skills.mpv_controller import (
        next_track,
        prev_track,
        set_volume,
        stop,
        toggle_fullscreen,
        toggle_pause,
    )

    action = intent.params.get("action", "")

    if action == "stop":
        ok, msg = stop()
        return PlanResult(
            plan_steps=["Parando"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    if action == "fullscreen":
        ok, msg = toggle_fullscreen()
        return PlanResult(
            plan_steps=["Tela cheia"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    if action in ("pause", "resume", "toggle"):
        ok, msg = toggle_pause()
        return PlanResult(
            plan_steps=["Pause/Resume"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    if action == "next":
        ok, msg = next_track()
        return PlanResult(
            plan_steps=["Próxima"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    if action == "prev":
        ok, msg = prev_track()
        return PlanResult(
            plan_steps=["Anterior"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    if action == "volume":
        vol = intent.params.get("volume", 50)
        ok, msg = set_volume(int(vol))
        return PlanResult(
            plan_steps=["Volume"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    return PlanResult(
        plan_steps=[],
        results=[],
        outcome="failure",
        summary=f"Ação '{action}' não reconhecida para media.",
    )
