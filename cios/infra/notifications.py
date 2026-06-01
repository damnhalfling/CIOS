"""Notifications system — event-driven notification infrastructure.

Provides a central notification bus that skills, handlers, and system events
can publish to. The UI layer subscribes and renders notifications.

Notification types:
- info: general information (e.g. "Connected to WiFi")
- progress: long-running task update (e.g. "Installing htop... 60%")
- action: requires user response (e.g. "USB detected. Open?")
- error: something failed (e.g. "WiFi connection failed")
- timer: scheduled reminder (e.g. "Lembra: reunião às 17h")
- insight: proactive discovery (e.g. "Novidades sobre FastAPI")

Architecture:
- NotificationBus: singleton, thread-safe, pub/sub
- Notification: dataclass with type, title, body, actions, expiry
- Subscribers register callbacks (UI layers)
- History kept in memory (last 100), persisted to SQLite optionally

#500 — Notifications system
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from collections import deque

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    INFO = "info"
    PROGRESS = "progress"
    ACTION = "action"
    ERROR = "error"
    TIMER = "timer"
    INSIGHT = "insight"


@dataclass
class NotificationAction:
    """An action button on a notification."""
    label: str
    callback_id: str  # Identifier for the action (handler resolves)
    params: dict = field(default_factory=dict)


@dataclass
class Notification:
    """A single notification."""
    id: str
    type: NotificationType
    title: str
    body: str = ""
    icon: str = ""  # emoji or icon name
    actions: list[NotificationAction] = field(default_factory=list)
    progress: float | None = None  # 0.0-1.0 for progress type
    source: str = ""  # which skill/module generated this
    timestamp: float = field(default_factory=time.time)
    expires_at: float | None = None  # auto-dismiss after this time
    dismissed: bool = False
    read: bool = False


# Type for subscriber callbacks
NotificationCallback = Callable[[Notification], None]


class NotificationBus:
    """Central notification bus — singleton, thread-safe.

    Usage:
        from cios.infra.notifications import bus

        # Publish
        bus.notify("Connected to Starlink", type=NotificationType.INFO, source="network")

        # Subscribe (UI layer)
        bus.subscribe(my_callback)

        # With actions
        bus.notify(
            "USB detectado. Abrir?",
            type=NotificationType.ACTION,
            actions=[NotificationAction(label="Abrir", callback_id="automount_open")],
        )
    """

    def __init__(self, max_history: int = 100):
        self._subscribers: list[NotificationCallback] = []
        self._history: deque[Notification] = deque(maxlen=max_history)
        self._lock = threading.Lock()
        self._counter = 0

    def notify(
        self,
        title: str,
        body: str = "",
        type: NotificationType = NotificationType.INFO,
        icon: str = "",
        actions: list[NotificationAction] | None = None,
        progress: float | None = None,
        source: str = "",
        expires_in: float | None = None,
    ) -> Notification:
        """Publish a notification to all subscribers.

        Args:
            title: Short notification title
            body: Optional longer description
            type: Notification type (info, progress, action, error, timer, insight)
            icon: Emoji or icon name
            actions: Action buttons (for ACTION type)
            progress: Progress value 0.0-1.0 (for PROGRESS type)
            source: Which module generated this
            expires_in: Auto-dismiss after N seconds (None = manual dismiss)

        Returns:
            The created Notification object
        """
        with self._lock:
            self._counter += 1
            notif_id = f"notif_{self._counter}_{int(time.time())}"

        expires_at = None
        if expires_in:
            expires_at = time.time() + expires_in

        notification = Notification(
            id=notif_id,
            type=type,
            title=title,
            body=body,
            icon=icon or self._default_icon(type),
            actions=actions or [],
            progress=progress,
            source=source,
            expires_at=expires_at,
        )

        with self._lock:
            self._history.append(notification)

        # Notify subscribers (outside lock to avoid deadlocks)
        for callback in self._subscribers:
            try:
                callback(notification)
            except Exception as e:
                logger.warning("Notification subscriber error: %s", e)

        logger.debug("Notification: [%s] %s — %s", type.value, title, source)
        return notification

    def subscribe(self, callback: NotificationCallback) -> None:
        """Register a callback to receive notifications."""
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: NotificationCallback) -> None:
        """Remove a subscriber."""
        with self._lock:
            self._subscribers = [s for s in self._subscribers if s != callback]

    def dismiss(self, notif_id: str) -> None:
        """Mark a notification as dismissed."""
        with self._lock:
            for notif in self._history:
                if notif.id == notif_id:
                    notif.dismissed = True
                    break

    def mark_read(self, notif_id: str) -> None:
        """Mark a notification as read."""
        with self._lock:
            for notif in self._history:
                if notif.id == notif_id:
                    notif.read = True
                    break

    def get_history(self, limit: int = 50, include_dismissed: bool = False) -> list[Notification]:
        """Get notification history (most recent first)."""
        with self._lock:
            items = list(self._history)

        if not include_dismissed:
            items = [n for n in items if not n.dismissed]

        # Filter expired
        now = time.time()
        items = [n for n in items if not n.expires_at or n.expires_at > now]

        return list(reversed(items))[:limit]

    def get_unread_count(self) -> int:
        """Get count of unread, non-dismissed notifications."""
        now = time.time()
        with self._lock:
            return sum(
                1 for n in self._history
                if not n.dismissed and not n.read
                and (not n.expires_at or n.expires_at > now)
            )

    def update_progress(self, notif_id: str, progress: float, body: str = "") -> None:
        """Update progress on an existing progress notification."""
        with self._lock:
            for notif in self._history:
                if notif.id == notif_id:
                    notif.progress = progress
                    if body:
                        notif.body = body
                    break

        # Re-notify subscribers with updated notification
        for notif in self._history:
            if notif.id == notif_id:
                for callback in self._subscribers:
                    try:
                        callback(notif)
                    except Exception:
                        pass
                break

    def clear_all(self) -> None:
        """Clear all notifications."""
        with self._lock:
            self._history.clear()

    @staticmethod
    def _default_icon(type: NotificationType) -> str:
        icons = {
            NotificationType.INFO: "ℹ️",
            NotificationType.PROGRESS: "⏳",
            NotificationType.ACTION: "❓",
            NotificationType.ERROR: "❌",
            NotificationType.TIMER: "⏰",
            NotificationType.INSIGHT: "💡",
        }
        return icons.get(type, "")


# Singleton instance
bus = NotificationBus()


# ═══════════════════════════════════════════════════════════════════════════
#  DO NOT DISTURB MODE (#523)
# ═══════════════════════════════════════════════════════════════════════════


class DoNotDisturb:
    """Do Not Disturb mode — silences all notifications.

    When active, notifications are still stored in history but
    subscribers are NOT notified (no UI popups, no sounds).

    #523 — Do Not Disturb mode
    """

    def __init__(self):
        self._active = False
        self._original_subscribers: list[NotificationCallback] = []

    @property
    def active(self) -> bool:
        return self._active

    def enable(self) -> None:
        """Enable DND — mute all notification delivery."""
        if self._active:
            return
        self._active = True
        # Store current subscribers and clear them
        self._original_subscribers = list(bus._subscribers)
        bus._subscribers = []
        logger.info("Do Not Disturb: enabled")

    def disable(self) -> None:
        """Disable DND — restore notification delivery."""
        if not self._active:
            return
        self._active = False
        # Restore subscribers
        bus._subscribers = self._original_subscribers
        self._original_subscribers = []
        logger.info("Do Not Disturb: disabled")

    def toggle(self) -> bool:
        """Toggle DND. Returns new state."""
        if self._active:
            self.disable()
        else:
            self.enable()
        return self._active


# Singleton
dnd = DoNotDisturb()
