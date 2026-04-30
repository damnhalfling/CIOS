"""Skill: dev_start — detect project type, install deps, start server."""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from harmoni.core.executor import Executor, ExecResult


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
    """Check if dependencies need to be installed."""
    if project.type == "node":
        return not (Path(project.root) / "node_modules").exists()
    if project.type == "python":
        # Rough heuristic: check if venv exists
        return not (Path(project.root) / ".venv").exists() and not (
            Path(project.root) / "venv"
        ).exists()
    return False


def _is_port_in_use(port: int) -> bool:
    """Check if a port is in use using a direct socket test."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def execute_dev_start(
    executor: Executor,
    project: Optional[ProjectInfo] = None,
    directory: str = ".",
    _retry: bool = False,
) -> tuple[list[str], list[ExecResult], Optional[int]]:
    """
    Full dev_start flow: detect → install → clear port → start.
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
        time.sleep(2)  # Let the port release
        # Double-check
        if _is_port_in_use(project.port):
            # Try harder with a direct kill
            executor.run(f"kill -9 $(lsof -ti:{project.port}) 2>/dev/null || true")
            time.sleep(1)

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
            time.sleep(2)
            retry_plan, retry_results, retry_pid = execute_dev_start(
                executor, project=project, _retry=True
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
    return plan, results, proc.pid
