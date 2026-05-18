"""TaskQueue — Background execution system for long-running operations.

Allows the user to keep using the prompt while tasks (apt install, upgrades,
downloads) run in background threads. Each task has:
- Unique ID
- Status (queued, running, completed, failed)
- Progress updates (streaming)
- Result storage
- Queue for related follow-up commands

Design:
- Tasks are grouped by context (e.g., all package ops in one thread)
- New input is classified: same context → enqueue, different → new task
- UI polls or subscribes to progress updates
- Completed tasks notify the UI
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskProgress:
    """A single progress update from a running task."""

    message: str
    percentage: float = -1.0  # -1 = indeterminate
    timestamp: float = field(default_factory=time.time)


@dataclass
class Task:
    """A single unit of work that runs in background."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    context: str = ""  # e.g., "package", "network", "file"
    status: TaskStatus = TaskStatus.QUEUED
    progress: list[TaskProgress] = field(default_factory=list)
    result: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0

    # The callable to execute (set by the handler)
    _execute_fn: Callable[["Task"], dict] | None = field(default=None, repr=False)

    def add_progress(self, message: str, percentage: float = -1.0) -> None:
        """Add a progress update. Thread-safe (append is atomic in CPython)."""
        self.progress.append(TaskProgress(message=message, percentage=percentage))

    @property
    def latest_progress(self) -> str:
        """Get the most recent progress message."""
        if self.progress:
            return self.progress[-1].message
        return self.description

    @property
    def duration(self) -> float:
        """Duration in seconds (running or total)."""
        if self.started_at == 0:
            return 0.0
        end = self.completed_at if self.completed_at > 0 else time.time()
        return end - self.started_at


class TaskThread:
    """A background execution thread that processes a queue of related tasks.

    Each TaskThread has a context (e.g., "package") and processes tasks
    sequentially from its queue. Multiple TaskThreads can run in parallel
    for different contexts.
    """

    def __init__(self, context: str, on_task_complete: Callable[[Task], None] | None = None):
        self.context = context
        self.id = uuid.uuid4().hex[:8]
        self._queue: Queue[Task] = Queue()
        self._current_task: Task | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._on_task_complete = on_task_complete
        self._lock = threading.Lock()

    @property
    def current_task(self) -> Task | None:
        return self._current_task

    @property
    def is_busy(self) -> bool:
        return self._current_task is not None and self._current_task.status == TaskStatus.RUNNING

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def enqueue(self, task: Task) -> None:
        """Add a task to this thread's queue and start processing if idle."""
        task.status = TaskStatus.QUEUED
        self._queue.put(task)
        logger.info("task %s enqueued in thread %s (%s)", task.id, self.id, self.context)

        # Start worker if not running
        with self._lock:
            if not self._running:
                self._running = True
                self._thread = threading.Thread(
                    target=self._worker, daemon=True, name=f"task-{self.context}"
                )
                self._thread.start()

    def _worker(self) -> None:
        """Process tasks from the queue sequentially."""
        while True:
            try:
                task = self._queue.get(timeout=5.0)
            except Exception:
                # Queue empty for 5s — stop worker
                with self._lock:
                    if self._queue.empty():
                        self._running = False
                        return
                continue

            self._current_task = task
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            task.add_progress(f"Iniciando: {task.description}")

            try:
                if task._execute_fn:
                    result = task._execute_fn(task)
                    task.result = result if result else {}
                    task.status = TaskStatus.COMPLETED
                    task.add_progress("Concluído", 100.0)
                else:
                    task.result = {"status": "error", "result": "No execute function"}
                    task.status = TaskStatus.FAILED
            except Exception as e:
                logger.exception("Task %s failed: %s", task.id, e)
                task.result = {"status": "error", "result": str(e)}
                task.status = TaskStatus.FAILED
                task.add_progress(f"Erro: {e}")

            task.completed_at = time.time()
            self._current_task = None

            # Notify completion
            if self._on_task_complete:
                try:
                    self._on_task_complete(task)
                except Exception:
                    logger.exception("Error in task completion callback")

            self._queue.task_done()


class TaskManager:
    """Manages all background task threads.

    Routes new tasks to existing threads (same context) or creates new ones.
    Provides a unified view of all running/queued/completed tasks.
    """

    def __init__(self, on_task_complete: Callable[[Task], None] | None = None):
        self._threads: dict[str, TaskThread] = {}
        self._completed: list[Task] = []
        self._lock = threading.Lock()
        self._on_task_complete = on_task_complete
        self._max_completed = 50

    def submit(self, task: Task) -> str:
        """Submit a task for background execution.

        Routes to existing thread with same context, or creates a new one.
        Returns the task ID immediately.
        """
        context = task.context or "default"

        with self._lock:
            if context not in self._threads:
                self._threads[context] = TaskThread(
                    context=context,
                    on_task_complete=self._handle_completion,
                )

            self._threads[context].enqueue(task)

        logger.info("task %s submitted (context=%s, desc=%s)", task.id, context, task.description)
        return task.id

    def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID (running, queued, or completed)."""
        with self._lock:
            # Check running/queued
            for thread in self._threads.values():
                if thread.current_task and thread.current_task.id == task_id:
                    return thread.current_task
            # Check completed
            for task in self._completed:
                if task.id == task_id:
                    return task
        return None

    def get_active_tasks(self) -> list[Task]:
        """Get all currently running tasks."""
        tasks = []
        with self._lock:
            for thread in self._threads.values():
                if thread.current_task and thread.current_task.status == TaskStatus.RUNNING:
                    tasks.append(thread.current_task)
        return tasks

    def get_all_tasks(self) -> list[Task]:
        """Get all tasks (running + recent completed)."""
        tasks = self.get_active_tasks()
        with self._lock:
            tasks.extend(self._completed[-10:])
        return tasks

    def is_context_busy(self, context: str) -> bool:
        """Check if a context has a running task."""
        with self._lock:
            thread = self._threads.get(context)
            return thread.is_busy if thread else False

    def _handle_completion(self, task: Task) -> None:
        """Called when a task completes. Stores in history and notifies."""
        with self._lock:
            self._completed.append(task)
            if len(self._completed) > self._max_completed:
                self._completed = self._completed[-self._max_completed :]

        if self._on_task_complete:
            try:
                self._on_task_complete(task)
            except Exception:
                logger.exception("Error in global task completion callback")


# ═══════════════════════════════════════════════════════════════════════════
#  CONTEXT DETECTION
# ═══════════════════════════════════════════════════════════════════════════

# Map intent types to task contexts
_INTENT_CONTEXT_MAP = {
    "package": "package",
    "self_update": "package",
    "network": "network",
    "file_organize": "files",
    "disk_analysis": "files",
}

# Intents that should run in background (long-running)
BACKGROUND_INTENTS = frozenset(
    [
        "package",  # apt install/remove/update/upgrade
        "self_update",  # cios self-update
    ]
)


def should_run_background(intent_type: str, params: dict) -> bool:
    """Determine if an intent should run as a background task."""
    if intent_type in BACKGROUND_INTENTS:
        # Package search is fast, don't background it
        return not (intent_type == "package" and params.get("action") == "search")
    return False


def get_task_context(intent_type: str) -> str:
    """Get the task context for an intent type."""
    return _INTENT_CONTEXT_MAP.get(intent_type, "default")
