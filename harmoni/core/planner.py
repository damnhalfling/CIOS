"""Planner — converts intents into executable plans and runs them.

Keeps plans to 2-5 steps. Handles one retry on failure.
Every skill call goes through _resilient_call() for retry + human error messages.
"""

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

from harmoni.core.config import MAX_RETRIES
from harmoni.core.executor import Executor, ExecResult
from harmoni.core.intent_parser import Intent, IntentType
from harmoni.core.memory import Memory, MemoryRecord
from harmoni.skills.dev_start import (
    detect_project,
    execute_dev_start,
    _is_port_in_use,
    _detect_editor,
    _open_editor,
    _open_browser,
    ProjectInfo,
)
from harmoni.skills.process_control import (
    find_process_on_port,
    kill_process_on_port,
    list_listening_ports,
)
from harmoni.skills.log_analysis import analyze_text
from harmoni.skills.file_organize import organize_directory
from harmoni.skills.system_health import check_system_health
from harmoni.skills.app_launcher import find_app, launch_app
from harmoni.skills.session_control import (
    execute_session_action,
    is_destructive,
    get_session_action,
)
from harmoni.skills import network as network_skill
from harmoni.skills import audio as audio_skill
from harmoni.skills.disk_analysis import analyze_disk, clean_safe
from harmoni.skills import power as power_skill
from harmoni.skills import package_manager as pkg_skill
from harmoni.skills import clipboard as clipboard_skill
from harmoni.skills import window_control as window_skill
from harmoni.skills import self_update as update_skill
from harmoni.skills import bluetooth as bt_skill
from harmoni.skills.explore_system import format_capabilities, list_installed_apps_grouped
from harmoni.skills.file_search import search_files, open_file, find_and_open
from harmoni.core.mcp import context as mcp

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  PROJECT SCANNING (for workflow_start)
# ═══════════════════════════════════════════════════════════════════════════

