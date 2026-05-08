"""Skill: system_health — diagnose system issues and suggest actions.

Not just metrics. Actionable intelligence:
- "Chrome is using 1.8GB. Want to close it?"
- "3 heavy processes found. Want me to handle them?"
"""

from dataclasses import dataclass, field

import psutil


@dataclass
class HealthReport:
    plan_steps: list[str]
    summary_lines: list[str]
    status: str  # "healthy" | "warning" | "critical"
    top_processes: list[dict]
    suggestions: list[str] = field(default_factory=list)


def _size_human(b: int) -> str:
    if b >= 1024**3:
        return f"{b / (1024 ** 3):.1f}GB"
    if b >= 1024**2:
        return f"{b / (1024 ** 2):.0f}MB"
    return f"{b / 1024:.0f}KB"


def check_system_health() -> HealthReport:
    """Run a system health check with actionable suggestions."""
    plan_steps = []
    summary = []
    suggestions = []
    warnings = 0

    # CPU
    plan_steps.append("Checking CPU")
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    if cpu_percent > 90:
        summary.append(f"⚠ Processor is very busy ({cpu_percent:.0f}%)")
        warnings += 1
    elif cpu_percent > 70:
        summary.append(f"Processor is moderately busy ({cpu_percent:.0f}%)")
    else:
        summary.append(f"Processor is fine ({cpu_percent:.0f}% used, {cpu_count} cores)")

    # Memory
    plan_steps.append("Checking memory")
    mem = psutil.virtual_memory()
    mem_used_gb = mem.used / (1024**3)
    mem_total_gb = mem.total / (1024**3)
    if mem.percent > 90:
        summary.append(
            f"⚠ Memory is almost full ({mem.percent:.0f}% — {mem_used_gb:.1f} / {mem_total_gb:.1f} GB)"
        )
        warnings += 1
    elif mem.percent > 75:
        summary.append(
            f"Memory is getting full ({mem.percent:.0f}% — {mem_used_gb:.1f} / {mem_total_gb:.1f} GB)"
        )
    else:
        summary.append(
            f"Memory is fine ({mem.percent:.0f}% — {mem_used_gb:.1f} / {mem_total_gb:.1f} GB)"
        )

    # Disk
    plan_steps.append("Checking disk")
    disk = psutil.disk_usage("/")
    disk_free_gb = disk.free / (1024**3)
    disk_total_gb = disk.total / (1024**3)
    if disk.percent > 90:
        summary.append(
            f"⚠ Storage is almost full ({disk_free_gb:.1f} GB free of {disk_total_gb:.0f} GB)"
        )
        suggestions.append('Say "free space" to find what\'s using your disk')
        warnings += 1
    elif disk.percent > 80:
        summary.append(
            f"Storage is getting full ({disk_free_gb:.1f} GB free of {disk_total_gb:.0f} GB)"
        )
    else:
        summary.append(f"Storage is fine ({disk_free_gb:.1f} GB free of {disk_total_gb:.0f} GB)")

    # Top processes by memory (more useful than CPU for "slow" complaints)
    plan_steps.append("Checking top processes")
    top_procs = []
    for proc in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_percent", "memory_info"]
    ):
        try:
            info = proc.info
            mem_pct = info.get("memory_percent") or 0
            cpu_pct = info.get("cpu_percent") or 0
            mem_bytes = 0
            if info.get("memory_info"):
                mem_bytes = info["memory_info"].rss

            if mem_pct > 1.0 or cpu_pct > 5.0:
                name = info["name"] or "unknown"
                # Skip system processes
                if name in (
                    "systemd",
                    "kworker",
                    "Xwayland",
                    "Xorg",
                    "pipewire",
                    "pulseaudio",
                    "dbus-daemon",
                ):
                    continue
                top_procs.append(
                    {
                        "name": name,
                        "pid": info["pid"],
                        "cpu": cpu_pct,
                        "memory_pct": mem_pct,
                        "memory_bytes": mem_bytes,
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort by memory usage (most relevant for "slow" complaints)
    top_procs.sort(key=lambda p: p["memory_bytes"], reverse=True)
    top_procs = top_procs[:5]

    if top_procs:
        summary.append("")
        summary.append("Most active apps:")
        for p in top_procs:
            mem_str = _size_human(p["memory_bytes"])
            summary.append(f"  {p['name']} — {mem_str} memory, " f"{p['cpu']:.0f}% processor")

        # Generate actionable suggestions for heavy processes
        heavy = [p for p in top_procs if p["memory_bytes"] > 500 * 1024 * 1024]  # > 500MB
        if heavy and mem.percent > 70:
            heaviest = heavy[0]
            mem_str = _size_human(heaviest["memory_bytes"])
            suggestions.append(
                f"{heaviest['name']} is using {mem_str}. "
                f'Say "kill process {heaviest["name"]}" to close it'
            )

        cpu_heavy = [p for p in top_procs if p["cpu"] > 50]
        if cpu_heavy and cpu_percent > 70:
            heaviest = cpu_heavy[0]
            suggestions.append(
                f"{heaviest['name']} is using {heaviest['cpu']:.0f}% CPU. "
                f'Say "kill process {heaviest["name"]}" to stop it'
            )

    # Add suggestions to summary
    if suggestions:
        summary.append("")
        summary.append("💡 Suggestions:")
        for s in suggestions:
            summary.append(f"  → {s}")

    # Overall status
    if warnings >= 2:
        status = "critical"
    elif warnings >= 1:
        status = "warning"
    else:
        status = "healthy"

    return HealthReport(
        plan_steps=plan_steps,
        summary_lines=summary,
        status=status,
        top_processes=top_procs,
        suggestions=suggestions,
    )
