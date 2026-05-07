"""Handler for package management intents (apt install/remove/search/update)."""

from cios.core.executor import Executor
from cios.core.intent_parser import Intent
from cios.core.memory import Memory
from cios.core.handlers._common import PlanResult
from cios.skills import package_manager as pkg_skill


def handle_package(intent: Intent, executor: Executor, memory: Memory) -> PlanResult:
    """Handle package install/remove/search/update/upgrade."""
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
