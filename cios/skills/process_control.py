"""Skill: process_control — detect port usage, kill processes."""

from typing import Optional

import psutil

from cios.core.executor import Executor, ExecResult


def find_process_on_port(port: int) -> Optional[dict]:
    """Find the process listening on a given port."""
    for conn in psutil.net_connections(kind="inet"):
        if conn.laddr.port == port and conn.status == "LISTEN":
            try:
                proc = psutil.Process(conn.pid)
                return {
                    "pid": conn.pid,
                    "name": proc.name(),
                    "cmdline": " ".join(proc.cmdline()),
                    "port": port,
                }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return {"pid": conn.pid, "name": "unknown", "cmdline": "", "port": port}
    return None


def kill_process_on_port(executor: Executor, port: int) -> tuple[list[str], ExecResult]:
    """Kill whatever is on the port and report what happened."""
    info = find_process_on_port(port)
    if info is None:
        return (
            [f"Nothing is listening on port {port}"],
            ExecResult("check", 0, f"Port {port} is free", "", 0.0),
        )

    plan = [f"Found {info['name']} (PID {info['pid']}) on port {port}", "Killing process"]
    result = executor.kill_by_port(port)
    return plan, result


def list_listening_ports() -> list[dict]:
    """List all listening TCP ports with process info."""
    ports = []
    seen = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == "LISTEN" and conn.laddr.port not in seen:
            seen.add(conn.laddr.port)
            try:
                proc = psutil.Process(conn.pid)
                ports.append(
                    {
                        "port": conn.laddr.port,
                        "pid": conn.pid,
                        "name": proc.name(),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                ports.append({"port": conn.laddr.port, "pid": conn.pid, "name": "unknown"})
    return sorted(ports, key=lambda p: p["port"])
