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
    """Send IPC command to compositor. Currently unused — IPC only accepts one connection."""
    # The compositor only accepts one IPC connection (the runtime listener).
    # Monitor detection uses DRM sysfs instead.
    return None


def _get_monitors_from_drm() -> list[MonitorInfo]:
    """Read connected monitors from /sys/class/drm (kernel DRM subsystem).

    This works regardless of IPC state and gives us connected outputs
    with their preferred resolution.
    """
    import glob
    import re

    monitors = []
    drm_cards = glob.glob("/sys/class/drm/card*-*")

    for card_path in sorted(drm_cards):
        status_file = os.path.join(card_path, "status")
        if not os.path.exists(status_file):
            continue

        try:
            with open(status_file) as f:
                status = f.read().strip()
        except OSError:
            continue

        if status != "connected":
            continue

        # Extract connector name (e.g. "eDP-1", "HDMI-A-1")
        card_name = os.path.basename(card_path)
        # Format: card1-HDMI-A-1 → HDMI-A-1
        match = re.match(r"card\d+-(.+)", card_name)
        if not match:
            continue
        name = match.group(1)

        # Read preferred mode (first mode listed)
        modes_file = os.path.join(card_path, "modes")
        width, height = 0, 0
        if os.path.exists(modes_file):
            try:
                with open(modes_file) as f:
                    first_mode = f.readline().strip()
                if first_mode:
                    mode_match = re.match(r"(\d+)x(\d+)", first_mode)
                    if mode_match:
                        width = int(mode_match.group(1))
                        height = int(mode_match.group(2))
            except OSError:
                pass

        # First monitor is primary
        is_primary = len(monitors) == 0

        monitors.append(
            MonitorInfo(
                name=name,
                width=width,
                height=height,
                x=0,
                y=0,
                primary=is_primary,
            )
        )

    return monitors


def get_monitors() -> list[MonitorInfo]:
    """Get list of connected monitors.

    Tries IPC first (has position info), falls back to DRM sysfs.
    """
    # Try IPC (has accurate position data from compositor)
    resp = _ipc_send({"cmd": "get_outputs"})
    if resp and "outputs" in resp and resp["outputs"]:
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

    # Fallback: read from DRM sysfs (no position info, but detects connected outputs)
    return _get_monitors_from_drm()


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
