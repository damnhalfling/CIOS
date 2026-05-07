"""Handler for network/Wi-Fi intents."""

from cios.core.executor import Executor
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.core.handlers._common import PlanResult, resilient_call
from cios.core.mcp import context as mcp
from cios.skills import network as network_skill


def handle_network(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle Wi-Fi status, list, connect, disconnect."""
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
        steps, ok, msg = resilient_call(
            network_skill.disconnect, skill="network")
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure", summary=msg)

    if action == "connect":
        ssid = intent.params.get("ssid", "")
        password = intent.params.get("password", "")

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
            for net in available:
                if net.ssid.lower() in known:
                    ssid = net.ssid
                    break

            if not ssid:
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

        steps, ok, msg = resilient_call(
            network_skill.connect, ssid, password, skill="network")
        return PlanResult(
            plan_steps=steps, results=[],
            outcome="success" if ok else "failure",
            summary=msg,
            error=None if ok else msg)

    return PlanResult(
        plan_steps=["Checking Wi-Fi"], results=[], outcome="failure",
        summary="Unknown network action")
