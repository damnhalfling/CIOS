"""Automount skill — detect and mount USB/SD/external drives.

Uses udisks2 D-Bus interface to detect new block devices and mount them.
Sends notification via bus when a device is plugged in.

#504 — Automount USB/SD/drives externos
#505 — Notificação de device plugado
"""

import logging
import subprocess
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MountedDevice:
    """A mounted external device."""
    device: str  # /dev/sdb1
    label: str  # "USB_DRIVE" or partition label
    mount_point: str  # /media/user/USB_DRIVE
    filesystem: str  # ext4, vfat, ntfs
    size: str  # "32G"


class AutomountWatcher:
    """Watches for new block devices and mounts them automatically.

    Uses `udisksctl monitor` to detect hotplug events.
    Sends notifications via the notification bus.
    """

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._mounted: dict[str, MountedDevice] = {}

    def start(self) -> None:
        """Start watching for device events."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True, name="cios-automount")
        self._thread.start()
        logger.info("Automount watcher started")

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def mount_device(self, device: str) -> MountedDevice | None:
        """Mount a specific device using udisksctl.

        Returns MountedDevice on success, None on failure.
        """
        try:
            result = subprocess.run(
                ["udisksctl", "mount", "-b", device],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                # Parse mount point from output: "Mounted /dev/sdb1 at /media/user/LABEL"
                output = result.stdout.strip()
                mount_point = ""
                if " at " in output:
                    mount_point = output.split(" at ")[-1].rstrip(".")

                info = self._get_device_info(device)
                mounted = MountedDevice(
                    device=device,
                    label=info.get("label", device.split("/")[-1]),
                    mount_point=mount_point,
                    filesystem=info.get("filesystem", "unknown"),
                    size=info.get("size", ""),
                )
                self._mounted[device] = mounted
                logger.info("Mounted %s at %s", device, mount_point)
                return mounted
            else:
                logger.warning("Mount failed for %s: %s", device, result.stderr)
                return None
        except Exception as e:
            logger.error("Mount error for %s: %s", device, e)
            return None

    def unmount_device(self, device: str) -> bool:
        """Unmount a device."""
        try:
            result = subprocess.run(
                ["udisksctl", "unmount", "-b", device],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                self._mounted.pop(device, None)
                logger.info("Unmounted %s", device)
                return True
            return False
        except Exception as e:
            logger.error("Unmount error: %s", e)
            return False

    def list_mounted(self) -> list[MountedDevice]:
        """List currently mounted external devices."""
        return list(self._mounted.values())

    def _watch_loop(self) -> None:
        """Watch for device events using polling (fallback if udisks monitor unavailable)."""
        known_devices = self._scan_removable_devices()

        while self._running:
            time.sleep(3)  # Poll every 3 seconds
            current = self._scan_removable_devices()

            # Detect new devices
            new_devices = current - known_devices
            for device in new_devices:
                self._on_device_added(device)

            # Detect removed devices
            removed = known_devices - current
            for device in removed:
                self._on_device_removed(device)

            known_devices = current

    def _on_device_added(self, device: str) -> None:
        """Handle new device detection — notify user."""
        from cios.infra.notifications import bus, NotificationType, NotificationAction

        info = self._get_device_info(device)
        label = info.get("label", device.split("/")[-1])
        size = info.get("size", "")

        title = f"Dispositivo detectado: {label}"
        body = f"{size} — {info.get('filesystem', 'unknown')}" if size else ""

        bus.notify(
            title=title,
            body=body,
            type=NotificationType.ACTION,
            icon="💾",
            source="automount",
            actions=[
                NotificationAction(label="Montar", callback_id="automount_mount", params={"device": device}),
                NotificationAction(label="Ignorar", callback_id="automount_ignore", params={"device": device}),
            ],
        )
        logger.info("New device detected: %s (%s)", device, label)

    def _on_device_removed(self, device: str) -> None:
        """Handle device removal."""
        from cios.infra.notifications import bus, NotificationType

        self._mounted.pop(device, None)
        bus.notify(
            title="Dispositivo removido",
            type=NotificationType.INFO,
            icon="⏏️",
            source="automount",
            expires_in=5,
        )

    def _scan_removable_devices(self) -> set[str]:
        """Scan for removable block devices."""
        devices = set()
        try:
            result = subprocess.run(
                ["lsblk", "-nrpo", "NAME,RM,TYPE,MOUNTPOINT"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 3:
                    name, removable, dev_type = parts[0], parts[1], parts[2]
                    mountpoint = parts[3] if len(parts) > 3 else ""
                    # Removable partitions not yet mounted
                    if removable == "1" and dev_type == "part" and not mountpoint:
                        devices.add(name)
        except Exception as e:
            logger.debug("lsblk scan failed: %s", e)
        return devices

    def _get_device_info(self, device: str) -> dict:
        """Get device info (label, filesystem, size)."""
        info = {}
        try:
            result = subprocess.run(
                ["lsblk", "-nrpo", "LABEL,FSTYPE,SIZE", device],
                capture_output=True, text=True, timeout=5,
            )
            parts = result.stdout.strip().split()
            if len(parts) >= 1:
                info["label"] = parts[0] if parts[0] else device.split("/")[-1]
            if len(parts) >= 2:
                info["filesystem"] = parts[1]
            if len(parts) >= 3:
                info["size"] = parts[2]
        except Exception:
            pass
        return info


# Singleton
automount_watcher = AutomountWatcher()
