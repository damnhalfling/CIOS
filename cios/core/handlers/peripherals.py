"""Handlers for bluetooth, clipboard, and window control intents."""

from cios.core.executor import Executor
from cios.core.handlers._common import PlanResult, resilient_call
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.skills import bluetooth as bt_skill
from cios.skills import clipboard as clipboard_skill
from cios.skills import window_control as window_skill


def handle_bluetooth(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle bluetooth status/scan/connect/disconnect/power."""
    action = intent.params.get("action", "status")

    if action == "status":
        if not bt_skill.is_available():
            return PlanResult(
                plan_steps=["Checking Bluetooth"],
                results=[],
                outcome="failure",
                summary="Bluetooth not available on this device",
            )
        powered = bt_skill.is_powered()
        connected = bt_skill.list_connected()
        if not powered:
            return PlanResult(
                plan_steps=["Checking Bluetooth"],
                results=[],
                outcome="success",
                summary="Bluetooth is off",
            )
        if connected:
            names = ", ".join(d.display_name for d in connected)
            return PlanResult(
                plan_steps=["Checking Bluetooth"],
                results=[],
                outcome="success",
                summary=f"Bluetooth on — connected to {names}",
            )
        return PlanResult(
            plan_steps=["Checking Bluetooth"],
            results=[],
            outcome="success",
            summary="Bluetooth on — no devices connected",
        )

    if action == "power_on":
        steps, ok, msg = resilient_call(bt_skill.power_on, skill="bluetooth")
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if ok else "failure", summary=msg
        )

    if action == "power_off":
        steps, ok, msg = resilient_call(bt_skill.power_off, skill="bluetooth")
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if ok else "failure", summary=msg
        )

    if action == "scan":
        if not bt_skill.is_available():
            return PlanResult(
                plan_steps=["Checking Bluetooth"],
                results=[],
                outcome="failure",
                summary="Bluetooth not available on this device",
            )
        devices = bt_skill.scan(duration=5)
        if not devices:
            return PlanResult(
                plan_steps=["Scanning Bluetooth"],
                results=[],
                outcome="success",
                summary="No Bluetooth devices found nearby",
            )
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
            results=[],
            outcome="success",
            summary=f"Found {len(devices)} device(s):\n" + "\n".join(lines),
            voice_mode="brief",
        )

    if action == "list":
        devices = bt_skill.list_paired()
        if not devices:
            return PlanResult(
                plan_steps=["Listing Bluetooth devices"],
                results=[],
                outcome="success",
                summary="No paired Bluetooth devices",
            )
        lines = []
        for d in devices[:10]:
            status = " ✓ connected" if d.connected else ""
            lines.append(f"  {d.type_icon} {d.display_name}{status}")
        return PlanResult(
            plan_steps=["Listing Bluetooth devices"],
            results=[],
            outcome="success",
            summary=f"{len(devices)} paired device(s):\n" + "\n".join(lines),
            voice_mode="brief",
        )

    if action == "connect":
        device_name = intent.params.get("device", "")
        if not device_name:
            paired = bt_skill.list_paired()
            if paired:
                lines = [f"  {d.type_icon} {d.display_name}" for d in paired[:8]]
                return PlanResult(
                    plan_steps=["Listing paired devices"],
                    results=[],
                    outcome="success",
                    summary="Which device?\n" + "\n".join(lines),
                )
            return PlanResult(
                plan_steps=["Checking Bluetooth"],
                results=[],
                outcome="success",
                summary="No paired devices. Try: scan bluetooth",
            )

        steps, ok, msg = resilient_call(bt_skill.connect, device_name, skill="bluetooth")
        return PlanResult(
            plan_steps=steps,
            results=[],
            outcome="success" if ok else "failure",
            summary=msg,
            error=None if ok else msg,
        )

    if action == "disconnect":
        device_name = intent.params.get("device", "")
        steps, ok, msg = resilient_call(bt_skill.disconnect, device_name, skill="bluetooth")
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if ok else "failure", summary=msg
        )

    if action == "remove":
        device_name = intent.params.get("device", "")
        if not device_name:
            return PlanResult(
                plan_steps=["Checking Bluetooth"],
                results=[],
                outcome="failure",
                summary="Which device should I remove?",
            )
        steps, ok, msg = resilient_call(bt_skill.remove, device_name, skill="bluetooth")
        return PlanResult(
            plan_steps=steps, results=[], outcome="success" if ok else "failure", summary=msg
        )

    return PlanResult(
        plan_steps=["Checking Bluetooth"],
        results=[],
        outcome="failure",
        summary="Unknown Bluetooth action",
    )


def handle_clipboard(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle clipboard current/history/paste/clear."""
    action = intent.params.get("action", "current")
    cb = clipboard_skill.CognitiveClipboard()

    if action == "current":
        content = cb.get_current()
        if content:
            content_type = clipboard_skill.detect_content_type(content)
            preview = content[:200]
            summary = f"Clipboard ({content_type}):\n{preview}"
            actions = cb.suggest_actions(content)
            if actions:
                summary += "\n\nSuggested actions:"
                for a in actions[:3]:
                    summary += f"\n  {a.icon} {a.label}"
        else:
            summary = "Clipboard is empty"
        return PlanResult(
            plan_steps=["Checking clipboard"],
            results=[],
            outcome="success",
            summary=summary,
            voice_mode="brief",
        )

    if action == "history":
        items = cb.get_history(10)
        if not items:
            return PlanResult(
                plan_steps=["Checking history"],
                results=[],
                outcome="success",
                summary="No clipboard history",
            )
        lines = []
        for i, item in enumerate(items):
            lines.append(f"  {i+1}. [{item.content_type}] {item.preview}")
        return PlanResult(
            plan_steps=["Loading clipboard history"],
            results=[],
            outcome="success",
            summary=f"Clipboard history ({len(items)} items):\n" + "\n".join(lines),
            voice_mode="brief",
        )

    if action == "paste_previous":
        ok = cb.paste_from_history(1)
        return PlanResult(
            plan_steps=["Pasting previous item"],
            results=[],
            outcome="success" if ok else "failure",
            summary="Previous item restored to clipboard" if ok else "No previous item",
        )

    if action == "clear":
        cb.clear_history()
        return PlanResult(
            plan_steps=["Clearing clipboard history"],
            results=[],
            outcome="success",
            summary="Clipboard history cleared",
        )

    return PlanResult(
        plan_steps=["Checking clipboard"],
        results=[],
        outcome="failure",
        summary="Unknown clipboard action",
    )


def handle_window(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle window list/focus/close/tile/switch_desktop."""
    action = intent.params.get("action", "list")

    if action == "list":
        windows = window_skill.list_windows()
        if not windows:
            return PlanResult(
                plan_steps=["Listing windows"],
                results=[],
                outcome="success",
                summary="No windows open",
            )
        lines = []
        for w in windows[:10]:
            lines.append(f"  {w.app_name}: {w.title[:40]}")
        return PlanResult(
            plan_steps=["Listing windows"],
            results=[],
            outcome="success",
            summary=f"{len(windows)} windows open:\n" + "\n".join(lines),
            voice_mode="brief",
        )

    if action == "focus":
        target = intent.params.get("target", "")
        if not target:
            return PlanResult(
                plan_steps=["No window specified"],
                results=[],
                outcome="failure",
                summary="Which window?",
            )
        window = window_skill.find_window(target)
        if not window:
            return PlanResult(
                plan_steps=[f"Searching for {target}"],
                results=[],
                outcome="failure",
                summary=f"Window not found: {target}",
            )
        steps, ok, err = resilient_call(window_skill.focus_window, window, skill="window")
        return PlanResult(
            plan_steps=steps,
            results=[],
            outcome="success" if ok else "failure",
            summary=f"Focused: {window.title[:40]}" if ok else f"Failed: {err}",
        )

    if action == "close":
        target = intent.params.get("target", "")
        if not target:
            return PlanResult(
                plan_steps=["No window specified"],
                results=[],
                outcome="failure",
                summary="Which window should I close?",
            )
        window = window_skill.find_window(target)
        if not window:
            return PlanResult(
                plan_steps=[f"Searching for {target}"],
                results=[],
                outcome="failure",
                summary=f"Window not found: {target}",
            )
        steps, ok, err = resilient_call(window_skill.close_window, window, skill="window")
        return PlanResult(
            plan_steps=steps,
            results=[],
            outcome="success" if ok else "failure",
            summary=f"Closed: {window.title[:40]}" if ok else f"Failed: {err}",
        )

    if action == "tile":
        position = intent.params.get("position", "maximize")
        window = window_skill.get_active_window()
        if not window:
            return PlanResult(
                plan_steps=["Getting active window"],
                results=[],
                outcome="failure",
                summary="No active window",
            )
        steps, ok, err = resilient_call(window_skill.tile_window, window, position, skill="window")
        return PlanResult(
            plan_steps=steps,
            results=[],
            outcome="success" if ok else "failure",
            summary=f"Window tiled: {position}" if ok else f"Failed: {err}",
        )

    if action == "switch_desktop":
        desktop = intent.params.get("desktop", 1)
        steps, ok, err = resilient_call(window_skill.switch_desktop, desktop, skill="window")
        return PlanResult(
            plan_steps=steps,
            results=[],
            outcome="success" if ok else "failure",
            summary=f"Switched to desktop {desktop}" if ok else f"Failed: {err}",
        )

    return PlanResult(
        plan_steps=["Listing windows"],
        results=[],
        outcome="failure",
        summary="Unknown window action",
    )
