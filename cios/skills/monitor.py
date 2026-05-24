"""Skill: Monitor Configuration — detect, position, and persist monitor layout.

Provides:
- List connected monitors with resolution and position
- Configure position (above, below, left, right)
- Mirror mode (same image on both)
- Persist configuration to ~/.config/cios/monitors.conf
- Auto-apply saved config on boot

Uses CIOS Shell IPC (configure_output, get_outputs).
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".config" / "cios"
_CONFIG_FILE = _CONFIG_DIR / "monitors.conf"


@dataclass
class MonitorInfo:
    """Information about a connected monitor."""

    name: str  # e.g. "eDP-1", "HDMI-A-1"
    width: int
    height: int
    x: int
    y: int
    primary: bool


def _ipc_send(command: dict) -> dict | None:
    """Send IPC command to compositor."""
    import socket

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    sock_path = os.path.join(runtime_dir, "cios-shell.sock")

    if not os.path.exists(sock_path):
        return None

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(3)
            sock.connect(sock_path)
            payload = {"v": 1, "id": f"mon_{id(command)}", "command": command.pop("cmd"), **command}
            msg = json.dumps(payload) + "\n"
            sock.sendall(msg.encode("utf-8"))
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            if data:
                return json.loads(data.decode("utf-8").strip())
    except (OSError, json.JSONDecodeError) as e:
        logger.debug("Monitor IPC failed: %s", e)
    return None


def get_monitors() -> list[MonitorInfo]:
    """Get list of connected monitors from compositor."""
    resp = _ipc_send({"cmd": "get_outputs"})
    if not resp or "outputs" not in resp:
        return []

    monitors = []
    for out in resp["outputs"]:
        monitors.append(
            MonitorInfo(
                name=out.get("name", "unknown"),
                width=out.get("width", 0),
                height=out.get("height", 0),
                x=out.get("x", 0),
                y=out.get("y", 0),
                primary=out.get("primary", False),
            )
        )
    return monitors


def configure_position(target: str, position: str, reference: str) -> tuple[list[str], bool, str]:
    """Position a monitor relative to another.

    Args:
        target: Name of monitor to move (e.g. "HDMI-A-1")
        position: "above", "below", "left", "right"
        reference: Name of reference monitor (e.g. "eDP-1")
    """
    monitors = get_monitors()
    ref = next((m for m in monitors if m.name == reference), None)
    if not ref:
        return [f"Posicionando {target}"], False, f"Monitor {reference} não encontrado"

    # Calculate position based on reference
    if position == "above":
        # Get target resolution
        tgt = next((m for m in monitors if m.name == target), None)
        tgt_h = tgt.height if tgt else 1080
        x = ref.x
        y = ref.y - tgt_h
    elif position == "below":
        x = ref.x
        y = ref.y + ref.height
    elif position == "left":
        tgt = next((m for m in monitors if m.name == target), None)
        tgt_w = tgt.width if tgt else 1920
        x = ref.x - tgt_w
        y = ref.y
    elif position == "right":
        x = ref.x + ref.width
        y = ref.y
    else:
        return [f"Posicionando {target}"], False, f"Posição inválida: {position}"

    resp = _ipc_send({"cmd": "configure_output", "name": target, "x": x, "y": y})
    if resp and resp.get("response") == "ok":
        _save_config(monitors, target, x, y)
        return [f"Monitor {target} posicionado {position} de {reference}"], True, ""
    return (
        [f"Posicionando {target}"],
        False,
        resp.get("reason", "IPC failed") if resp else "Sem resposta",
    )


def configure_mirror(target: str, mirror_of: str) -> tuple[list[str], bool, str]:
    """Set a monitor to mirror another."""
    resp = _ipc_send({"cmd": "configure_output", "name": target, "mirror_of": mirror_of})
    if resp and resp.get("response") == "ok":
        _save_mirror_config(target, mirror_of)
        return [f"Monitor {target} espelhando {mirror_of}"], True, ""
    return (
        [f"Espelhando {target}"],
        False,
        resp.get("reason", "IPC failed") if resp else "Sem resposta",
    )


def _save_config(monitors: list[MonitorInfo], moved_name: str, new_x: int, new_y: int) -> None:
    """Save monitor layout to config file."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if _CONFIG_FILE.exists():
        try:
            config = json.loads(_CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            config = {}

    if "outputs" not in config:
        config["outputs"] = {}

    # Save all current positions
    for m in monitors:
        if m.name == moved_name:
            config["outputs"][m.name] = {"x": new_x, "y": new_y, "mode": "extend"}
        else:
            config["outputs"][m.name] = {"x": m.x, "y": m.y, "mode": "extend"}

    _CONFIG_FILE.write_text(json.dumps(config, indent=2))
    logger.info("Monitor config saved: %s", _CONFIG_FILE)


def _save_mirror_config(target: str, mirror_of: str) -> None:
    """Save mirror configuration."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    config: dict = {}
    if _CONFIG_FILE.exists():
        try:
            config = json.loads(_CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            config = {}

    if "outputs" not in config:
        config["outputs"] = {}

    config["outputs"][target] = {"mirror_of": mirror_of, "mode": "mirror"}
    _CONFIG_FILE.write_text(json.dumps(config, indent=2))


def apply_saved_config() -> bool:
    """Apply saved monitor config (called on boot)."""
    if not _CONFIG_FILE.exists():
        return False

    try:
        config = json.loads(_CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    outputs = config.get("outputs", {})
    if not outputs:
        return False

    applied = False
    for name, cfg in outputs.items():
        mode = cfg.get("mode", "extend")
        if mode == "mirror":
            mirror_of = cfg.get("mirror_of")
            if mirror_of:
                resp = _ipc_send({"cmd": "configure_output", "name": name, "mirror_of": mirror_of})
                if resp and resp.get("response") == "ok":
                    applied = True
        else:
            x = cfg.get("x", 0)
            y = cfg.get("y", 0)
            resp = _ipc_send({"cmd": "configure_output", "name": name, "x": x, "y": y})
            if resp and resp.get("response") == "ok":
                applied = True

    if applied:
        logger.info("Applied saved monitor config from %s", _CONFIG_FILE)
    return applied
