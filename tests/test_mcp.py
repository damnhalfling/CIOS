"""Tests for the MCP (Model Context Protocol) module."""

from unittest.mock import MagicMock, patch

from cios.core.mcp import (
    AudioState,
    BatteryState,
    ContextSnapshot,
    SystemContext,
    SystemState,
    WifiState,
    _scan_audio,
    _scan_battery,
    _scan_known_networks,
    _scan_system,
    _scan_wifi,
)


class TestDataStructures:
    """MCP data structures defaults."""

    def test_wifi_state_defaults(self):
        state = WifiState()
        assert state.connected is False
        assert state.ssid == ""
        assert state.signal == 0

    def test_audio_state_defaults(self):
        state = AudioState()
        assert state.volume == 0
        assert state.muted is False

    def test_battery_state_defaults(self):
        state = BatteryState()
        assert state.present is False
        assert state.percent == 100

    def test_system_state_defaults(self):
        state = SystemState()
        assert state.cpu_percent == 0.0
        assert state.cpu_cores == 1

    def test_context_snapshot_defaults(self):
        snap = ContextSnapshot()
        assert snap.wifi.connected is False
        assert snap.audio.volume == 0
        assert snap.running_apps == []
        assert snap.timestamp == 0.0


class TestScanWifi:
    """Wi-Fi scanning."""

    def test_scan_wifi_connected(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "yes:MinhaRede:85:wlan0\nno:OutraRede:60:wlan0"

        ip_result = MagicMock()
        ip_result.returncode = 0
        ip_result.stdout = "IP4.ADDRESS[1]:192.168.1.100/24"

        with patch("subprocess.run", side_effect=[mock_result, ip_result]):
            state = _scan_wifi()
            assert state.connected is True
            assert state.ssid == "MinhaRede"
            assert state.signal == 85
            assert state.device == "wlan0"
            assert state.ip == "192.168.1.100"

    def test_scan_wifi_disconnected(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "no:MinhaRede:85:wlan0"

        with patch("subprocess.run", return_value=mock_result):
            state = _scan_wifi()
            assert state.connected is False

    def test_scan_wifi_nmcli_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            state = _scan_wifi()
            assert state.connected is False


class TestScanAudio:
    """Audio scanning."""

    def test_scan_audio_normal(self):
        vol_result = MagicMock()
        vol_result.returncode = 0
        vol_result.stdout = "Volume: front-left: 49152 /  75% / -7.50 dB"

        mute_result = MagicMock()
        mute_result.returncode = 0
        mute_result.stdout = "Mute: no"

        sink_result = MagicMock()
        sink_result.returncode = 0
        sink_result.stdout = "alsa_output.pci-0000_00_1f.3.analog-stereo"

        with patch("subprocess.run", side_effect=[vol_result, mute_result, sink_result]):
            state = _scan_audio()
            assert state.volume == 75
            assert state.muted is False

    def test_scan_audio_muted(self):
        vol_result = MagicMock()
        vol_result.returncode = 0
        vol_result.stdout = "Volume: front-left: 49152 /  75%"

        mute_result = MagicMock()
        mute_result.returncode = 0
        mute_result.stdout = "Mute: yes"

        sink_result = MagicMock()
        sink_result.returncode = 0
        sink_result.stdout = "default"

        with patch("subprocess.run", side_effect=[vol_result, mute_result, sink_result]):
            state = _scan_audio()
            assert state.muted is True


class TestScanBattery:
    """Battery scanning."""

    def test_scan_battery_present(self):
        mock_battery = MagicMock()
        mock_battery.percent = 82.5
        mock_battery.power_plugged = False
        mock_battery.secsleft = 7200  # 2 hours

        with patch("psutil.sensors_battery", return_value=mock_battery):
            state = _scan_battery()
            assert state.present is True
            assert state.percent == 82
            assert state.charging is False
            assert "2h00m" in state.time_remaining

    def test_scan_battery_charging(self):
        mock_battery = MagicMock()
        mock_battery.percent = 60.0
        mock_battery.power_plugged = True
        mock_battery.secsleft = -1

        with patch("psutil.sensors_battery", return_value=mock_battery):
            state = _scan_battery()
            assert state.charging is True
            assert state.time_remaining == ""

    def test_scan_battery_not_present(self):
        with patch("psutil.sensors_battery", return_value=None):
            state = _scan_battery()
            assert state.present is False


class TestScanSystem:
    """System metrics scanning."""

    def test_scan_system_metrics(self):
        mock_mem = MagicMock()
        mock_mem.percent = 65.3
        mock_mem.used = 8 * 1024**3  # 8GB
        mock_mem.total = 16 * 1024**3  # 16GB

        mock_disk = MagicMock()
        mock_disk.percent = 45.0
        mock_disk.free = 200 * 1024**3  # 200GB

        with (
            patch("psutil.cpu_percent", return_value=25.5),
            patch("psutil.cpu_count", return_value=8),
            patch("psutil.virtual_memory", return_value=mock_mem),
            patch("psutil.disk_usage", return_value=mock_disk),
        ):
            state = _scan_system()
            assert state.cpu_percent == 25.5
            assert state.cpu_cores == 8
            assert state.mem_percent == 65.3
            assert state.mem_used_gb == 8.0
            assert state.mem_total_gb == 16.0
            assert state.disk_percent == 45.0


class TestScanKnownNetworks:
    """Known networks scanning."""

    def test_scan_known_networks(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "Casa:802-11-wireless\nTrabalho:802-11-wireless\nEthernet:802-3-ethernet"
        )

        with patch("subprocess.run", return_value=mock_result):
            networks = _scan_known_networks()
            assert "Casa" in networks
            assert "Trabalho" in networks
            assert len(networks) == 2  # Ethernet excluded


class TestSystemContext:
    """SystemContext singleton behavior."""

    def test_snapshot_returns_context(self):
        ctx = SystemContext()
        snap = ctx.snapshot()
        assert isinstance(snap, ContextSnapshot)

    def test_properties_accessible(self):
        ctx = SystemContext()
        assert isinstance(ctx.wifi, WifiState)
        assert isinstance(ctx.audio, AudioState)
        assert isinstance(ctx.battery, BatteryState)
        assert isinstance(ctx.system, SystemState)
        assert isinstance(ctx.running_apps, list)
        assert isinstance(ctx.known_networks, list)

    def test_start_and_stop(self):
        ctx = SystemContext()
        with patch.object(ctx, "_update"):
            ctx.start()
            assert ctx._running is True
            ctx.stop()
            assert ctx._running is False