def _scan_project_dirs() -> list[str]:
    """Scan common directories for projects.

    Looks for directories containing project markers (package.json,
    pyproject.toml, Cargo.toml, go.mod, etc.)
    """
    home = os.path.expanduser("~")
    search_roots = [
        os.path.join(home, d) for d in
        ("projetos", "projects", "dev", "code", "src", "workspace",
         "repos", "github", "Development", "Code")
    ]
    # Also check home directly for top-level projects
    search_roots.append(home)

    markers = {
        "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
        "pom.xml", "build.gradle", "Makefile", "CMakeLists.txt",
        "Gemfile", "composer.json", ".git",
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
                # Check for project markers
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


def _find_project(query: str, project_dirs: list[str]) -> Optional[str]:
    """Find the best matching project directory for a query."""
    q = query.lower().strip()

    # Exact match
    for d in project_dirs:
        if os.path.basename(d).lower() == q:
            return d

    # Starts with
    for d in project_dirs:
        if os.path.basename(d).lower().startswith(q):
            return d

    # Contains
    for d in project_dirs:
        if q in os.path.basename(d).lower():
            return d

    # Fuzzy: any word matches
    q_words = set(q.split())
    for d in project_dirs:
        name_words = set(os.path.basename(d).lower().replace("-", " ").replace("_", " ").split())
        if q_words & name_words:
            return d

    return None


# ═══════════════════════════════════════════════════════════════════════════
#  ERROR SANITIZER — never leak technical details to the user
# ═══════════════════════════════════════════════════════════════════════════

def _sanitize_error(error: str, skill: str = "") -> str:
    """Strip technical noise from error messages. Never show raw stderr.

    Rules:
    - No file paths (/usr/lib/python3/...)
    - No tracebacks (File "...", line N)
    - No error codes (errno, E2BIG, ENOENT)
    - No process/PID references
    - No raw command output
    - Always return something human-readable
    """
    if not error:
        return ""

    import re

    # Strip raw stderr prefix
    cleaned = re.sub(r'\bstderr:\s*', '', error)
    # Strip file paths
    cleaned = re.sub(r'/[\w/.\-]+', '', cleaned)
    # Strip tracebacks
    cleaned = re.sub(r'File ".*?", line \d+.*', '', cleaned)
    # Strip error codes
    cleaned = re.sub(r'\b(errno|E[A-Z]{2,}|error\s*\d+)\b', '', cleaned, flags=re.I)
    # Strip PID references
    cleaned = re.sub(r'\(PID \d+\)', '', cleaned)
    cleaned = re.sub(r'PID \d+', '', cleaned)
    # Strip subprocess noise
    cleaned = re.sub(r'(subprocess|Popen|CalledProcessError).*', '', cleaned, flags=re.I)
    # Strip Python exception class names
    cleaned = re.sub(r'\b\w*(Error|Exception|Warning)\b:\s*', '', cleaned)
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # If nothing useful remains, return a generic message
    if not cleaned or len(cleaned) < 5:
        _SKILL_FALLBACKS = {
            "network": "Não consegui completar a operação de rede.",
            "audio": "Não consegui ajustar o áudio.",
            "power": "Não consegui acessar as configurações de energia.",
            "package": "Não consegui completar a operação de pacotes.",
            "window": "Não consegui controlar a janela.",
            "app_launch": "Não consegui abrir o aplicativo.",
            "clipboard": "Não consegui acessar a área de transferência.",
            "disk": "Não consegui analisar o disco.",
            "session": "Não consegui executar a ação de sessão.",
        }
        return _SKILL_FALLBACKS.get(skill, "Algo deu errado.")

    # Truncate to reasonable length
    return cleaned[:150]


def _resilient_call(
    fn: Callable[..., tuple],
    *args: Any,
    skill: str = "",
    retryable: bool = True,
    retry_delay: float = 0.5,
) -> tuple:
    """Call a skill function with retry and error sanitization.

    Wraps any skill call (fn that returns (steps, ok, msg) or similar)
    with:
    1. Try/except for unexpected crashes
    2. One retry on transient failures
    3. Error message sanitization

    Returns the same tuple the skill would return.
    """
    try:
        result = fn(*args)
    except FileNotFoundError as e:
        tool = str(e).split("'")[-2] if "'" in str(e) else "ferramenta"
        msg = f"{tool} não está instalado neste sistema."
        logger.warning("Skill %s: tool not found: %s", skill, e)
        return (["Verificando disponibilidade"], False, msg)
    except Exception as e:
        logger.exception("Skill %s: unexpected error", skill)
        msg = _sanitize_error(str(e), skill)
        return (["Executando"], False, msg)

    # If the result is a tuple with (steps, ok, msg) pattern
    if isinstance(result, tuple) and len(result) >= 2:
        # Check if second element is a bool (success flag)
        if isinstance(result[1], bool) and not result[1] and retryable:
            # Failed — retry once
            error_msg = result[2] if len(result) > 2 else ""
            if _is_transient(error_msg):
                logger.info("Skill %s: transient failure, retrying: %s", skill, error_msg[:80])
                time.sleep(retry_delay)
                try:
                    result = fn(*args)
                except Exception:
                    pass  # keep original result

        # Sanitize error message in the result
        if isinstance(result, tuple) and len(result) >= 3 and isinstance(result[1], bool) and not result[1]:
            sanitized = _sanitize_error(str(result[2]), skill)
            result = (result[0], result[1], sanitized)

    return result


def _is_transient(error: str) -> bool:
    """Check if an error is likely transient (worth retrying)."""
    if not error:
        return False
    lower = error.lower()
    return any(kw in lower for kw in (
        "timeout", "timed out", "busy", "temporarily",
        "try again", "connection reset", "resource",
        "lock", "unavailable",
    ))


@dataclass
class PlanResult:
    plan_steps: list[str]
    results: list[ExecResult]
    outcome: str  # "success" | "failure" | "recovered"
    summary: str = ""
    error: Optional[str] = None
    voice_mode: str = "full"  # "full" = speak summary, "brief" = "pronto, tá na tela"


class Planner:
    """Converts intents to actions and executes them."""

    def __init__(self, executor: Executor, memory: Memory) -> None:
        self.executor = executor
        self.memory = memory

    def execute(self, intent: Intent) -> PlanResult:
        """Execute an intent with MCO (context-aware decision layer).

        MCO flow:
        1. Consult MCP for system state
        2. Decide: execute directly / ask / suggest
        3. Route to handler
        """
        handler = {
            IntentType.DEV_START: self._handle_dev_start,
            IntentType.PROCESS_CONTROL: self._handle_process_control,
            IntentType.LOG_ANALYSIS: self._handle_log_analysis,
            IntentType.FIX_LAST_ERROR: self._handle_fix_last_error,
            IntentType.COMMAND_EXEC: self._handle_command_exec,
            IntentType.STATUS: self._handle_status,
            IntentType.FILE_ORGANIZE: self._handle_file_organize,
            IntentType.SYSTEM_HEALTH: self._handle_system_health,
            IntentType.APP_LAUNCH: self._handle_app_launch,
            IntentType.SESSION: self._handle_session,
            IntentType.NETWORK: self._handle_network,
            IntentType.AUDIO: self._handle_audio,
            IntentType.DISK_ANALYSIS: self._handle_disk,
            IntentType.POWER: self._handle_power,
            IntentType.PACKAGE: self._handle_package,
            IntentType.CLIPBOARD: self._handle_clipboard,
            IntentType.WINDOW: self._handle_window,
            IntentType.BLUETOOTH: self._handle_bluetooth,
            IntentType.SELF_UPDATE: self._handle_self_update,
            IntentType.EXPLORE_SYSTEM: self._handle_explore_system,
            IntentType.LIST_APPS: self._handle_list_apps,
            IntentType.WORKFLOW_START: self._handle_workflow_start,
            IntentType.CONTINUE_PROJECT: self._handle_continue_project,
            IntentType.INTENT_MEDIA: self._handle_intent_media,
            IntentType.INTENT_BROWSE: self._handle_intent_browse,
            IntentType.INTENT_WRITE: self._handle_intent_write,
            IntentType.FILES_SEARCH: self._handle_files_search,
            IntentType.FILES_OPEN: self._handle_files_open,
        }.get(intent.type)

        if handler is None:
            return PlanResult(
                plan_steps=["Unknown intent"],
                results=[],
                outcome="failure",
                summary="I don't understand that request.",
                error="Unknown intent type",
            )

        # MCO: context-aware pre-check
        mco_result = self._mco_precheck(intent)
        if mco_result:
            self.memory.store(MemoryRecord(
                timestamp=time.time(), user_input=intent.raw_input,
                intent=intent.type.value, plan=mco_result.plan_steps,
                commands=[], outcome=mco_result.outcome,
                error=mco_result.error, context=intent.params))
            return mco_result

        result = handler(intent)

        # Store in memory
        self.memory.store(
            MemoryRecord(
                timestamp=time.time(),
                user_input=intent.raw_input,
                intent=intent.type.value,
                plan=result.plan_steps,
                commands=[r.command for r in result.results],
                outcome=result.outcome,
                error=result.error,
                context=intent.params,
            )
        )

        return result

    # --- Handlers ---

    def _handle_dev_start(self, intent: Intent) -> PlanResult:
        project = detect_project(intent.params.get("directory", "."))
        plan_steps, results, pid = execute_dev_start(
            self.executor, project=project, memory=self.memory,
        )

        # Check if any step failed
        failed = [r for r in results if not r.success]
        if failed:
            # Analyze the failure
            combined_output = "\n".join(r.stderr for r in failed if r.stderr)
            insight = analyze_text(combined_output, source="dev_start")

            # Attempt one retry with fix
            if "port" in insight.root_cause.lower() and project.port:
                retry_plan, retry_results, retry_pid = self._retry_with_port_fix(
                    project
                )
                if retry_pid:
                    return PlanResult(
                        plan_steps=plan_steps + retry_plan,
                        results=results + retry_results,
                        outcome="recovered",
                        summary="Fixed port conflict and started server",
                    )

            return PlanResult(
                plan_steps=plan_steps,
                results=results,
                outcome="failure",
                summary=f"Failed: {_sanitize_error(insight.root_cause, 'dev_start')}. {insight.suggestion}",
                error=_sanitize_error(insight.root_cause, "dev_start"),
            )

        summary = plan_steps[-1] if plan_steps else "Done"
        return PlanResult(
            plan_steps=plan_steps,
            results=results,
            outcome="success",
            summary=summary,
        )

    def _retry_with_port_fix(self, project):
        """Kill the port and retry starting."""
        from harmoni.skills.dev_start import execute_dev_start

        kill_plan, kill_result = kill_process_on_port(self.executor, project.port)
        time.sleep(1)
        plan_steps, results, pid = execute_dev_start(
            self.executor, project=project, memory=self.memory,
        )
        return kill_plan + plan_steps, [kill_result] + results, pid

    def _handle_process_control(self, intent: Intent) -> PlanResult:
        port = intent.params.get("port")
        action = intent.params.get("action", "kill")

        if port is None:
            return PlanResult(
                plan_steps=["No port specified"],
                results=[],
                outcome="failure",
                summary="Which port? e.g., 'kill process on port 3000'",
                error="Missing port",
            )

        if action == "query":
            info = find_process_on_port(port)
            if info:
                summary = f"Port {port}: {info['name']} is using it"
            else:
                summary = f"Port {port} is free"
            return PlanResult(
                plan_steps=[f"Check port {port}"],
                results=[],
                outcome="success",
                summary=summary,
            )

        plan, result = kill_process_on_port(self.executor, port)
        return PlanResult(
            plan_steps=plan,
            results=[result],
            outcome="success" if result.success else "failure",
            summary=f"Killed process on port {port}" if result.success else f"Failed to kill process on port {port}",
            error=_sanitize_error(result.stderr, "process_control") if not result.success else None,
        )

    def _handle_log_analysis(self, intent: Intent) -> PlanResult:
        # Check memory for recent failures
        last = self.memory.last_failure()
        if last and last.error:
            combined = "\n".join(last.commands) + "\n" + (last.error or "")
            insight = analyze_text(combined, source="memory")
        else:
            # Read system logs
            from harmoni.skills.log_analysis import read_system_logs

            logs = read_system_logs(self.executor)
            insight = analyze_text(logs, source="system_logs")

        lines_display = "\n".join(insight.error_lines[:5]) if insight.error_lines else "No errors"
        summary = f"Root cause: {insight.root_cause}\nSuggestion: {insight.suggestion}"

        return PlanResult(
            plan_steps=["Read logs", "Analyze errors"],
            results=[],
            outcome="success",
            summary=f"{lines_display}\n\n{summary}",
            voice_mode="brief",
        )

    def _handle_fix_last_error(self, intent: Intent) -> PlanResult:
        last = self.memory.last_failure()
        if last is None:
            return PlanResult(
                plan_steps=["Check memory for last failure"],
                results=[],
                outcome="success",
                summary="No recent failures found in memory.",
            )

        # Analyze the stored error — combine error field, commands, and any context
        error_text = last.error or ""
        combined = error_text + "\n" + "\n".join(last.commands)
        insight = analyze_text(combined, source="memory")

        # If log analysis didn't find a specific cause, check the error string directly
        if insight.root_cause == "No errors detected" or insight.root_cause == "Unrecognized error":
            # Check if the stored error itself contains useful info
            if "port" in error_text.lower() and "in use" in error_text.lower():
                insight.root_cause = error_text
                insight.suggestion = "Kill the process using the port and retry"
            elif "module" in error_text.lower() or "not found" in error_text.lower():
                insight.root_cause = error_text
                insight.suggestion = "Reinstall dependencies"

        plan_steps = [f"Found last failure: {last.intent}", f"Root cause: {insight.root_cause}"]
        results: list[ExecResult] = []

        # Attempt automatic fix based on root cause
        if "port" in insight.root_cause.lower():
            # Extract port number
            import re

            port_match = re.search(r"(\d{4,5})", insight.root_cause)
            port = int(port_match.group(1)) if port_match else 3000
            plan_steps.append(f"Killing process on port {port}")
            kill_result = self.executor.kill_by_port(port)
            results.append(kill_result)
            time.sleep(1)

            # If the original intent was dev_start, retry it
            if last.intent == "dev_start":
                plan_steps.append("Retrying server start")
                project = detect_project(last.context.get("directory", "."))
                start_plan, start_results, pid = execute_dev_start(
                    self.executor, project=project, memory=self.memory,
                )
                plan_steps.extend(start_plan)
                results.extend(start_results)

                if pid:
                    return PlanResult(
                        plan_steps=plan_steps,
                        results=results,
                        outcome="recovered",
                        summary="Fixed port conflict and restarted server",
                    )

        elif "module" in insight.root_cause.lower() or "install" in insight.suggestion.lower():
            plan_steps.append("Reinstalling dependencies")
            project = detect_project(".")
            if project.install_command:
                install_result = self.executor.run(
                    project.install_command, cwd=project.root, timeout=180
                )
                results.append(install_result)
                if install_result.success and last.intent == "dev_start":
                    plan_steps.append("Retrying server start")
                    start_plan, start_results, pid = execute_dev_start(
                        self.executor, project=project, memory=self.memory,
                    )
                    plan_steps.extend(start_plan)
                    results.extend(start_results)
                    if pid:
                        return PlanResult(
                            plan_steps=plan_steps,
                            results=results,
                            outcome="recovered",
                            summary="Reinstalled components and restarted — running now",
                        )

        # If we couldn't auto-fix
        failed = [r for r in results if not r.success]
        if failed:
            return PlanResult(
                plan_steps=plan_steps,
                results=results,
                outcome="failure",
                summary=f"Attempted fix but failed. {insight.suggestion}",
                error=insight.root_cause,
            )

        return PlanResult(
            plan_steps=plan_steps,
            results=results,
            outcome="recovered" if results else "success",
            summary=f"Applied fix: {insight.suggestion}",
        )

    def _handle_command_exec(self, intent: Intent) -> PlanResult:
        command = intent.params.get("command", "")
        if not command:
            return PlanResult(
                plan_steps=["No command provided"],
                results=[],
                outcome="failure",
                summary="What command should I run?",
                error="Missing command",
            )

        result = self.executor.run(command)
        if result.success:
            # Summarize output without raw technical content
            output = result.stdout[:500].strip()
            summary = output if output else "Done"
        else:
            summary = _sanitize_error(result.stderr, "command")
        return PlanResult(
            plan_steps=[f"Execute: {command}"],
            results=[result],
            outcome="success" if result.success else "failure",
            summary=summary,
            error=_sanitize_error(result.stderr, "command") if not result.success else None,
        )

    def _handle_status(self, intent: Intent) -> PlanResult:
        ports = list_listening_ports()
        if ports:
            lines = [f"  :{p['port']}  {p['name']}" for p in ports[:15]]
            summary = "Listening ports:\n" + "\n".join(lines)
        else:
            summary = "No services currently listening."

        return PlanResult(
            plan_steps=["Check running services"],
            results=[],
            outcome="success",
            summary=summary,
            voice_mode="brief",
        )

    def _handle_file_organize(self, intent: Intent) -> PlanResult:
        target = intent.params.get("target", "downloads")
        # Resolve common names to paths
        path_map = {
            "downloads": "~/Downloads",
            "download": "~/Downloads",
            "desktop": "~/Desktop",
            "área de trabalho": "~/Desktop",
            "documents": "~/Documents",
            "document": "~/Documents",
            "documentos": "~/Documents",
            "documento": "~/Documents",
            "pictures": "~/Pictures",
            "picture": "~/Pictures",
            "fotos": "~/Pictures",
            "foto": "~/Pictures",
            "imagens": "~/Pictures",
            "home": "~",
            "files": ".",
            "arquivos": ".",
            "folder": ".",
            "pasta": ".",
        }
        directory = path_map.get(target, target)

        from pathlib import Path
        resolved = Path(directory).expanduser().resolve()
        if not resolved.is_dir():
            return PlanResult(
                plan_steps=[f"Looking for {target}"],
                results=[],
                outcome="failure",
                summary=f"Could not find folder: {target}",
                error=f"Directory not found: {directory}",
            )

        result = organize_directory(str(resolved))
        if result.errors:
            return PlanResult(
                plan_steps=result.plan_steps,
                results=[],
                outcome="failure",
                summary=f"Organized {result.moved} files with {len(result.errors)} errors",
                error=_sanitize_error(result.errors[0], "file_organize") if result.errors else None,
            )

        summary_parts = [f"{result.moved} files organized"]
        if result.folders_created:
            summary_parts.append(f"Created: {', '.join(result.folders_created)}")

        return PlanResult(
            plan_steps=result.plan_steps,
            results=[],
            outcome="success",
            summary=". ".join(summary_parts),
        )

    def _handle_system_health(self, intent: Intent) -> PlanResult:
        report = check_system_health()
        return PlanResult(
            plan_steps=report.plan_steps,
            results=[],
            outcome="success" if report.status == "healthy" else (
                "failure" if report.status == "critical" else "recovered"
            ),
            summary="\n".join(report.summary_lines),
            voice_mode="brief",
        )

    def _handle_app_launch(self, intent: Intent) -> PlanResult:
        app_name = intent.params.get("app", "")
        if not app_name:
            return PlanResult(
                plan_steps=["No app specified"],
                results=[],
                outcome="failure",
                summary="Which app should I open?",
                error="Missing app name",
            )

        app = find_app(app_name)
        if not app:
            return PlanResult(
                plan_steps=[f"Searching for {app_name}"],
                results=[],
                outcome="failure",
                summary=f"App not found: {app_name}",
                error=f"Could not find application matching '{app_name}'",
            )

        plan_steps, success, error = _resilient_call(
            launch_app, app, skill="app_launch", retryable=False)
        return PlanResult(
            plan_steps=plan_steps,
            results=[],
            outcome="success" if success else "failure",
            summary=f"{app.name} opened" if success else f"Failed to open {app.name}",
            error=error,
        )

    def _handle_session(self, intent: Intent) -> PlanResult:
        action_name = intent.params.get("action", "")
        if not action_name:
            return PlanResult(
                plan_steps=["No action specified"],
                results=[],
                outcome="failure",
                summary="What should I do? (shutdown, reboot, suspend, lock)",
                error="Missing session action",
            )

        action = get_session_action(action_name)
        if not action:
            return PlanResult(
                plan_steps=[f"Unknown action: {action_name}"],
                results=[],
                outcome="failure",
                summary=f"I don't know how to: {action_name}",
                error=f"Unknown session action: {action_name}",
            )

        plan_steps, success, error = _resilient_call(
            execute_session_action, action_name, skill="session", retryable=False)
        return PlanResult(
            plan_steps=plan_steps,
            results=[],
            outcome="success" if success else "failure",
            summary=action.description if success else f"Failed: {action.description}",
            error=error,
        )

    def _handle_network(self, intent: Intent) -> PlanResult:
        action = intent.params.get("action", "status")

        if action == "status":
            wifi = mcp.wifi
            if wifi.connected:
                summary = f"Connected to {wifi.ssid}"
                if wifi.ip:
                    summary += f" ({wifi.ip})"
                if wifi.signal:
                    summary += f" — Signal: {wifi.signal}%"
                return PlanResult(
                    plan_steps=["Checking Wi-Fi"],
                    results=[], outcome="success", summary=summary)
            return PlanResult(
                plan_steps=["Checking Wi-Fi"],
                results=[], outcome="success",
                summary="Not connected to any network")

        if action == "list":
            networks = network_skill.list_networks()
            if not networks:
                return PlanResult(
                    plan_steps=["Scanning networks"],
                    results=[], outcome="success",
                    summary="No Wi-Fi networks found")
            lines = []
            for n in networks[:10]:
                status = " ✓" if n.active else ""
                lines.append(f"  {n.ssid} — {n.signal}% ({n.security}){status}")
            return PlanResult(
                plan_steps=["Scanning networks"],
                results=[], outcome="success",
                summary="Available networks:\n" + "\n".join(lines))

        if action == "disconnect":
            steps, ok, msg = _resilient_call(
                network_skill.disconnect, skill="network")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "connect":
            ssid = intent.params.get("ssid", "")
            password = intent.params.get("password", "")

            # MCO logic: context-aware connection
            wifi = mcp.wifi

            # Already connected to this network?
            if wifi.connected and ssid and wifi.ssid.lower() == ssid.lower():
                return PlanResult(
                    plan_steps=["Checking connection"],
                    results=[], outcome="success",
                    summary=f"Already connected to {wifi.ssid}")

            # No SSID specified — try known networks
            if not ssid:
                available = network_skill.list_networks()
                known = set(n.lower() for n in mcp.known_networks)
                # Find a known network that's available
                for net in available:
                    if net.ssid.lower() in known:
                        ssid = net.ssid
                        break

                if not ssid:
                    # No known network available — list what's there
                    if available:
                        lines = [f"  {n.ssid} — {n.signal}%" for n in available[:8]]
                        return PlanResult(
                            plan_steps=["Scanning networks"],
                            results=[], outcome="success",
                            summary="No known networks found. Available:\n"
                                    + "\n".join(lines))
                    return PlanResult(
                        plan_steps=["Scanning networks"],
                        results=[], outcome="failure",
                        summary="No Wi-Fi networks found")

            steps, ok, msg = _resilient_call(
                network_skill.connect, ssid, password, skill="network")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure",
                summary=msg,
                error=None if ok else msg)

        return PlanResult(
            plan_steps=["Checking Wi-Fi"], results=[], outcome="failure",
            summary="Unknown network action")

    def _handle_audio(self, intent: Intent) -> PlanResult:
        action = intent.params.get("action", "status")

        if action == "status":
            audio = mcp.audio
            if audio.muted:
                return PlanResult(
                    plan_steps=["Checking volume"],
                    results=[], outcome="success",
                    summary=f"Audio muted (volume at {audio.volume}%)")
            return PlanResult(
                plan_steps=["Checking volume"],
                results=[], outcome="success",
                summary=f"Volume: {audio.volume}%")

        if action == "up":
            delta = intent.params.get("delta", 10)
            steps, ok, msg = _resilient_call(
                audio_skill.change_volume, delta, skill="audio")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "down":
            delta = intent.params.get("delta", 10)
            steps, ok, msg = _resilient_call(
                audio_skill.change_volume, -delta, skill="audio")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "set":
            level = intent.params.get("level", 50)
            steps, ok, msg = _resilient_call(
                audio_skill.set_volume, level, skill="audio")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "mute":
            steps, ok, msg = _resilient_call(
                audio_skill.mute, True, skill="audio")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "unmute":
            steps, ok, msg = _resilient_call(
                audio_skill.mute, False, skill="audio")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        return PlanResult(
            plan_steps=["Checking volume"], results=[], outcome="failure",
            summary="Unknown audio action")

    def _handle_disk(self, intent: Intent) -> PlanResult:
        action = intent.params.get("action", "analyze")

        if action == "clean":
            steps, freed, errors = clean_safe()
            if errors:
                return PlanResult(
                    plan_steps=steps, results=[],
                    outcome="recovered" if freed > 0 else "failure",
                    summary=f"Freed {freed // (1024*1024)}MB with {len(errors)} errors",
                    error=_sanitize_error(errors[0], "disk") if errors else None)
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success",
                summary=f"Freed {freed // (1024*1024)}MB")

        # Default: analyze
        report = analyze_disk()
        return PlanResult(
            plan_steps=report.plan_steps,
            results=[],
            outcome="success" if report.percent_used < 90 else "warning",
            summary="\n".join(report.summary_lines),
            voice_mode="brief")

    def _handle_power(self, intent: Intent) -> PlanResult:
        action = intent.params.get("action", "battery_status")

        if action == "battery_status":
            # Use MCP for instant response
            bat = mcp.battery
            if not bat.present:
                return PlanResult(
                    plan_steps=["Checking battery"], results=[],
                    outcome="success",
                    summary="No battery detected — running on AC power")
            pct = bat.percent
            if bat.charging:
                summary = f"Battery: {pct}% ⚡ Charging"
            else:
                summary = f"Battery: {pct}%"
                if bat.time_remaining:
                    summary += f" — {bat.time_remaining} remaining"
            if pct < 15:
                summary += "\n⚠ Battery critically low!"
            elif pct < 30:
                summary += "\n⚠ Battery getting low"
            return PlanResult(
                plan_steps=["Checking battery"], results=[],
                outcome="success", summary=summary)

        if action == "brightness_status":
            level = power_skill.get_brightness()
            if level < 0:
                return PlanResult(
                    plan_steps=["Checking brightness"], results=[],
                    outcome="failure",
                    summary="Brightness control not available")
            return PlanResult(
                plan_steps=["Checking brightness"], results=[],
                outcome="success", summary=f"Brightness: {level}%")

        if action == "brightness_up":
            delta = intent.params.get("delta", 10)
            steps, ok, msg = _resilient_call(
                power_skill.change_brightness, delta, skill="power")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "brightness_down":
            delta = intent.params.get("delta", 10)
            steps, ok, msg = _resilient_call(
                power_skill.change_brightness, -delta, skill="power")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "brightness_set":
            level = intent.params.get("level", 50)
            steps, ok, msg = _resilient_call(
                power_skill.set_brightness, level, skill="power")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "power_saving":
            steps, ok, msg = _resilient_call(
                power_skill.enable_power_saving, skill="power")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        return PlanResult(
            plan_steps=["Checking battery"], results=[], outcome="failure",
            summary="Unknown power action")

    def _handle_package(self, intent: Intent) -> PlanResult:
        action = intent.params.get("action", "search")
        package = intent.params.get("package", "")
        password = intent.params.get("sudo_password", "")

        if action == "install":
            if not package:
                return PlanResult(
                    plan_steps=["No package specified"], results=[],
                    outcome="failure",
                    summary="Which package should I install?")
            result = pkg_skill.install_package(package, password=password)
            return PlanResult(
                plan_steps=result.plan_steps, results=[],
                outcome="success" if result.success else "failure",
                summary=result.message)

        if action == "remove":
            if not package:
                return PlanResult(
                    plan_steps=["No package specified"], results=[],
                    outcome="failure",
                    summary="Which package should I remove?")
            result = pkg_skill.remove_package(package, password=password)
            return PlanResult(
                plan_steps=result.plan_steps, results=[],
                outcome="success" if result.success else "failure",
                summary=result.message)

        if action == "search":
            if not package:
                return PlanResult(
                    plan_steps=["No search query"], results=[],
                    outcome="failure",
                    summary="What package are you looking for?")
            result = pkg_skill.search_packages(package)
            if result.packages:
                lines = []
                for p in result.packages[:8]:
                    status = " ✓" if p.installed else ""
                    lines.append(f"  {p.name}{status} — {p.description[:50]}")
                summary = f"Found {len(result.packages)} packages:\n" + "\n".join(lines)
            else:
                summary = result.message
            return PlanResult(
                plan_steps=result.plan_steps, results=[],
                outcome="success" if result.success else "failure",
                summary=summary, voice_mode="brief")

        if action == "update":
            result = pkg_skill.update_lists(password=password)
            return PlanResult(
                plan_steps=result.plan_steps, results=[],
                outcome="success" if result.success else "failure",
                summary=result.message)

        if action == "upgrade":
            result = pkg_skill.upgrade_packages(password=password)
            return PlanResult(
                plan_steps=result.plan_steps, results=[],
                outcome="success" if result.success else "failure",
                summary=result.message)

        return PlanResult(
            plan_steps=["Checking packages"], results=[], outcome="failure",
            summary="Unknown package action")

    def _handle_clipboard(self, intent: Intent) -> PlanResult:
        action = intent.params.get("action", "current")
        cb = clipboard_skill.CognitiveClipboard()

        if action == "current":
            content = cb.get_current()
            if content:
                content_type = clipboard_skill.detect_content_type(content)
                preview = content[:200]
                summary = f"Clipboard ({content_type}):\n{preview}"
                # Suggest actions
                actions = cb.suggest_actions(content)
                if actions:
                    summary += "\n\nSuggested actions:"
                    for a in actions[:3]:
                        summary += f"\n  {a.icon} {a.label}"
            else:
                summary = "Clipboard is empty"
            return PlanResult(
                plan_steps=["Checking clipboard"], results=[],
                outcome="success", summary=summary, voice_mode="brief")

        if action == "history":
            items = cb.get_history(10)
            if not items:
                return PlanResult(
                    plan_steps=["Checking history"], results=[],
                    outcome="success", summary="No clipboard history")
            lines = []
            for i, item in enumerate(items):
                lines.append(f"  {i+1}. [{item.content_type}] {item.preview}")
            return PlanResult(
                plan_steps=["Loading clipboard history"], results=[],
                outcome="success",
                summary=f"Clipboard history ({len(items)} items):\n" + "\n".join(lines),
                voice_mode="brief")

        if action == "paste_previous":
            ok = cb.paste_from_history(1)
            return PlanResult(
                plan_steps=["Pasting previous item"], results=[],
                outcome="success" if ok else "failure",
                summary="Previous item restored to clipboard" if ok else "No previous item")

        if action == "clear":
            cb.clear_history()
            return PlanResult(
                plan_steps=["Clearing clipboard history"], results=[],
                outcome="success", summary="Clipboard history cleared")

        return PlanResult(
            plan_steps=["Checking clipboard"], results=[], outcome="failure",
            summary="Unknown clipboard action")

    def _handle_window(self, intent: Intent) -> PlanResult:
        action = intent.params.get("action", "list")

        if action == "list":
            windows = window_skill.list_windows()
            if not windows:
                return PlanResult(
                    plan_steps=["Listing windows"], results=[],
                    outcome="success", summary="No windows open")
            lines = []
            for w in windows[:10]:
                lines.append(f"  {w.app_name}: {w.title[:40]}")
            return PlanResult(
                plan_steps=["Listing windows"], results=[],
                outcome="success",
                summary=f"{len(windows)} windows open:\n" + "\n".join(lines),
                voice_mode="brief")

        if action == "focus":
            target = intent.params.get("target", "")
            if not target:
                return PlanResult(
                    plan_steps=["No window specified"], results=[],
                    outcome="failure", summary="Which window?")
            window = window_skill.find_window(target)
            if not window:
                return PlanResult(
                    plan_steps=[f"Searching for {target}"], results=[],
                    outcome="failure", summary=f"Window not found: {target}")
            steps, ok, err = _resilient_call(
                window_skill.focus_window, window, skill="window")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure",
                summary=f"Focused: {window.title[:40]}" if ok else f"Failed: {err}")

        if action == "close":
            target = intent.params.get("target", "")
            if not target:
                return PlanResult(
                    plan_steps=["No window specified"], results=[],
                    outcome="failure", summary="Which window should I close?")
            window = window_skill.find_window(target)
            if not window:
                return PlanResult(
                    plan_steps=[f"Searching for {target}"], results=[],
                    outcome="failure", summary=f"Window not found: {target}")
            steps, ok, err = _resilient_call(
                window_skill.close_window, window, skill="window")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure",
                summary=f"Closed: {window.title[:40]}" if ok else f"Failed: {err}")

        if action == "tile":
            position = intent.params.get("position", "maximize")
            window = window_skill.get_active_window()
            if not window:
                return PlanResult(
                    plan_steps=["Getting active window"], results=[],
                    outcome="failure", summary="No active window")
            steps, ok, err = _resilient_call(
                window_skill.tile_window, window, position, skill="window")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure",
                summary=f"Window tiled: {position}" if ok else f"Failed: {err}")

        if action == "switch_desktop":
            desktop = intent.params.get("desktop", 1)
            steps, ok, err = _resilient_call(
                window_skill.switch_desktop, desktop, skill="window")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure",
                summary=f"Switched to desktop {desktop}" if ok else f"Failed: {err}")

        return PlanResult(
            plan_steps=["Listing windows"], results=[], outcome="failure",
            summary="Unknown window action")

    def _handle_bluetooth(self, intent: Intent) -> PlanResult:
        action = intent.params.get("action", "status")

        if action == "status":
            if not bt_skill.is_available():
                return PlanResult(
                    plan_steps=["Checking Bluetooth"],
                    results=[], outcome="failure",
                    summary="Bluetooth not available on this device")
            powered = bt_skill.is_powered()
            connected = bt_skill.list_connected()
            if not powered:
                return PlanResult(
                    plan_steps=["Checking Bluetooth"],
                    results=[], outcome="success",
                    summary="Bluetooth is off")
            if connected:
                names = ", ".join(d.display_name for d in connected)
                return PlanResult(
                    plan_steps=["Checking Bluetooth"],
                    results=[], outcome="success",
                    summary=f"Bluetooth on — connected to {names}")
            return PlanResult(
                plan_steps=["Checking Bluetooth"],
                results=[], outcome="success",
                summary="Bluetooth on — no devices connected")

        if action == "power_on":
            steps, ok, msg = _resilient_call(
                bt_skill.power_on, skill="bluetooth")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "power_off":
            steps, ok, msg = _resilient_call(
                bt_skill.power_off, skill="bluetooth")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "scan":
            if not bt_skill.is_available():
                return PlanResult(
                    plan_steps=["Checking Bluetooth"],
                    results=[], outcome="failure",
                    summary="Bluetooth not available on this device")
            devices = bt_skill.scan(duration=5)
            if not devices:
                return PlanResult(
                    plan_steps=["Scanning Bluetooth"],
                    results=[], outcome="success",
                    summary="No Bluetooth devices found nearby")
            lines = []
            for d in devices[:10]:
                status = ""
                if d.connected:
                    status = " ✓ connected"
                elif d.paired:
                    status = " (paired)"
                lines.append(f"  {d.type_icon} {d.display_name}{status}")
            return PlanResult(
                plan_steps=["Scanning Bluetooth"],
                results=[], outcome="success",
                summary=f"Found {len(devices)} device(s):\n" + "\n".join(lines),
                voice_mode="brief")

        if action == "list":
            devices = bt_skill.list_paired()
            if not devices:
                return PlanResult(
                    plan_steps=["Listing Bluetooth devices"],
                    results=[], outcome="success",
                    summary="No paired Bluetooth devices")
            lines = []
            for d in devices[:10]:
                status = " ✓ connected" if d.connected else ""
                lines.append(f"  {d.type_icon} {d.display_name}{status}")
            return PlanResult(
                plan_steps=["Listing Bluetooth devices"],
                results=[], outcome="success",
                summary=f"{len(devices)} paired device(s):\n" + "\n".join(lines),
                voice_mode="brief")

        if action == "connect":
            device_name = intent.params.get("device", "")
            if not device_name:
                # List paired devices and ask which one
                paired = bt_skill.list_paired()
                if paired:
                    lines = [f"  {d.type_icon} {d.display_name}" for d in paired[:8]]
                    return PlanResult(
                        plan_steps=["Listing paired devices"],
                        results=[], outcome="success",
                        summary="Which device?\n" + "\n".join(lines))
                return PlanResult(
                    plan_steps=["Checking Bluetooth"],
                    results=[], outcome="success",
                    summary="No paired devices. Try: scan bluetooth")

            steps, ok, msg = _resilient_call(
                bt_skill.connect, device_name, skill="bluetooth")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure",
                summary=msg,
                error=None if ok else msg)

        if action == "disconnect":
            device_name = intent.params.get("device", "")
            steps, ok, msg = _resilient_call(
                bt_skill.disconnect, device_name, skill="bluetooth")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        if action == "remove":
            device_name = intent.params.get("device", "")
            if not device_name:
                return PlanResult(
                    plan_steps=["Checking Bluetooth"], results=[], outcome="failure",
                    summary="Which device should I remove?")
            steps, ok, msg = _resilient_call(
                bt_skill.remove, device_name, skill="bluetooth")
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure", summary=msg)

        return PlanResult(
            plan_steps=["Checking Bluetooth"], results=[], outcome="failure",
            summary="Unknown Bluetooth action")

    def _handle_self_update(self, intent: Intent) -> PlanResult:
        action = intent.params.get("action", "check")

        if action == "version":
            version = update_skill.get_current_version()
            return PlanResult(
                plan_steps=["Checking version"],
                results=[], outcome="success",
                summary=f"Harmoni v{version}")

        if action == "check":
            steps, summary = update_skill.check_update_summary()
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success", summary=summary)

        if action == "update":
            info = update_skill.check_update(use_cache=False)
            if not info.has_update:
                return PlanResult(
                    plan_steps=["Verificando atualizações"],
                    results=[], outcome="success",
                    summary=f"Já está na versão mais recente (v{info.current_version})")

            steps, ok, msg = update_skill.download_and_install(info)
            return PlanResult(
                plan_steps=steps, results=[],
                outcome="success" if ok else "failure",
                summary=msg)

        return PlanResult(
            plan_steps=["Checking version"], results=[], outcome="failure",
            summary="Ação de atualização desconhecida")

    def _handle_explore_system(self, intent: Intent) -> PlanResult:
        """#112-113: Show what Harmoni can do."""
        from harmoni.core.humanizer import _LANG
        steps, summary = format_capabilities(_LANG)
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success", summary=summary,
            voice_mode="brief")

    def _handle_list_apps(self, intent: Intent) -> PlanResult:
        """#114: List installed apps grouped by category."""
        from harmoni.core.humanizer import _LANG
        steps, summary = list_installed_apps_grouped(_LANG)
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success", summary=summary,
            voice_mode="brief")

    def _handle_workflow_start(self, intent: Intent) -> PlanResult:
        """#115-118: Start a development workflow for a project."""
        project_query = intent.params.get("project", "")
        if not project_query:
            return PlanResult(
                plan_steps=["No project specified"], results=[],
                outcome="failure",
                summary="Which project? e.g., 'quero trabalhar no meu-app'")

        plan_steps = ["Searching for project"]

        # Scan common project directories
        project_dirs = _scan_project_dirs()
        match = _find_project(project_query, project_dirs)

        if not match:
            if project_dirs:
                names = [os.path.basename(d) for d in project_dirs[:8]]
                lines = [f"  📁 {n}" for n in names]
                return PlanResult(
                    plan_steps=plan_steps, results=[],
                    outcome="failure",
                    summary=f"Project '{project_query}' not found.\n\nAvailable projects:\n"
                            + "\n".join(lines))
            return PlanResult(
                plan_steps=plan_steps, results=[],
                outcome="failure",
                summary=f"Project '{project_query}' not found. No project directories found.")

        plan_steps.append(f"Found: {os.path.basename(match)}")

        # Detect project type
        project = detect_project(match)
        plan_steps.append(f"Type: {project.type}")

        # Open editor
        editor_opened = False
        editor_app = find_app("code") or find_app("editor")
        if editor_app:
            plan_steps.append(f"Opening {editor_app.name}")
            _resilient_call(launch_app, editor_app, skill="app_launch", retryable=False)
            # Open the project folder in the editor
            try:
                import subprocess
                subprocess.Popen(
                    [editor_app.exec_command.split()[0], match],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                editor_opened = True
            except Exception:
                pass

        # Open browser if it's a web project
        browser_opened = False
        if project.type in ("node", "python") and project.port:
            browser_app = find_app("browser") or find_app("chrome") or find_app("firefox")
            if browser_app:
                plan_steps.append(f"Opening browser on port {project.port}")
                try:
                    import subprocess
                    subprocess.Popen(
                        [browser_app.exec_command.split()[0], f"http://localhost:{project.port}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    browser_opened = True
                except Exception:
                    pass

        # Build summary
        parts = [f"Workspace ready: {os.path.basename(match)}"]
        if editor_opened:
            parts.append("Editor opened")
        if browser_opened:
            parts.append(f"Browser on localhost:{project.port}")

        # Record for auto-learning
        from harmoni.skills.auto_learn import AutoLearner
        learner = AutoLearner()
        learner.record_execution(
            intent.raw_input, "workflow_start",
            {"project": project_query, "path": match},
            "success")

        return PlanResult(
            plan_steps=plan_steps, results=[],
            outcome="success",
            summary="\n".join(parts))

    def _handle_continue_project(self, intent: Intent) -> PlanResult:
        """Restore a previous workspace session.

        Flow:
        1. Parse project name from intent params (or use latest session)
        2. Look up SessionContext from Memory
        3. Check if server is still running (socket test on saved port)
        4. If running → skip server start, open editor + browser only
        5. If not running → full Dev Start with saved project path
        6. If project path doesn't exist → error + suggest available projects
        """
        project_name = intent.params.get("project", "")

        # If no project specified, use the most recent session
        if not project_name:
            latest = self.memory.get_latest_session()
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
            session = self.memory.get_session(project_name)
            if session is None:
                # Try fuzzy match against available sessions
                all_sessions = self.memory.list_sessions()
                for s in all_sessions:
                    if project_name.lower() in s.project_name.lower():
                        session = s
                        break

            if session is None:
                all_sessions = self.memory.list_sessions()
                if all_sessions:
                    names = [f"  📁 {s.project_name}" for s in all_sessions[:8]]
                    return PlanResult(
                        plan_steps=["Searching for project"],
                        results=[],
                        outcome="failure",
                        summary="Projeto não encontrado.\n\nProjetos disponíveis:\n"
                                + "\n".join(names),
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

        # Check if project path still exists
        if not os.path.exists(session.project_path):
            all_sessions = self.memory.list_sessions()
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

        # Check if server is still running
        server_running = (
            session.server_port > 0 and _is_port_in_use(session.server_port)
        )

        if server_running:
            # Server still running — just open editor + browser
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
            # Server not running — full Dev Start with saved project path
            plan_steps.append("Server not running — starting full Dev Start")

            project = detect_project(session.project_path)
            dev_plan, dev_results, pid = execute_dev_start(
                self.executor, project=project, memory=self.memory,
            )
            plan_steps.extend(dev_plan)

            failed = [r for r in dev_results if not r.success]
            if failed:
                return PlanResult(
                    plan_steps=plan_steps,
                    results=dev_results,
                    outcome="failure",
                    summary=f"Failed to restart project {session.project_name}.",
                    error=_sanitize_error(
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

    def _handle_intent_media(self, intent: Intent) -> PlanResult:
        """#119: Open the right app for media consumption."""
        media_type = intent.params.get("media_type", "video")

        if media_type == "audio":
            # Try music players
            app = (find_app("spotify") or find_app("music") or
                   find_app("rhythmbox") or find_app("vlc"))
            category = "music player"
            category_pt = "player de música"
        else:
            # Try video players / browsers
            app = (find_app("vlc") or find_app("browser") or
                   find_app("chrome") or find_app("firefox"))
            category = "video player"
            category_pt = "player de vídeo"

        if not app:
            from harmoni.core.humanizer import _LANG
            msg = (f"Nenhum {category_pt} encontrado. Instale um com: instalar vlc"
                   if _LANG == "pt"
                   else f"No {category} found. Install one with: install vlc")
            return PlanResult(
                plan_steps=[f"Looking for {category}"], results=[],
                outcome="failure", summary=msg)

        steps, ok, err = _resilient_call(
            launch_app, app, skill="app_launch", retryable=False)
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure",
            summary=f"{app.name} opened" if ok else f"Couldn't open {app.name}",
            error=err)

    def _handle_intent_browse(self, intent: Intent) -> PlanResult:
        """#120: Open browser for web browsing."""
        app = (find_app("browser") or find_app("chrome") or
               find_app("firefox") or find_app("chromium"))

        if not app:
            from harmoni.core.humanizer import _LANG
            msg = ("Nenhum navegador encontrado. Instale um com: instalar firefox"
                   if _LANG == "pt"
                   else "No browser found. Install one with: install firefox")
            return PlanResult(
                plan_steps=["Looking for browser"], results=[],
                outcome="failure", summary=msg)

        steps, ok, err = _resilient_call(
            launch_app, app, skill="app_launch", retryable=False)
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure",
            summary=f"{app.name} opened" if ok else f"Couldn't open {app.name}",
            error=err)

    def _handle_intent_write(self, intent: Intent) -> PlanResult:
        """#121: Open a text editor or office app for writing."""
        # Try office suite first, then text editors
        app = (find_app("writer") or find_app("libreoffice") or
               find_app("editor") or find_app("texto") or
               find_app("gedit") or find_app("kate"))

        if not app:
            from harmoni.core.humanizer import _LANG
            msg = ("Nenhum editor encontrado. Instale um com: instalar libreoffice"
                   if _LANG == "pt"
                   else "No editor found. Install one with: install libreoffice")
            return PlanResult(
                plan_steps=["Looking for text editor"], results=[],
                outcome="failure", summary=msg)

        steps, ok, err = _resilient_call(
            launch_app, app, skill="app_launch", retryable=False)
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure",
            summary=f"{app.name} opened" if ok else f"Couldn't open {app.name}",
            error=err)

    def _handle_files_search(self, intent: Intent) -> PlanResult:
        """#123-125: Search for files by name or content."""
        query = intent.params.get("query", "")
        if not query:
            return PlanResult(
                plan_steps=["No search query"], results=[],
                outcome="failure",
                summary="What file are you looking for?")

        report = search_files(query)

        if not report.results:
            from harmoni.core.humanizer import _LANG
            msg = (f"Nenhum arquivo encontrado para: {query}"
                   if _LANG == "pt"
                   else f"No files found for: {query}")
            return PlanResult(
                plan_steps=report.plan_steps, results=[],
                outcome="success", summary=msg)

        lines = []
        for r in report.results[:10]:
            icon = {"document": "📄", "image": "🖼️", "video": "🎬",
                    "audio": "🎵", "code": "💻", "archive": "📦"}.get(r.file_type, "📁")
            match_tag = " (conteúdo)" if r.match_type == "content" else ""
            lines.append(f"  {icon} {r.name} — {r.size_human} — {r.modified}{match_tag}")
            # Show shortened path
            home = os.path.expanduser("~")
            display_path = r.path.replace(home, "~")
            lines.append(f"     {display_path}")

        from harmoni.core.humanizer import _LANG
        header = (f"Encontrados {len(report.results)} arquivo(s) para \"{query}\":"
                  if _LANG == "pt"
                  else f"Found {len(report.results)} file(s) for \"{query}\":")
        tip = ('\nDiga "abrir arquivo [nome]" para abrir.'
               if _LANG == "pt"
               else '\nSay "open file [name]" to open.')

        return PlanResult(
            plan_steps=report.plan_steps, results=[],
            outcome="success",
            summary=header + "\n" + "\n".join(lines) + tip,
            voice_mode="brief")

    def _handle_files_open(self, intent: Intent) -> PlanResult:
        """#124: Find and open a file."""
        query = intent.params.get("query", "")
        if not query:
            return PlanResult(
                plan_steps=["No file specified"], results=[],
                outcome="failure",
                summary="Which file should I open?")

        steps, ok, err = _resilient_call(
            find_and_open, query, skill="file_search")
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure",
            summary=steps[-1] if ok and steps else (err or f"File not found: {query}"),
            error=err)

    def _mco_precheck(self, intent: Intent) -> Optional[PlanResult]:
        """MCO: context-aware decision layer.

        Consults MCP before execution. Returns a PlanResult if the MCO
        can resolve the intent without running the full handler, or None
        to proceed normally.

        Rules:
        - If context is sufficient → resolve directly (instant)
        - If state already matches request → short-circuit
        - Otherwise → proceed to handler
        """
        state = mcp.snapshot()

        # AUDIO: instant responses from MCP state
        if intent.type == IntentType.AUDIO:
            action = intent.params.get("action")
            if action == "mute" and state.audio.muted:
                return PlanResult(
                    plan_steps=["Checking volume"],
                    results=[], outcome="success",
                    summary=f"Already muted (volume at {state.audio.volume}%)")
            if action == "unmute" and not state.audio.muted:
                return PlanResult(
                    plan_steps=["Checking volume"],
                    results=[], outcome="success",
                    summary=f"Already unmuted — Volume: {state.audio.volume}%")
            if action == "status":
                if state.audio.muted:
                    return PlanResult(
                        plan_steps=["Checking volume"],
                        results=[], outcome="success",
                        summary=f"Audio muted (volume at {state.audio.volume}%)")
                return PlanResult(
                    plan_steps=["Checking volume"],
                    results=[], outcome="success",
                    summary=f"Volume: {state.audio.volume}%")

        # NETWORK: status from MCP (instant, no nmcli call)
        if intent.type == IntentType.NETWORK:
            action = intent.params.get("action")
            if action == "status":
                wifi = state.wifi
                if wifi.connected:
                    summary = f"Connected to {wifi.ssid}"
                    if wifi.ip:
                        summary += f" ({wifi.ip})"
                    if wifi.signal:
                        summary += f" — Signal: {wifi.signal}%"
                    return PlanResult(
                        plan_steps=["Checking Wi-Fi"],
                        results=[], outcome="success", summary=summary)
                return PlanResult(
                    plan_steps=["Checking Wi-Fi"],
                    results=[], outcome="success",
                    summary="Not connected to any network")

            if action == "connect":
                ssid = intent.params.get("ssid", "")
                if state.wifi.connected and ssid and state.wifi.ssid.lower() == ssid.lower():
                    return PlanResult(
                        plan_steps=["Checking connection"],
                        results=[], outcome="success",
                        summary=f"Already connected to {state.wifi.ssid}")

        # SYSTEM_HEALTH: if system is healthy and was checked recently, say so fast
        # (no short-circuit here — always run full check for accuracy)

        return None  # proceed to handler
