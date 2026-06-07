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

    Plays a URL or searches for content, respecting display_mode (sidebar/fullscreen).
    This is the handler that makes "toca um techno" work end-to-end.
    """
    from cios.skills.media_player import play_media

    url = intent.params.get("url", "")
    query = intent.params.get("query", "")
    display_mode = intent.params.get("_display_mode", "foreground")

    # If we have a URL, play directly
    if url:
        ok, msg = play_media(url, display_mode=display_mode)
        return PlanResult(
            plan_steps=[f"Reproduzindo ({display_mode})"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    # If we have a search query, open in browser with youtube search
    if query:
        import shutil
        import subprocess

        # Try mpv + yt-dlp first (native player, respects display_mode)
        if shutil.which("mpv") and shutil.which("yt-dlp"):
            search_url = f"ytdl://ytsearch:{query}"
            ok, msg = play_media(search_url, display_mode=display_mode)
            if ok:
                return PlanResult(
                    plan_steps=[f"Buscando e reproduzindo ({display_mode})"],
                    results=[],
                    outcome="success",
                    summary=msg,
                )

        # Fallback: open YouTube search in browser (Chrome/Firefox)
        import urllib.parse

        yt_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        try:
            # Try Chrome first (most common), then firefox, then xdg-open
            browser = None
            for candidate in [
                "google-chrome-stable",
                "google-chrome",
                "chromium-browser",
                "chromium",
                "firefox",
            ]:
                if shutil.which(candidate):
                    browser = candidate
                    break

            if browser:
                subprocess.Popen(
                    [browser, yt_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            else:
                subprocess.Popen(
                    ["xdg-open", yt_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            return PlanResult(
                plan_steps=["Abrindo YouTube"],
                results=[],
                outcome="success",
                summary=f"Buscando no YouTube: {query}",
            )
        except Exception as e:
            return PlanResult(
                plan_steps=["Reproduzindo"],
                results=[],
                outcome="failure",
                summary=f"Não consegui abrir o navegador: {e}",
            )

    return PlanResult(
        plan_steps=[],
        results=[],
        outcome="failure",
        summary="Não sei o que tocar. Diga o que quer ouvir.",
    )


def handle_media_control(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle media_control from the Maestro orchestrator.

    Controls active media: pause, resume, next, stop, fullscreen.
    """
    from cios.skills.media_player import media_fullscreen, stop_playback

    action = intent.params.get("action", "")

    if action == "stop":
        ok, msg = stop_playback()
        return PlanResult(
            plan_steps=["Parando"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    if action == "fullscreen":
        ok, msg = media_fullscreen()
        return PlanResult(
            plan_steps=["Tela cheia"],
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
        )

    if action in ("pause", "resume", "toggle"):
        import subprocess

        try:
            # Send pause toggle to mpv via xdotool
            subprocess.run(
                ["xdotool", "search", "--name", "mpv", "key", "space"],
                capture_output=True,
                timeout=3,
            )
            return PlanResult(
                plan_steps=["Pause/Resume"],
                results=[],
                outcome="success",
                summary="Pause/Resume",
            )
        except Exception:
            pass

    if action == "next":
        import subprocess

        try:
            subprocess.run(
                ["xdotool", "search", "--name", "mpv", "key", "greater"],
                capture_output=True,
                timeout=3,
            )
            return PlanResult(
                plan_steps=["Próximo"],
                results=[],
                outcome="success",
                summary="Próximo",
            )
        except Exception:
            pass

    return PlanResult(
        plan_steps=[],
        results=[],
        outcome="failure",
        summary=f"Ação '{action}' não reconhecida para media.",
    )
