"""Handlers for development workflow intents: dev_start, workflow_start, continue_project."""

import logging
import os
import time

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult, sanitize_error
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.skills.dev_start import (
    _detect_editor,
    _is_port_in_use,
    _open_browser,
    _open_editor,
    detect_project,
    execute_dev_start,
    workflow_start,
)
from cios.skills.log_analysis import analyze_text
from cios.skills.process_control import kill_process_on_port

logger = logging.getLogger(__name__)


def handle_dev_start(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Start a development server for the current/specified project."""
    project = detect_project(intent.params.get("directory", "."))
    plan_steps, results, pid = execute_dev_start(
        executor,
        project=project,
        memory=memory,
    )

    failed = [r for r in results if not r.success]
    if failed:
        combined_output = "\n".join(r.stderr for r in failed if r.stderr)
        insight = analyze_text(combined_output, source="dev_start")

        if "port" in insight.root_cause.lower() and project.port:
            kill_plan, kill_result = kill_process_on_port(executor, project.port)
            time.sleep(1)
            retry_plan, retry_results, retry_pid = execute_dev_start(
                executor,
                project=project,
                memory=memory,
            )
            if retry_pid:
                return PlanResult(
                    plan_steps=plan_steps + kill_plan + retry_plan,
                    results=results + [kill_result] + retry_results,
                    outcome="recovered",
                    summary="Fixed port conflict and started server",
                )

        return PlanResult(
            plan_steps=plan_steps,
            results=results,
            outcome="failure",
            summary=f"Failed: {sanitize_error(insight.root_cause, 'dev_start')}. {insight.suggestion}",
            error=sanitize_error(insight.root_cause, "dev_start"),
        )

    summary = plan_steps[-1] if plan_steps else "Done"
    return PlanResult(
        plan_steps=plan_steps,
        results=results,
        outcome="success",
        summary=summary,
    )


def handle_workflow_start(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Start a development workflow for a project — thin wrapper delegating to skill."""
    project_query = intent.params.get("project", "")
    if not project_query:
        return PlanResult(
            plan_steps=["No project specified"],
            results=[],
            outcome="failure",
            summary="Which project? e.g., 'quero trabalhar no meu-app'",
        )

    result = workflow_start(project_query, executor, memory)
    return PlanResult(
        plan_steps=result.steps,
        results=[],
        outcome=result.outcome,
        summary=result.summary,
    )


def handle_continue_project(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Restore a previous workspace session."""
    project_name = intent.params.get("project", "")

    if not project_name:
        latest = memory.get_latest_session()
        if latest is None:
            return PlanResult(
                plan_steps=["Looking for recent project"],
                results=[],
                outcome="failure",
                summary="No recent projects found. Start a project first.",
                error="No sessions in memory",
            )
        session = latest
    else:
        session = memory.get_session(project_name)  # type: ignore[assignment]
        if session is None:
            all_sessions = memory.list_sessions()
            for s in all_sessions:
                if project_name.lower() in s.project_name.lower():
                    session = s
                    break

        if session is None:
            all_sessions = memory.list_sessions()
            if all_sessions:
                names = [f"  📁 {s.project_name}" for s in all_sessions[:8]]
                return PlanResult(
                    plan_steps=["Searching for project"],
                    results=[],
                    outcome="failure",
                    summary="Projeto não encontrado.\n\nProjetos disponíveis:\n" + "\n".join(names),
                    error="Project not found in sessions",
                )
            return PlanResult(
                plan_steps=["Searching for project"],
                results=[],
                outcome="failure",
                summary="Projeto não encontrado. Nenhum projeto salvo.",
                error="No sessions in memory",
            )

    plan_steps = [f"Restoring project: {session.project_name}"]

    if not os.path.exists(session.project_path):
        all_sessions = memory.list_sessions()
        suggestions = [
            f"  📁 {s.project_name}"
            for s in all_sessions
            if s.project_name != session.project_name and os.path.exists(s.project_path)
        ]
        msg = "Projeto não encontrado — o diretório foi removido."
        if suggestions:
            msg += "\n\nProjetos disponíveis:\n" + "\n".join(suggestions[:8])
        return PlanResult(
            plan_steps=plan_steps,
            results=[],
            outcome="failure",
            summary=msg,
            error="Project path does not exist",
        )

    server_running = session.server_port > 0 and _is_port_in_use(session.server_port)

    if server_running:
        plan_steps.append(f"Server already running on port {session.server_port}")
        editor_cmd = session.editor_command or _detect_editor()
        if editor_cmd:
            _open_editor(editor_cmd, session.project_path)
            plan_steps.append(f"Editor opened ({editor_cmd})")

        browser_url = session.browser_url or f"http://localhost:{session.server_port}"
        _open_browser(browser_url)
        plan_steps.append(f"Browser opened ({browser_url})")

        return PlanResult(
            plan_steps=plan_steps,
            results=[],
            outcome="success",
            summary=f"Workspace restored: {session.project_name}. Server already running.",
        )
    else:
        plan_steps.append("Server not running — starting full Dev Start")
        project = detect_project(session.project_path)
        dev_plan, dev_results, pid = execute_dev_start(
            executor,
            project=project,
            memory=memory,
        )
        plan_steps.extend(dev_plan)

        failed = [r for r in dev_results if not r.success]
        if failed:
            return PlanResult(
                plan_steps=plan_steps,
                results=dev_results,
                outcome="failure",
                summary=f"Failed to restart project {session.project_name}.",
                error=sanitize_error(
                    "; ".join(r.stderr[:100] for r in failed if r.stderr),
                    "dev_start",
                ),
            )

        return PlanResult(
            plan_steps=plan_steps,
            results=dev_results,
            outcome="success",
            summary=f"Workspace restored: {session.project_name}. Server restarted.",
        )


def handle_close_project(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Close a project: kill server processes, close related windows.

    Looks up the SessionContext for the project (or latest session),
    kills the server process, and closes editor/browser windows.
    """
    import psutil

    from cios.skills.window_control import close_window, list_windows

    project_name = intent.params.get("project", "")
    plan_steps = []

    # Find the session
    if project_name:
        session = memory.get_session(project_name)
        if session is None:
            # Fuzzy match
            all_sessions = memory.list_sessions()
            for s in all_sessions:
                if project_name.lower() in s.project_name.lower():
                    session = s
                    break
    else:
        session = memory.get_latest_session()

    if session is None:
        return PlanResult(
            plan_steps=["Buscando projeto ativo"],
            results=[],
            outcome="failure",
            summary="Nenhum projeto ativo encontrado.",
        )

    plan_steps.append(f"Fechando projeto: {session.project_name}")

    # 1. Kill server process (by PID first, then by port)
    server_killed = False

    if session.server_pid:
        try:
            proc = psutil.Process(session.server_pid)
            # Kill the process tree (server + child processes)
            children = proc.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            proc.terminate()

            # Wait briefly for graceful shutdown
            gone, alive = psutil.wait_procs([proc] + children, timeout=3)
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass

            plan_steps.append(f"Servidor encerrado (PID {session.server_pid})")
            server_killed = True
        except psutil.NoSuchProcess:
            plan_steps.append("Servidor já não estava rodando")
            server_killed = True
        except psutil.AccessDenied:
            plan_steps.append("Sem permissão para encerrar servidor")

    # Fallback: kill by port if PID didn't work
    if not server_killed and session.server_port > 0:
        if _is_port_in_use(session.server_port):
            kill_plan, kill_result = kill_process_on_port(executor, session.server_port)
            plan_steps.extend(kill_plan)
            if kill_result.success:
                server_killed = True
        else:
            plan_steps.append(f"Porta {session.server_port} já livre")
            server_killed = True

    # 2. Close related windows (editor, browser)
    windows_closed = 0

    # Close editor window (by project path in title)
    project_basename = os.path.basename(session.project_path)
    try:
        all_windows = list_windows()
        for win in all_windows:
            title_lower = win.title.lower()
            wm_lower = win.wm_class.lower()

            # Match editor windows (VS Code, Zed, etc. show project name in title)
            is_editor = any(
                ed in wm_lower or ed in title_lower
                for ed in ("code", "vscodium", "zed", "sublime", "atom", "editor")
            )
            has_project = project_basename.lower() in title_lower

            # Match browser windows with localhost:port
            is_browser = any(
                br in wm_lower or br in title_lower
                for br in ("firefox", "chrome", "chromium", "brave", "browser")
            )
            has_port = session.server_port > 0 and f"localhost:{session.server_port}" in title_lower

            should_close = (is_editor and has_project) or (is_browser and has_port)

            if should_close:
                close_window(win)
                windows_closed += 1
                plan_steps.append(f"Janela fechada: {win.title[:40]}")

    except Exception as e:
        logger.debug("Failed to close windows: %s", e)

    if windows_closed == 0:
        plan_steps.append("Nenhuma janela do projeto encontrada")

    # Build summary
    parts = [f"Projeto '{session.project_name}' encerrado."]
    if server_killed:
        parts.append("Servidor parado.")
    if windows_closed > 0:
        parts.append(f"{windows_closed} janela(s) fechada(s).")

    return PlanResult(
        plan_steps=plan_steps,
        results=[],
        outcome="success",
        summary=" ".join(parts),
    )
