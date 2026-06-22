"""Tests for the dependency checker with graceful degradation."""

from unittest.mock import MagicMock, patch

from cios.infra.deps import (
    SYSTEM_REGISTRY,
    WAYLAND_REGISTRY,
    _build_registry,
    _has_passwordless_sudo,
    check_and_install_deps,
    get_degraded_features,
    get_missing_tools,
    is_tool_available,
)


class TestDependencyRegistry:
    """Verify the dependency registry is well-formed."""

    def test_system_registry_has_required_tools(self):
        binaries = {dep.binary for dep in SYSTEM_REGISTRY}
        assert "pactl" in binaries
        assert "wpctl" in binaries
        assert "bluetoothctl" in binaries
        assert "mpv" in binaries
        assert "ffmpeg" in binaries

    def test_wayland_registry_has_required_tools(self):
        binaries = {dep.binary for dep in WAYLAND_REGISTRY}
        assert "foot" in binaries
        assert "wl-copy" in binaries
        assert "wl-paste" in binaries
        assert "ollama" in binaries
        assert "nmcli" in binaries

    def test_build_registry_includes_all(self):
        """Registry includes core + feature deps."""
        registry = _build_registry()
        binaries = {dep.binary for dep in registry}
        # Core (critical)
        assert "foot" in binaries
        assert "wl-copy" in binaries
        assert "ollama" in binaries
        assert "nmcli" in binaries
        # Features (non-critical)
        assert "mpv" in binaries
        assert "ffmpeg" in binaries
        # No X11
        assert "xdotool" not in binaries
        assert "wmctrl" not in binaries

    def test_wayland_deps_are_critical(self):
        """Core deps are all critical."""
        for dep in WAYLAND_REGISTRY:
            assert dep.critical, f"{dep.binary} should be critical"

    def test_all_deps_have_degraded_messages(self):
        registry = _build_registry()
        for dep in registry:
            assert dep.degraded_msg, f"{dep.binary} missing degraded_msg"
            assert dep.feature, f"{dep.binary} missing feature name"
            assert dep.apt_package, f"{dep.binary} missing apt_package"

    def test_degraded_messages_are_humanized(self):
        """Degradation messages should be in PT-BR, not technical."""
        registry = _build_registry()
        for dep in registry:
            assert (
                "indisponível" in dep.degraded_msg or "indisponíveis" in dep.degraded_msg
            ), f"{dep.binary} degraded_msg should contain 'indisponível': {dep.degraded_msg}"


