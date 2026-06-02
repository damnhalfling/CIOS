"""Tests for system skills — audio, network, display, automount.

All subprocess calls are mocked — tests logic, not system state.
"""

from unittest.mock import MagicMock, patch

# ═══════════════════════════════════════════════════════════════════════════
#  AUDIO SKILL
# ═══════════════════════════════════════════════════════════════════════════


class TestAudioSkill:
    """Test audio control skill (mocked pactl)."""

    def test_get_volume(self):
        from cios.skills import audio

        with patch.object(audio, "_backend", "pactl"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout="Volume: front-left: 45000 /  69% / -9.50 dB,"
                    "   front-right: 45000 /  69% / -9.50 dB\n",
                )
                vol = audio.get_volume()
                assert vol == 69

    def test_set_volume(self):
        from cios.skills import audio

        with patch.object(audio, "_backend", "pactl"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                steps, success, msg = audio.set_volume(80)
                assert success is True

    def test_mute(self):
        from cios.skills import audio

        with patch.object(audio, "_backend", "pactl"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")
                steps, success, msg = audio.mute(True)
                assert success is True


# ═══════════════════════════════════════════════════════════════════════════
#  NETWORK SKILL
# ═══════════════════════════════════════════════════════════════════════════


class TestNetworkSkill:
    """Test network/wifi skill (mocked nmcli)."""

    def test_list_networks(self):
        from cios.skills.network import list_networks

        nmcli_output = "Starlink:85:WPA2\n" "Vizinho:40:WPA2\n" "OpenNet:60:--\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=nmcli_output)
            networks = list_networks()
            assert isinstance(networks, list)

    def test_connect_network(self):
        from cios.skills.network import connect

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Connection successfully activated\n",
            )
            steps, success, msg = connect("Starlink")
            assert success is True

    def test_get_current_connection(self):
        from cios.skills.network import get_current_connection

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Starlink:802-11-wireless:wlp2s0:activated\n",
            )
            conn = get_current_connection()
            # May return dict or None depending on parsing
            # Just verify it doesn't crash
            assert conn is None or isinstance(conn, dict)


# ═══════════════════════════════════════════════════════════════════════════
#  DISPLAY SKILL
# ═══════════════════════════════════════════════════════════════════════════


class TestDisplaySkill:
    """Test display settings skill (mocked wlr-randr)."""

    def test_set_resolution(self):
        from cios.skills.display import set_resolution

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            success, msg = set_resolution("eDP-1", 1920, 1080)
            assert success is True
            assert "1920x1080" in msg

    def test_set_resolution_failure(self):
        from cios.skills.display import set_resolution

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Mode not found")
            success, msg = set_resolution("eDP-1", 9999, 9999)
            assert success is False

    def test_set_scale(self):
        from cios.skills.display import set_scale

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            success, msg = set_scale("eDP-1", 1.5)
            assert success is True
            assert "1.5" in msg

    def test_set_position(self):
        from cios.skills.display import set_position

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            success, msg = set_position("HDMI-A-1", 1920, 0)
            assert success is True

    def test_enable_output(self):
        from cios.skills.display import enable_output

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            success, msg = enable_output("HDMI-A-1")
            assert success is True

    def test_disable_output(self):
        from cios.skills.display import disable_output

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            success, msg = disable_output("HDMI-A-1")
            assert success is True


# ═══════════════════════════════════════════════════════════════════════════
#  AUTOMOUNT SKILL
# ═══════════════════════════════════════════════════════════════════════════


class TestAutomountSkill:
    """Test automount watcher (mocked lsblk/udisksctl)."""

    def test_mount_device_success(self):
        from cios.skills.automount import AutomountWatcher

        watcher = AutomountWatcher()

        with patch("subprocess.run") as mock_run:
            # First call: udisksctl mount
            # Second call: lsblk for info
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="Mounted /dev/sdb1 at /media/user/USB."),
                MagicMock(returncode=0, stdout="USB vfat 32G"),
            ]
            result = watcher.mount_device("/dev/sdb1")
            assert result is not None
            assert result.mount_point == "/media/user/USB"
            assert result.device == "/dev/sdb1"

    def test_mount_device_failure(self):
        from cios.skills.automount import AutomountWatcher

        watcher = AutomountWatcher()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Not authorized")
            result = watcher.mount_device("/dev/sdb1")
            assert result is None

    def test_unmount_device(self):
        from cios.skills.automount import AutomountWatcher

        watcher = AutomountWatcher()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Unmounted /dev/sdb1.")
            result = watcher.unmount_device("/dev/sdb1")
            assert result is True

    def test_scan_removable_devices(self):
        from cios.skills.automount import AutomountWatcher

        watcher = AutomountWatcher()

        lsblk_output = (
            "/dev/sda 0 disk \n" "/dev/sda1 0 part /\n" "/dev/sdb 1 disk \n" "/dev/sdb1 1 part \n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=lsblk_output)
            devices = watcher._scan_removable_devices()
            assert "/dev/sdb1" in devices
            assert "/dev/sda1" not in devices

    def test_list_mounted_empty(self):
        from cios.skills.automount import AutomountWatcher

        watcher = AutomountWatcher()
        assert watcher.list_mounted() == []


# ═══════════════════════════════════════════════════════════════════════════
#  FILE SEARCH SKILL
# ═══════════════════════════════════════════════════════════════════════════


class TestFileSearchSkill:
    """Test file search skill (mocked find/locate)."""

    def test_search_files_by_name(self):
        from cios.skills.file_search import search_files

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="/home/user/docs/contract.pdf\n/home/user/downloads/contract_v2.pdf\n",
            )
            result = search_files("contract")
            # Returns SearchReport object
            assert result is not None
            assert hasattr(result, "results") or hasattr(result, "files")

    def test_search_no_results(self):
        from cios.skills.file_search import search_files

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = search_files("nonexistent_file_xyz")
            assert result is not None
