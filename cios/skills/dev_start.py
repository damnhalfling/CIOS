"""Skill: dev_start — detect project type, install deps, start server."""

import logging
import os
import shutil
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cios.core.executor import Executor, ExecResult
from cios.core.memory import Memory, SessionContext

logger = logging.getLogger(__name__)


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


def _detect_editor() -> Optional[str]:
    """Detect the best available code editor.

    Checks for ``code`` (VS Code), ``codium`` (VS Codium), then falls back
    to the ``VISUAL`` or ``EDITOR`` environment variables.
    Returns the command name or ``None`` if nothing is found.
    """
    for candidate in ("code", "codium"):
        if shutil.which(candidate):
            return candidate
    # Fallback to environment variables
    for var in ("VISUAL", "EDITOR"):
        editor = os.environ.get(var)
        if editor and shutil.which(editor):
            return editor
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
    project: Optional[ProjectInfo] = None,
    directory: str = ".",
    _retry: bool = False,
    memory: Optional[Memory] = None,
) -> tuple[list[str], list[ExecResult], Optional[int]]:
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
                executor, project=project, _retry=True, memory=memory,
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