class TestCheckAndInstallDeps:
    """Test the main check_and_install_deps function."""

    def test_all_tools_present_returns_empty(self):
        """When all tools are present, returns empty list."""
        with patch("cios.infra.deps.shutil.which", return_value="/usr/bin/tool"):
            result = check_and_install_deps()
            assert result == []
            assert get_missing_tools() == set()
            assert get_degraded_features() == {}

    def test_missing_nmcli_tracked(self):
        """Missing nmcli is tracked as degraded."""

        def fake_which(binary):
            if binary == "nmcli":
                return None
            return f"/usr/bin/{binary}"

        with (
            patch("cios.infra.deps.shutil.which", side_effect=fake_which),
            patch("cios.infra.deps._try_install", return_value=False),
        ):
            result = check_and_install_deps()
            assert "nmcli" in result
            assert "nmcli" in get_missing_tools()
            assert "Controle de rede indisponível" in get_degraded_features().values()

    def test_missing_pactl_tracked(self):
        """Missing pactl is tracked as degraded."""

        def fake_which(binary):
            if binary == "pactl":
                return None
            return f"/usr/bin/{binary}"

        with (
            patch("cios.infra.deps.shutil.which", side_effect=fake_which),
            patch("cios.infra.deps._try_install", return_value=False),
        ):
            result = check_and_install_deps()
            assert "pactl" in result
            assert "Áudio indisponível" in get_degraded_features().values()

    def test_missing_bluetoothctl_tracked(self):
        """Missing bluetoothctl is tracked as degraded."""

        def fake_which(binary):
            if binary == "bluetoothctl":
                return None
            return f"/usr/bin/{binary}"

        with (
            patch("cios.infra.deps.shutil.which", side_effect=fake_which),
            patch("cios.infra.deps._try_install", return_value=False),
        ):
            result = check_and_install_deps()
            assert "bluetoothctl" in result
            assert "Bluetooth indisponível" in get_degraded_features().values()

    def test_successful_install_clears_missing(self):
        """After successful install, tools are no longer missing."""
        call_count = {"n": 0}

        def fake_which(binary):
            # First call: nmcli missing. After install: nmcli present.
            if binary == "nmcli":
                call_count["n"] += 1
                if call_count["n"] <= 1:
                    return None
                return "/usr/bin/nmcli"
            return f"/usr/bin/{binary}"

        with (
            patch("cios.infra.deps.shutil.which", side_effect=fake_which),
            patch("cios.infra.deps._try_install", return_value=True),
        ):
            result = check_and_install_deps()
            assert "nmcli" not in result

    def test_install_failure_logs_warning(self):
        """When install fails, tools remain in missing list."""

        def fake_which(binary):
            if binary == "nmcli":
                return None
            return f"/usr/bin/{binary}"

        with (
            patch("cios.infra.deps.shutil.which", side_effect=fake_which),
            patch("cios.infra.deps._try_install", return_value=False),
        ):
            result = check_and_install_deps()
            assert "nmcli" in result

    def test_multiple_missing_tools(self):
        """Multiple missing tools are all tracked."""
        missing_set = {"nmcli", "pactl", "bluetoothctl"}

        def fake_which(binary):
            if binary in missing_set:
                return None
            return f"/usr/bin/{binary}"

        with (
            patch("cios.infra.deps.shutil.which", side_effect=fake_which),
            patch("cios.infra.deps._try_install", return_value=False),
        ):
            result = check_and_install_deps()
            for tool in missing_set:
                assert tool in result
            assert len(get_degraded_features()) >= 3

    def test_is_tool_available_reflects_state(self):
        """is_tool_available returns correct state after check."""

        def fake_which(binary):
            if binary == "nmcli":
                return None
            return f"/usr/bin/{binary}"

        with (
            patch("cios.infra.deps.shutil.which", side_effect=fake_which),
            patch("cios.infra.deps._try_install", return_value=False),
        ):
            check_and_install_deps()
            assert is_tool_available("nmcli") is False
            assert is_tool_available("pactl") is True


class TestInstallStrategies:
    """Test the install strategy selection."""

    def test_has_passwordless_sudo_true(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch("cios.infra.deps.shutil.which", return_value="/usr/bin/sudo"),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert _has_passwordless_sudo() is True

    def test_has_passwordless_sudo_false(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with (
            patch("cios.infra.deps.shutil.which", return_value="/usr/bin/sudo"),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert _has_passwordless_sudo() is False

    def test_has_passwordless_sudo_no_sudo(self):
        with patch("cios.infra.deps.shutil.which", return_value=None):
            assert _has_passwordless_sudo() is False


class TestMCPScannerGracefulDegradation:
    """Verify MCP scanners return safe defaults when tools are missing."""

    def test_wifi_scanner_returns_default_on_missing_nmcli(self):
        from cios.core.mcp import WifiState, _scan_wifi

        with patch("subprocess.run", side_effect=FileNotFoundError("nmcli")):
            state = _scan_wifi()
            assert isinstance(state, WifiState)
            assert state.connected is False
            assert state.ssid == ""

    def test_audio_scanner_returns_default_on_missing_pactl_and_wpctl(self):
        from cios.core.mcp import AudioState, _scan_audio

        with patch("subprocess.run", side_effect=FileNotFoundError("pactl")):
            state = _scan_audio()
            assert isinstance(state, AudioState)
            assert state.volume == 0
            assert state.muted is False

    def test_bluetooth_scanner_returns_default_on_missing_bluetoothctl(self):
        from cios.core.mcp import BluetoothState, _scan_bluetooth

        with patch("subprocess.run", side_effect=FileNotFoundError("bluetoothctl")):
            state = _scan_bluetooth()
            assert isinstance(state, BluetoothState)
            assert state.available is False
            assert state.connected_devices == []

    def test_known_networks_returns_empty_on_missing_nmcli(self):
        from cios.core.mcp import _scan_known_networks

        with patch("subprocess.run", side_effect=FileNotFoundError("nmcli")):
            networks = _scan_known_networks()
            assert networks == []
