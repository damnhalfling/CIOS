"""Tests for desktop features — notifications, scheduler, theming.

Validates:
- Notification bus pub/sub, dismiss, history, expiry
- Scheduler time parsing, add/fire reminders
- Theming set/toggle/get
"""

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════════════════
#  NOTIFICATION BUS
# ═══════════════════════════════════════════════════════════════════════════


class TestNotificationBus:
    """Test the notification bus pub/sub system."""

    def setup_method(self):
        from cios.infra.notifications import NotificationBus
        self.bus = NotificationBus()

    def test_notify_returns_notification(self):
        from cios.infra.notifications import NotificationType
        notif = self.bus.notify("Test", type=NotificationType.INFO)
        assert notif.title == "Test"
        assert notif.type == NotificationType.INFO
        assert notif.id.startswith("notif_")

    def test_subscriber_receives_notification(self):
        received = []
        self.bus.subscribe(lambda n: received.append(n))
        self.bus.notify("Hello")
        assert len(received) == 1
        assert received[0].title == "Hello"

    def test_multiple_subscribers(self):
        received_a = []
        received_b = []
        self.bus.subscribe(lambda n: received_a.append(n))
        self.bus.subscribe(lambda n: received_b.append(n))
        self.bus.notify("Test")
        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_unsubscribe(self):
        received = []

        def cb(n):
            received.append(n)

        self.bus.subscribe(cb)
        self.bus.notify("First")
        self.bus.unsubscribe(cb)
        self.bus.notify("Second")
        assert len(received) == 1

    def test_history_stores_notifications(self):
        self.bus.notify("One")
        self.bus.notify("Two")
        self.bus.notify("Three")
        history = self.bus.get_history()
        assert len(history) == 3
        # Most recent first
        assert history[0].title == "Three"

    def test_dismiss_removes_from_history(self):
        notif = self.bus.notify("Dismiss me")
        self.bus.dismiss(notif.id)
        history = self.bus.get_history(include_dismissed=False)
        assert all(n.id != notif.id for n in history)

    def test_dismiss_still_in_history_with_flag(self):
        notif = self.bus.notify("Dismiss me")
        self.bus.dismiss(notif.id)
        history = self.bus.get_history(include_dismissed=True)
        assert any(n.id == notif.id for n in history)

    def test_unread_count(self):
        self.bus.notify("One")
        self.bus.notify("Two")
        assert self.bus.get_unread_count() == 2
        history = self.bus.get_history()
        self.bus.mark_read(history[0].id)
        assert self.bus.get_unread_count() == 1

    def test_expiry_filters_old(self):
        notif = self.bus.notify("Expires", expires_in=0.01)
        time.sleep(0.02)
        history = self.bus.get_history()
        assert all(n.id != notif.id for n in history)

    def test_progress_update(self):
        from cios.infra.notifications import NotificationType
        notif = self.bus.notify("Installing", type=NotificationType.PROGRESS, progress=0.0)
        self.bus.update_progress(notif.id, 0.5, "50%")
        history = self.bus.get_history()
        updated = next(n for n in history if n.id == notif.id)
        assert updated.progress == 0.5
        assert updated.body == "50%"

    def test_default_icons(self):
        from cios.infra.notifications import NotificationType
        notif_info = self.bus.notify("Info", type=NotificationType.INFO)
        notif_error = self.bus.notify("Error", type=NotificationType.ERROR)
        assert notif_info.icon == "ℹ️"
        assert notif_error.icon == "❌"

    def test_action_notifications(self):
        from cios.infra.notifications import NotificationAction, NotificationType
        notif = self.bus.notify(
            "USB detected",
            type=NotificationType.ACTION,
            actions=[NotificationAction(label="Mount", callback_id="mount_usb")],
        )
        assert len(notif.actions) == 1
        assert notif.actions[0].label == "Mount"
        assert notif.actions[0].callback_id == "mount_usb"

    def test_max_history_cap(self):
        bus = __import__("cios.infra.notifications", fromlist=["NotificationBus"]).NotificationBus(max_history=5)
        for i in range(10):
            bus.notify(f"Notif {i}")
        history = bus.get_history(limit=100)
        assert len(history) <= 5

    def test_clear_all(self):
        self.bus.notify("One")
        self.bus.notify("Two")
        self.bus.clear_all()
        assert self.bus.get_history() == []
        assert self.bus.get_unread_count() == 0


# ═══════════════════════════════════════════════════════════════════════════
#  SCHEDULER — TIME PARSING
# ═══════════════════════════════════════════════════════════════════════════


