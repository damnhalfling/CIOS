"""Skill: dev_start — detect project type, install deps, start server."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

from cios.core.executor import ExecResult, Executor
from cios.core.memory import Memory, SessionContext

logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """Result of a workflow_start skill execution."""

    steps: list[str]
    outcome: str  # "success" | "failure" | "partial"
    summary: str
    project_path: str | None = None
    editor_opened: bool = False
    browser_opened: bool = False


@dataclass
class ContinueResult:
    """Result of a workflow_continue skill execution."""

    steps: list[str]
    outcome: str  # "success" | "failure"
    summary: str
    error: str | None = None
    results: list[ExecResult] = field(default_factory=list)


@dataclass
class ProjectInfo:
    type: str  # "node", "python", "unknown"
    root: str
    start_command: str
    install_command: str
    port: int
    package_manager: str = ""


def detect_project(directory: str = ".") -> ProjectInfo:
    """Detect project type and infer start/install commands."""
    root = os.path.abspath(directory)

    # --- Node.js ---
    pkg_json = Path(root) / "package.json"
    if pkg_json.exists():
        import json

        try:
            pkg = json.loads(pkg_json.read_text())
        except (json.JSONDecodeError, OSError):
            pkg = {}

        scripts = pkg.get("scripts", {})
        port = _detect_node_port(pkg, root)

        # Determine package manager
        if (Path(root) / "pnpm-lock.yaml").exists():
            pm = "pnpm"
        elif (Path(root) / "yarn.lock").exists():
            pm = "yarn"
        else:
            pm = "npm"

        # Determine start command
        if "dev" in scripts:
            start_cmd = f"{pm} run dev"
        elif "start" in scripts:
            start_cmd = f"{pm} start"
        elif "serve" in scripts:
            start_cmd = f"{pm} run serve"
        else:
            start_cmd = f"{pm} start"

        install_cmd = f"{pm} install"

        return ProjectInfo(
            type="node",
            root=root,
            start_command=start_cmd,
            install_command=install_cmd,
            port=port,
            package_manager=pm,
        )

    # --- Python ---
    if (Path(root) / "requirements.txt").exists() or (Path(root) / "pyproject.toml").exists():
        port = 8000
        if (Path(root) / "manage.py").exists():
            start_cmd = "python manage.py runserver"
        elif (Path(root) / "app.py").exists():
            start_cmd = "python app.py"
        elif (Path(root) / "main.py").exists():
            start_cmd = "python main.py"
        else:
            start_cmd = "python -m flask run"

        if (Path(root) / "requirements.txt").exists():
            install_cmd = "pip install -r requirements.txt"
        else:
            install_cmd = "pip install -e ."

        return ProjectInfo(
            type="python",
            root=root,
            start_command=start_cmd,
            install_command=install_cmd,
            port=port,
        )

    return ProjectInfo(
        type="unknown",
        root=root,
        start_command="",
        install_command="",
        port=0,
    )


def _detect_node_port(pkg: dict, root: str) -> int:
    """Try to detect the port from package.json scripts or common config files."""
    # Check scripts for --port flags
    for script in pkg.get("scripts", {}).values():
        if "--port" in script:
            import re

            m = re.search(r"--port[= ](\d+)", script)
            if m:
                return int(m.group(1))
        if "PORT=" in script:
            import re

            m = re.search(r"PORT=(\d+)", script)
            if m:
                return int(m.group(1))

    # Check .env
    env_file = Path(root) / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text().splitlines():
                if line.startswith("PORT="):
                    return int(line.split("=", 1)[1].strip())
        except (OSError, ValueError):
            pass

    return 3000  # Node default


def needs_install(project: ProjectInfo) -> bool:
    """Check if dependencies need to be installed.

    For Node projects, also detects stale installs by comparing
    package-lock.json mtime vs node_modules mtime.
    """
    root = Path(project.root)

    if project.type == "node":
        node_modules = root / "node_modules"
        if not node_modules.exists():
            return True
        # Stale dependency detection: if lock file is newer than node_modules,
        # dependencies have changed and need reinstalling.
        lock_file = root / "package-lock.json"
        if lock_file.exists() and node_modules.exists():
            try:
                lock_mtime = lock_file.stat().st_mtime
                nm_mtime = node_modules.stat().st_mtime
                if lock_mtime > nm_mtime:
                    return True
            except OSError:
                pass
        return False

    if project.type == "python":
        # Rough heuristic: check if venv exists
        return not (root / ".venv").exists() and not (root / "venv").exists()

    return False


def _is_port_in_use(port: int) -> bool:
    """Check if a port is in use using a direct socket test."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_port_free(port: int, timeout: float = 3.0, interval: float = 0.2) -> bool:
    """Poll until the port is free, up to *timeout* seconds.

    Returns True if the port became free, False if still in use after timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_port_in_use(port):
            return True
        time.sleep(interval)
    return not _is_port_in_use(port)


def _detect_editor() -> str | None:
    """Detect the user's preferred code editor.

    Resolution order:
    1. User config (~/.cios/config.json → "editor" key)
    2. $VISUAL environment variable
    3. $EDITOR environment variable
    4. Auto-detect from common editors installed on the system

    Returns the command name or None if nothing is found.
    """
    # 1. User config (highest priority — user's explicit choice)
    try:
        import json

        config_path = Path.home() / ".cios" / "config.json"
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            editor = config.get("editor", "")
            if editor and shutil.which(editor):
                return editor
    except Exception:
        pass

    # 2. Environment variables
    for var in ("VISUAL", "EDITOR"):
        editor = os.environ.get(var)
        if editor and shutil.which(editor):
            return editor

    # 3. Auto-detect (broad scan of common GUI editors)
    _KNOWN_EDITORS = (
        "kiro",
        "code",
        "codium",
        "zed",
        "sublime_text",
        "subl",
        "kate",
        "gedit",
        "gnome-text-editor",
        "neovide",
        "cursor",
    )
    for candidate in _KNOWN_EDITORS:
        if shutil.which(candidate):
            return candidate

    return None


def _open_editor(editor_cmd: str, project_root: str) -> None:
    """Open the editor at *project_root* in a non-blocking subprocess."""
    try:
        subprocess.Popen(
            [editor_cmd, project_root],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        logger.warning("Failed to open editor '%s' at '%s'", editor_cmd, project_root)


def _open_browser(url: str) -> None:
    """Open *url* in the default browser."""
    try:
        webbrowser.open(url)
    except Exception:
        logger.warning("Failed to open browser at '%s'", url)


def execute_dev_start(
    executor: Executor,
    project: ProjectInfo | None = None,
    directory: str = ".",
    _retry: bool = False,
    memory: Memory | None = None,
) -> tuple[list[str], list[ExecResult], int | None]:
    """
    Full dev_start flow: detect → install → clear port → start → editor → browser → persist.
    Returns (plan_steps, results, server_pid).
    If the server fails due to a port conflict, auto-retries once.
    """
    if project is None:
        project = detect_project(directory)

    if project.type == "unknown":
        return (
            ["Could not detect project type"],
            [ExecResult("detect", 1, "", "No recognized project found", 0.0)],
            None,
        )

    plan: list[str] = []
    results: list[ExecResult] = []

    # Step 1: Install if needed
    if needs_install(project):
        plan.append(f"Install dependencies ({project.install_command})")
        result = executor.run(project.install_command, cwd=project.root, timeout=180)
        results.append(result)
        if not result.success:
            return plan, results, None

    # Step 2: Check port (using direct socket test for reliability)
    if _is_port_in_use(project.port):
        plan.append(f"Port {project.port} in use — killing process")
        kill_result = executor.kill_by_port(project.port)
        results.append(kill_result)
        # Poll until port is free instead of fixed sleep
        if not _wait_for_port_free(project.port, timeout=3.0, interval=0.2):
            # Try harder with a direct kill
            executor.run(f"kill -9 $(lsof -ti:{project.port}) 2>/dev/null || true")
            _wait_for_port_free(project.port, timeout=1.0, interval=0.2)

    # Step 3: Start server
    plan.append(f"Starting server ({project.start_command})")
    proc = executor.run_background(project.start_command, cwd=project.root)
    results.append(
        ExecResult(
            command=project.start_command,
            returncode=0,
            stdout=f"Server started (PID {proc.pid})",
            stderr="",
            duration=0.0,
        )
    )

    # Step 4: Verify it's running
    time.sleep(3)
    if proc.poll() is not None:
        # Process already exited — grab output
        stdout, stderr = proc.communicate(timeout=5)
        combined = stdout + stderr

        # Check if it's a port conflict and we haven't retried yet
        if not _retry and ("EADDRINUSE" in combined or "address already in use" in combined):
            plan.append("Port conflict detected — auto-recovering")
            executor.kill_by_port(project.port)
            executor.run(f"kill -9 $(lsof -ti:{project.port}) 2>/dev/null || true")
            _wait_for_port_free(project.port, timeout=2.0, interval=0.2)
            retry_plan, retry_results, retry_pid = execute_dev_start(
                executor,
                project=project,
                _retry=True,
                memory=memory,
            )
            return plan + retry_plan, results + retry_results, retry_pid

        plan.append("Server exited immediately — check output")
        results.append(
            ExecResult(
                command="verify",
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                duration=0.0,
            )
        )
        return plan, results, None

    plan.append(f"Server running on port {project.port} (PID {proc.pid})")

    # Step 5: Open editor
    editor_cmd = _detect_editor()
    if editor_cmd:
        _open_editor(editor_cmd, project.root)
        plan.append(f"Editor opened ({editor_cmd})")
    else:
        editor_cmd = ""

    # Step 6: Open browser
    browser_url = f"http://localhost:{project.port}"
    _open_browser(browser_url)
    plan.append(f"Browser opened ({browser_url})")

    # Step 7: Persist SessionContext to Memory
    if memory is not None:
        project_name = os.path.basename(project.root)
        ctx = SessionContext(
            project_name=project_name,
            project_path=project.root,
            project_type=project.type,
            editor_command=editor_cmd or "",
            server_pid=proc.pid,
            server_port=project.port,
            browser_url=browser_url,
            start_command=project.start_command,
        )
        try:
            memory.save_session(ctx)
            plan.append("Session saved")
        except Exception:
            logger.warning("Failed to persist session context for '%s'", project_name)

    return plan, results, proc.pid


# ═══════════════════════════════════════════════════════════════════════════
#  PROJECT SCANNING (for workflow_start)
# ═══════════════════════════════════════════════════════════════════════════


def _scan_project_dirs() -> list[str]:
    """Scan common directories for projects."""
    home = os.path.expanduser("~")
    search_roots = [
        os.path.join(home, d)
        for d in (
            "Projetos",
            "projetos",
            "projects",
            "dev",
            "code",
            "src",
            "workspace",
            "repos",
            "github",
            "Development",
            "Code",
        )
    ]
    search_roots.append(home)

    markers = {
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "Makefile",
        "CMakeLists.txt",
        "Gemfile",
        "composer.json",
        ".git",
    }

    projects: list[str] = []
    seen: set[str] = set()

    for root in search_roots:
        if not os.path.isdir(root):
            continue
        try:
            for entry in os.scandir(root):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                path = entry.path
                if path in seen:
                    continue
                try:
                    contents = set(os.listdir(path))
                except PermissionError:
                    continue
                if contents & markers:
                    projects.append(path)
                    seen.add(path)
        except PermissionError:
            continue

    return sorted(projects, key=lambda p: os.path.getmtime(p), reverse=True)


def _find_project(query: str, project_dirs: list[str]) -> str | None:
    """Find the best matching project directory for a query."""
    q = query.lower().strip()

    for d in project_dirs:
        if os.path.basename(d).lower() == q:
            return d
    for d in project_dirs:
        if os.path.basename(d).lower().startswith(q):
            return d
    for d in project_dirs:
        if q in os.path.basename(d).lower():
            return d

    q_words = set(q.split())
    for d in project_dirs:
        name_words = set(os.path.basename(d).lower().replace("-", " ").replace("_", " ").split())
        if q_words & name_words:
            return d

    return None


# ═══════════════════════════════════════════════════════════════════════════
#  WORKFLOW START SKILL
# ═══════════════════════════════════════════════════════════════════════════


def workflow_start(
    project_query: str,
    executor: Executor,
    memory: Memory,
) -> WorkflowResult:
    """Full workflow_start logic — encapsulates all workflow orchestration.

    Handles:
    - Project found → detect type, open editor, optionally open browser.
    - Project not found → create dir, init git, open editor.
    - No editor found → outcome="partial" with warning.

    All I/O exceptions are caught and reflected in WorkflowResult.outcome.
    """
    try:
        return _workflow_start_inner(project_query, executor, memory)
    except Exception as exc:
        logger.exception("workflow_start failed unexpectedly: %s", exc)
        return WorkflowResult(
            steps=["Searching for project"],
            outcome="failure",
            summary=f"Erro inesperado: {exc}",
            project_path=None,
            editor_opened=False,
            browser_opened=False,
        )


def _workflow_start_inner(
    project_query: str,
    executor: Executor,
    memory: Memory,
) -> WorkflowResult:
    """Internal workflow logic — may raise on I/O errors (caught by caller)."""
    steps: list[str] = ["Searching for project"]
    project_dirs = _scan_project_dirs()
    match = _find_project(project_query, project_dirs)

    if not match:
        return _create_new_project(project_query, steps)

    # ── Found existing project ──────────────────────────────────────────
    steps.append(f"Found: {os.path.basename(match)}")
    project = detect_project(match)
    steps.append(f"Type: {project.type}")

    editor_opened = False
    editor_cmd = _detect_editor()
    if editor_cmd:
        steps.append(f"Opening in {editor_cmd}")
        _open_editor(editor_cmd, match)
        editor_opened = True

    browser_opened = _try_open_browser(project, match, steps)

    # Build summary
    parts = [f"Workspace ready: {os.path.basename(match)}"]
    if editor_opened:
        parts.append("Editor opened")
    else:
        parts.append("⚠ Nenhum editor de código encontrado no sistema")
    if browser_opened:
        parts.append(f"Browser on localhost:{project.port}")

    # Record for auto-learn
    _record_workflow(project_query, match)

    outcome = "success" if editor_opened else "partial"
    return WorkflowResult(
        steps=steps,
        outcome=outcome,
        summary="\n".join(parts),
        project_path=match,
        editor_opened=editor_opened,
        browser_opened=browser_opened,
    )


def _create_new_project(project_query: str, steps: list[str]) -> WorkflowResult:
    """Create a new project directory, init git, and open editor."""
    steps.append(f"Creating project '{project_query}'")
    home = os.path.expanduser("~")
    base_candidates = [
        os.path.join(home, "projetos"),
        os.path.join(home, "projects"),
        os.path.join(home, "dev"),
    ]
    base_dir = next(
        (d for d in base_candidates if os.path.isdir(d)),
        os.path.join(home, "projetos"),
    )

    safe_name = project_query.lower().replace(" ", "-")
    project_path = os.path.join(base_dir, safe_name)

    try:
        os.makedirs(project_path, exist_ok=True)
    except OSError as exc:
        logger.warning("Failed to create project dir: %s", exc)
        return WorkflowResult(
            steps=steps,
            outcome="failure",
            summary=f"Não consegui criar o projeto '{project_query}'",
            project_path=None,
            editor_opened=False,
            browser_opened=False,
        )

    # Create README
    readme_path = os.path.join(project_path, "README.md")
    if not os.path.exists(readme_path):
        try:
            with open(readme_path, "w") as f:
                f.write(f"# {project_query.title()}\n\n")
        except OSError:
            pass

    # Initialize git
    if shutil.which("git") and not os.path.exists(os.path.join(project_path, ".git")):
        try:
            subprocess.run(
                ["git", "init"],
                cwd=project_path,
                capture_output=True,
                timeout=10,
            )
            steps.append("Git initialized")
        except Exception:
            pass

    # Open editor
    editor_cmd = _detect_editor()
    editor_opened = False
    if editor_cmd:
        steps.append(f"Opening in {editor_cmd}")
        _open_editor(editor_cmd, project_path)
        editor_opened = True

    outcome = "success" if editor_opened else "partial"
    summary = (
        f"Projeto '{project_query}' criado e aberto no editor"
        if editor_opened
        else (
            f"Projeto '{project_query}' criado em {project_path}\n"
            "⚠ Nenhum editor de código encontrado no sistema"
        )
    )

    return WorkflowResult(
        steps=steps,
        outcome=outcome,
        summary=summary,
        project_path=project_path,
        editor_opened=editor_opened,
        browser_opened=False,
    )


def _try_open_browser(project: ProjectInfo, match: str, steps: list[str]) -> bool:
    """Attempt to open the browser for web projects. Returns True on success."""
    if project.type not in ("node", "python") or not project.port:
        return False

    from cios.skills.app_launcher import find_app

    browser_app = find_app("browser") or find_app("chrome") or find_app("firefox")
    if not browser_app:
        return False

    steps.append(f"Opening browser on port {project.port}")
    try:
        subprocess.Popen(
            [browser_app.exec_command.split()[0], f"http://localhost:{project.port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except Exception:
        return False


def _record_workflow(project_query: str, project_path: str) -> None:
    """Record the workflow execution in AutoLearner for pattern detection."""
    try:
        from cios.skills.auto_learn import AutoLearner

        learner = AutoLearner()
        learner.record_execution(
            project_query,
            "workflow_start",
            {"project": project_query, "path": project_path},
            "success",
        )
    except Exception:
        logger.debug("Failed to record workflow in AutoLearner")


# ═══════════════════════════════════════════════════════════════════════════
#  WORKFLOW CONTINUE SKILL
# ═══════════════════════════════════════════════════════════════════════════


def workflow_continue(
    project_name: str,
    executor: Executor,
    memory: Memory,
) -> ContinueResult:
    """Restore a previous workspace session — encapsulates all continue_project logic."""
    if not project_name:
        latest = memory.get_latest_session()
        if latest is None:
            return ContinueResult(
                steps=["Looking for recent project"],
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
                return ContinueResult(
                    steps=["Searching for project"],
                    outcome="failure",
                    summary="Projeto não encontrado.\n\nProjetos disponíveis:\n" + "\n".join(names),
                    error="Project not found in sessions",
                )
            return ContinueResult(
                steps=["Searching for project"],
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
        return ContinueResult(
            steps=plan_steps,
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

        return ContinueResult(
            steps=plan_steps,
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
            from cios.core.handlers._common import sanitize_error

            return ContinueResult(
                steps=plan_steps,
                results=dev_results,
                outcome="failure",
                summary=f"Failed to restart project {session.project_name}.",
                error=sanitize_error(
                    "; ".join(r.stderr[:100] for r in failed if r.stderr),
                    "dev_start",
                ),
            )

        return ContinueResult(
            steps=plan_steps,
            results=dev_results,
            outcome="success",
            summary=f"Workspace restored: {session.project_name}. Server restarted.",
        )
