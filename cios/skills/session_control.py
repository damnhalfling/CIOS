"""Session Control skill — power management and session actions.

Handles: shutdown, reboot, suspend, hibernate, logout, lock screen.
All actions require confirmation (enforced by the planner/bridge).
"""

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SessionAction:
    action: str  # "shutdown" | "reboot" | "suspend" | "hibernate" | "logout" | "lock"
    command: str  # comando real a executar
    description: str  # descrição humana
    destructive: bool  # requer confirmação?


# Mapeamento de ações disponíveis
_ACTIONS: dict[str, SessionAction] = {
    "shutdown": SessionAction(
        action="shutdown",
        command="systemctl poweroff",
        description="Desligar o computador",
        destructive=True,
    ),
    "reboot": SessionAction(
        action="reboot",
        command="systemctl reboot",
        description="Reiniciar o computador",
        destructive=True,
    ),
    "suspend": SessionAction(
        action="suspend",
        command="systemctl suspend",
        description="Suspender (modo dormir)",
        destructive=False,
    ),
    "hibernate": SessionAction(
        action="hibernate",
        command="systemctl hibernate",
        description="Hibernar",
        destructive=False,
    ),
    "logout": SessionAction(
        action="logout",
        command="loginctl terminate-session $XDG_SESSION_ID",
        description="Encerrar sessão",
        destructive=True,
    ),
    "lock": SessionAction(
        action="lock",
        command="",  # resolvido dinamicamente
        description="Bloquear tela",
        destructive=False,
    ),
}


def _find_lock_command() -> str:
    """Find the best available screen locker.

    Priority:
    1. i3lock — lightweight, works on any X session (Openbox, etc.)
    2. xdg-screensaver — desktop-agnostic standard
    3. gnome-screensaver — GNOME sessions
    4. xscreensaver — classic X locker
    5. dm-tool — LightDM lock (common on Debian with LightDM)
    6. loginctl — systemd fallback (needs a locker registered)
    7. xset dpms — last resort: just turns off the screen
    """
    lockers = [
        ("i3lock", "i3lock -c 0b0f14"),
        ("xdg-screensaver", "xdg-screensaver lock"),
        ("gnome-screensaver-command", "gnome-screensaver-command -l"),
        ("xscreensaver-command", "xscreensaver-command -lock"),
        ("dm-tool", "dm-tool lock"),
        ("loginctl", "loginctl lock-session"),
        ("xset", "xset dpms force off"),
    ]
    for binary, cmd in lockers:
        try:
            result = subprocess.run(
                ["which", binary],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return cmd
        except Exception:
            continue
    return "loginctl lock-session"  # absolute fallback


def get_session_action(action_name: str) -> SessionAction | None:
    """Get a session action by name."""
    action = _ACTIONS.get(action_name)
    if action and action.action == "lock" and not action.command:
        action.command = _find_lock_command()
    return action


def execute_session_action(action_name: str) -> tuple[list[str], bool, str | None]:
    """Execute a session action.

    Returns:
        (plan_steps, success, error)
    """
    action = get_session_action(action_name)
    if not action:
        return [f"Unknown action: {action_name}"], False, f"Action '{action_name}' not recognized"

    plan_steps = [action.description]

    try:
        import os

        cmd = action.command

        # Expandir variáveis de ambiente no comando
        if "$XDG_SESSION_ID" in cmd:
            session_id = os.environ.get("XDG_SESSION_ID", "")
            if not session_id:
                # Tentar obter via loginctl
                try:
                    result = subprocess.run(
                        ["loginctl", "show-session", "self", "-p", "Id", "--value"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    session_id = result.stdout.strip()
                except Exception:
                    session_id = ""
            cmd = cmd.replace("$XDG_SESSION_ID", session_id)

        logger.info(f"Session action: {action.action} -> {cmd}")

        # For lock, run synchronously to detect failure
        if action.action == "lock":
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                # Lock command failed — suggest installing a locker
                error_hint = result.stderr.strip()[:100] if result.stderr else ""
                logger.warning(
                    "Lock failed (cmd=%s, rc=%d): %s", cmd, result.returncode, error_hint
                )
                return (
                    plan_steps,
                    False,
                    "Nenhum bloqueador de tela encontrado. Instale um com: instalar i3lock",
                )
            plan_steps.append(f"{action.description} — executado")
            return plan_steps, True, None

        subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        plan_steps.append(f"{action.description} — executado")
        return plan_steps, True, None

    except Exception as e:
        error = str(e)
        plan_steps.append(f"Falha: {error}")
        return plan_steps, False, error


def is_destructive(action_name: str) -> bool:
    """Check if an action requires confirmation."""
    action = _ACTIONS.get(action_name)
    return action.destructive if action else True