class TestSchedulerTimeParsing:
    """Test natural language time expression parsing."""

    def test_relative_minutes(self):
        from cios.skills.scheduler import parse_time_expression
        result = parse_time_expression("daqui a 30 minutos")
        assert result is not None
        diff = (result - datetime.now()).total_seconds()
        assert 1700 < diff < 1900  # ~30 min

    def test_relative_hours(self):
        from cios.skills.scheduler import parse_time_expression
        result = parse_time_expression("em 2 horas")
        assert result is not None
        diff = (result - datetime.now()).total_seconds()
        assert 7000 < diff < 7400  # ~2h

    def test_relative_english(self):
        from cios.skills.scheduler import parse_time_expression
        result = parse_time_expression("in 15 minutes")
        assert result is not None
        diff = (result - datetime.now()).total_seconds()
        assert 800 < diff < 1000  # ~15 min

    def test_absolute_time_pt(self):
        from cios.skills.scheduler import parse_time_expression
        result = parse_time_expression("às 17h")
        assert result is not None
        assert result.hour == 17
        assert result.minute == 0

    def test_absolute_time_with_minutes(self):
        from cios.skills.scheduler import parse_time_expression
        result = parse_time_expression("às 14:30")
        assert result is not None
        assert result.hour == 14
        assert result.minute == 30

    def test_absolute_time_en(self):
        from cios.skills.scheduler import parse_time_expression
        result = parse_time_expression("at 5pm")
        assert result is not None
        assert result.hour == 17

    def test_tomorrow(self):
        from cios.skills.scheduler import parse_time_expression
        result = parse_time_expression("amanhã às 9h")
        assert result is not None
        tomorrow = datetime.now() + timedelta(days=1)
        assert result.day == tomorrow.day
        assert result.hour == 9

    def test_invalid_returns_none(self):
        from cios.skills.scheduler import parse_time_expression
        result = parse_time_expression("qualquer coisa sem horário")
        assert result is None


class TestSchedulerTasks:
    """Test scheduler task management."""

    def setup_method(self):
        from cios.skills.scheduler import Scheduler
        self.scheduler = Scheduler()

    def test_add_reminder(self):
        trigger = datetime.now() + timedelta(hours=1)
        task = self.scheduler.add_reminder("Test reminder", trigger)
        assert task.title == "Test reminder"
        assert task.trigger_at == trigger
        assert task.fired is False

    def test_list_pending(self):
        future = datetime.now() + timedelta(hours=1)
        self.scheduler.add_reminder("Future", future)
        pending = self.scheduler.list_pending()
        assert len(pending) == 1
        assert pending[0].title == "Future"

    def test_cancel_task(self):
        future = datetime.now() + timedelta(hours=1)
        task = self.scheduler.add_reminder("Cancel me", future)
        assert self.scheduler.cancel(task.id) is True
        assert len(self.scheduler.list_pending()) == 0

    def test_cancel_nonexistent(self):
        assert self.scheduler.cancel("fake_id") is False

    def test_add_deferred_intent(self):
        trigger = datetime.now() + timedelta(minutes=30)
        task = self.scheduler.add_deferred_intent("package", {"action": "install", "package": "htop"}, trigger)
        assert task.intent == "package"
        assert task.params["package"] == "htop"


# ═══════════════════════════════════════════════════════════════════════════
#  THEMING
# ═══════════════════════════════════════════════════════════════════════════


class TestTheming:
    """Test theming skill."""

    def test_get_current_theme_default(self):
        from cios.skills.theming import DEFAULT_THEME, get_current_theme
        # Without config file, should return default
        with patch("cios.skills.theming._load_config", return_value={}):
            assert get_current_theme() == DEFAULT_THEME

    def test_set_theme_dark(self):
        from cios.skills.theming import set_theme
        with patch("subprocess.run") as mock_run, \
             patch("cios.skills.theming._save_config"):
            mock_run.return_value = MagicMock(returncode=0)
            success, msg = set_theme("dark")
            assert success is True
            assert "escuro" in msg.lower()

    def test_set_theme_light(self):
        from cios.skills.theming import set_theme
        with patch("subprocess.run") as mock_run, \
             patch("cios.skills.theming._save_config"):
            mock_run.return_value = MagicMock(returncode=0)
            success, msg = set_theme("light")
            assert success is True
            assert "claro" in msg.lower()

    def test_set_invalid_theme(self):
        from cios.skills.theming import set_theme
        success, msg = set_theme("neon")
        assert success is False
        assert "não existe" in msg.lower()

    def test_toggle_theme(self):
        from cios.skills.theming import toggle_theme
        with patch("cios.skills.theming.get_current_theme", return_value="dark"), \
             patch("cios.skills.theming.set_theme") as mock_set:
            mock_set.return_value = (True, "Tema alterado para Modo claro.")
            success, msg = toggle_theme()
            mock_set.assert_called_once_with("light")

    def test_available_themes(self):
        from cios.skills.theming import THEMES
        assert "dark" in THEMES
        assert "light" in THEMES
        assert len(THEMES) >= 2
