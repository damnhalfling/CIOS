"""Scheduler skill — timers, reminders, and deferred intents.

Handles natural language scheduling:
- "lembra-me às 17h" → timer notification
- "daqui a 30 minutos" → relative timer
- "todo dia às 9h" → recurring (via systemd-timer or internal loop)

Uses the notification bus to deliver reminders.

#502 — Scheduled tasks / timers
#503 — Deferred intents
"""

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    """A scheduled task/reminder."""

    id: str
    title: str
    trigger_at: datetime
    recurring: str | None = None  # "daily", "weekly", None
    intent: str | None = None  # Deferred intent to execute
    params: dict = field(default_factory=dict)
    fired: bool = False


class Scheduler:
    """In-process scheduler for timers and reminders.

    Runs a background thread that checks pending tasks every 30s.
    Fires notifications via the notification bus when tasks are due.
    """

    def __init__(self):
        self._tasks: list[ScheduledTask] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._counter = 0

    def start(self) -> None:
        """Start the scheduler background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cios-scheduler")
        self._thread.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler stopped")

    def add_reminder(
        self, title: str, trigger_at: datetime, recurring: str | None = None
    ) -> ScheduledTask:
        """Add a reminder that fires a notification at the specified time."""
        with self._lock:
            self._counter += 1
            task = ScheduledTask(
                id=f"task_{self._counter}",
                title=title,
                trigger_at=trigger_at,
                recurring=recurring,
            )
            self._tasks.append(task)
        logger.info("Reminder added: '%s' at %s", title, trigger_at.isoformat())
        return task

    def add_deferred_intent(self, intent: str, params: dict, trigger_at: datetime) -> ScheduledTask:
        """Add a deferred intent that executes at the specified time.

        #503 — Deferred intents ("depois do almoço", "amanhã cedo")
        """
        with self._lock:
            self._counter += 1
            task = ScheduledTask(
                id=f"deferred_{self._counter}",
                title=f"Executar: {intent}",
                trigger_at=trigger_at,
                intent=intent,
                params=params,
            )
            self._tasks.append(task)
        logger.info("Deferred intent: '%s' at %s", intent, trigger_at.isoformat())
        return task

    def cancel(self, task_id: str) -> bool:
        """Cancel a scheduled task."""
        with self._lock:
            before = len(self._tasks)
            self._tasks = [t for t in self._tasks if t.id != task_id]
            return len(self._tasks) < before

    def list_pending(self) -> list[ScheduledTask]:
        """List all pending (unfired) tasks."""
        now = datetime.now()
        with self._lock:
            return [t for t in self._tasks if not t.fired and t.trigger_at > now]

    def _loop(self) -> None:
        """Background loop — checks tasks every 30s."""
        while self._running:
            self._check_tasks()
            time.sleep(30)

    def _check_tasks(self) -> None:
        """Fire tasks that are due."""
        now = datetime.now()
        to_fire: list[ScheduledTask] = []

        with self._lock:
            for task in self._tasks:
                if not task.fired and task.trigger_at <= now:
                    to_fire.append(task)
                    task.fired = True

        for task in to_fire:
            self._fire_task(task)

            # Handle recurring
            if task.recurring:
                next_trigger = self._next_occurrence(task.trigger_at, task.recurring)
                with self._lock:
                    self._counter += 1
                    new_task = ScheduledTask(
                        id=f"task_{self._counter}",
                        title=task.title,
                        trigger_at=next_trigger,
                        recurring=task.recurring,
                        intent=task.intent,
                        params=task.params,
                    )
                    self._tasks.append(new_task)

    def _fire_task(self, task: ScheduledTask) -> None:
        """Fire a task — send notification or execute deferred intent."""
        from cios.infra.notifications import NotificationType, bus

        if task.intent:
            # Deferred intent — notify and let bridge handle execution
            bus.notify(
                title=f"Executando: {task.title}",
                body=f"Intent: {task.intent}",
                type=NotificationType.TIMER,
                source="scheduler",
                icon="⏰",
            )
            logger.info("Deferred intent fired: %s", task.intent)
        else:
            # Simple reminder
            bus.notify(
                title=task.title,
                type=NotificationType.TIMER,
                source="scheduler",
                icon="⏰",
                expires_in=300,  # 5 min auto-dismiss
            )
            logger.info("Reminder fired: %s", task.title)

    @staticmethod
    def _next_occurrence(current: datetime, recurring: str) -> datetime:
        """Calculate next occurrence for recurring tasks."""
        if recurring == "daily":
            return current + timedelta(days=1)
        elif recurring == "weekly":
            return current + timedelta(weeks=1)
        elif recurring == "hourly":
            return current + timedelta(hours=1)
        return current + timedelta(days=1)


# Singleton
scheduler = Scheduler()


# ═══════════════════════════════════════════════════════════════════════════
#  NATURAL LANGUAGE TIME PARSING
# ═══════════════════════════════════════════════════════════════════════════


def parse_time_expression(text: str) -> datetime | None:
    """Parse natural language time expressions into datetime.

    Supports:
    - "às 17h", "at 5pm", "às 14:30"
    - "daqui a 30 minutos", "in 30 minutes"
    - "amanhã às 9h", "tomorrow at 9am"
    - "em 1 hora", "in 1 hour"
    """
    now = datetime.now()
    text_lower = text.lower().strip()

    # Relative: "daqui a X minutos/horas"
    m = re.search(r"(?:daqui\s+a|in|em)\s+(\d+)\s*(min|minuto|minute|hora|hour|h)", text_lower)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("h") or "hora" in unit or "hour" in unit:
            return now + timedelta(hours=amount)
        return now + timedelta(minutes=amount)

    # Absolute: "às 17h", "at 5pm", "às 14:30"
    m = re.search(r"(?:às|as|at)\s+(\d{1,2})(?::(\d{2}))?(?:\s*h)?(?:\s*(am|pm))?", text_lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # If time already passed today, schedule for tomorrow
        if target <= now:
            target += timedelta(days=1)
        return target

    # "amanhã" / "tomorrow"
    if "amanhã" in text_lower or "amanha" in text_lower or "tomorrow" in text_lower:
        m = re.search(r"(\d{1,2})(?::(\d{2}))?(?:\s*h)?", text_lower)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # Default: tomorrow 9am
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

    return None
