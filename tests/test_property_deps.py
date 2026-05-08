"""Property-based tests for dependency graceful degradation.

Feature: produto-percebido
"""

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from cios.core.mcp import (
    AudioState,
    BluetoothState,
    WifiState,
    _scan_audio,
    _scan_bluetooth,
    _scan_known_networks,
    _scan_wifi,
)
from cios.infra.deps import DEPENDENCY_REGISTRY, check_and_install_deps

# --- Constants ---

# The 6 system tools referenced in the design document
ALL_SYSTEM_TOOLS = ["nmcli", "pactl", "wpctl", "bluetoothctl", "xdotool", "wmctrl"]


# --- Strategies ---

# Generate random subsets of system tools to mark as missing
_missing_tools_subset = st.lists(
    st.sampled_from(ALL_SYSTEM_TOOLS),
    unique=True,
    min_size=0,
    max_size=len(ALL_SYSTEM_TOOLS),
)


# --- Helpers ---


def _make_subprocess_side_effect(missing_set: set[str]):
    """Return a side_effect for subprocess.run that raises FileNotFoundError
    for commands whose first argument is in *missing_set*, and returns a
    neutral completed-process for everything else.
    """

    def _side_effect(args, *a, **kw):
        cmd = args if isinstance(args, str) else args[0] if args else ""
        if cmd in missing_set:
            raise FileNotFoundError(f"[Errno 2] No such file or directory: '{cmd}'")
        # Return a neutral "nothing found" result for present tools
        return MagicMock(returncode=1, stdout="", stderr="")

    return _side_effect


# --- Property Tests ---


class TestDependencyDegradation:
    """Property 13: Dependency checker degrades gracefully for any missing tool.

    Feature: produto-percebido, Property 13: Dependency checker degrades gracefully for any missing tool
    """

    @given(missing=_missing_tools_subset)
    @settings(max_examples=100)
    def test_mcp_scanners_return_safe_defaults_for_any_missing_subset(
        self,
        missing: list[str],
    ):
        """For any subset of system dependencies marked as missing,
        the MCP scanners return safe default states without raising exceptions.

        **Validates: Requirements 4.4**
        """
        missing_set = set(missing)
        side_effect = _make_subprocess_side_effect(missing_set)

        with patch("subprocess.run", side_effect=side_effect):
            # _scan_wifi uses nmcli
            if "nmcli" in missing_set:
                wifi = _scan_wifi()
                assert isinstance(wifi, WifiState)
                assert wifi.connected is False
                assert wifi.ssid == ""

            # _scan_audio uses pactl and wpctl
            if "pactl" in missing_set and "wpctl" in missing_set:
                audio = _scan_audio()
                assert isinstance(audio, AudioState)
                assert audio.volume == 0
                assert audio.muted is False

            # _scan_bluetooth uses bluetoothctl
            if "bluetoothctl" in missing_set:
                bt = _scan_bluetooth()
                assert isinstance(bt, BluetoothState)
                assert bt.available is False
                assert bt.connected_devices == []

            # _scan_known_networks uses nmcli
            if "nmcli" in missing_set:
                networks = _scan_known_networks()
                assert networks == []

    @given(missing=_missing_tools_subset)
    @settings(max_examples=100)
    def test_check_and_install_deps_never_crashes_for_any_missing_subset(
        self,
        missing: list[str],
    ):
        """For any subset of system dependencies marked as missing,
        check_and_install_deps returns a list of missing tool names
        without raising exceptions.

        **Validates: Requirements 4.4**
        """
        missing_set = set(missing)

        def fake_which(binary):
            if binary in missing_set:
                return None
            return f"/usr/bin/{binary}"

        with (
            patch("cios.infra.deps.shutil.which", side_effect=fake_which),
            patch("cios.infra.deps._try_install", return_value=False),
        ):
            result = check_and_install_deps()

        # Result must be a list
        assert isinstance(result, list)

        # Every tool in the missing subset that is in the registry should
        # appear in the result
        registry_binaries = {dep.binary for dep in DEPENDENCY_REGISTRY}
        for tool in missing:
            if tool in registry_binaries:
                assert tool in result, f"Expected '{tool}' in missing result but got: {result}"

        # Tools NOT in the missing subset should NOT appear in the result
        for tool_name in result:
            assert tool_name in missing_set or tool_name not in {t for t in ALL_SYSTEM_TOOLS}, (
                f"Tool '{tool_name}' reported missing but was not in the "
                f"missing subset: {missing}"
            )
