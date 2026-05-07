"""Tests for Bluetooth skill and intent parsing."""

from unittest.mock import patch, MagicMock
import subprocess

import pytest

from cios.core.intent_parser import parse_intent, IntentType


# ═══════════════════════════════════════════════════════════════════════════
#  INTENT PARSER — BLUETOOTH PATTERNS
# ═══════════════════════════════════════════════════════════════════════════

class TestBluetoothIntents:
    """Test Bluetooth intent pattern matching (PT + EN)."""

    # --- Power ---

    def test_ligar_bluetooth(self):
        i = parse_intent("ligar bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "power_on"

    def test_desligar_bluetooth(self):
        i = parse_intent("desligar o bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "power_off"

    def test_turn_on_bluetooth(self):
        i = parse_intent("turn on bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "power_on"

    def test_turn_off_bluetooth(self):
        i = parse_intent("turn off bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "power_off"

    def test_ativar_bt(self):
        i = parse_intent("ativar bt")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "power_on"

    def test_desativar_bt(self):
        i = parse_intent("desativar o bt")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "power_off"

    def test_bluetooth_on(self):
        i = parse_intent("bluetooth on")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "power_on"

    def test_bluetooth_off(self):
        i = parse_intent("bluetooth off")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "power_off"

    # --- Scan ---

    def test_escanear_bluetooth(self):
        i = parse_intent("escanear bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "scan"

    def test_scan_bluetooth(self):
        i = parse_intent("scan bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "scan"

    def test_buscar_dispositivos_bluetooth(self):
        i = parse_intent("buscar dispositivos bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "scan"

    def test_procurar_bluetooth(self):
        i = parse_intent("procurar bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "scan"

    def test_bluetooth_scan(self):
        i = parse_intent("bluetooth scan")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "scan"

    # --- List ---

    def test_listar_dispositivos(self):
        i = parse_intent("listar dispositivos bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "list"

    def test_mostrar_dispositivos(self):
        i = parse_intent("mostrar dispositivos")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "list"

    def test_show_devices(self):
        i = parse_intent("show devices")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "list"

    def test_list_paired_devices(self):
        i = parse_intent("listar dispositivos pareados")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "list"

    def test_quais_dispositivos(self):
        i = parse_intent("quais dispositivos pareados")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "list"

    # --- Connect ---

    def test_conectar_bluetooth(self):
        i = parse_intent("conectar bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "connect"

    def test_conectar_bluetooth_device(self):
        i = parse_intent("conectar bluetooth JBL Flip")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "connect"
        assert i.params["device"] == "JBL Flip"

    def test_connect_to_bluetooth(self):
        i = parse_intent("conectar bluetooth AirPods")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "connect"
        assert i.params["device"] == "AirPods"

    def test_parear_bluetooth(self):
        i = parse_intent("parear bluetooth Galaxy Buds")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "connect"
        assert i.params["device"] == "Galaxy Buds"

    def test_conectar_fone(self):
        i = parse_intent("conectar fone")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "connect"

    def test_conectar_caixa(self):
        i = parse_intent("conectar caixa")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "connect"

    # --- Disconnect ---

    def test_desconectar_bluetooth(self):
        i = parse_intent("desconectar do bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "disconnect"

    def test_disconnect_bluetooth(self):
        i = parse_intent("desconectar do fone")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "disconnect"

    def test_desconectar_fone(self):
        i = parse_intent("desconectar do headset")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "disconnect"

    # --- Remove ---

    def test_remover_dispositivo(self):
        i = parse_intent("remover bluetooth JBL Flip")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "remove"
        assert "JBL Flip" in i.params["device"]

    def test_esquecer_dispositivo(self):
        i = parse_intent("esquecer bluetooth Galaxy Buds")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "remove"

    # --- Status ---

    def test_status_bluetooth(self):
        i = parse_intent("status do bluetooth")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "status"

    def test_estado_do_bluetooth(self):
        i = parse_intent("estado do bt")
        assert i.type == IntentType.BLUETOOTH
        assert i.params["action"] == "status"


# ═══════════════════════════════════════════════════════════════════════════
#  BLUETOOTH SKILL
# ═══════════════════════════════════════════════════════════════════════════

class TestBluetoothSkill:
    """Test Bluetooth skill functions with mocked bluetoothctl."""

    def test_is_available_true(self):
        from cios.skills.bluetooth import is_available
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="Controller XX:XX:XX:XX:XX:XX\n\tPowered: yes\n",
                stderr="",
            )
            assert is_available() is True

    def test_is_available_false_no_controller(self):
        from cios.skills.bluetooth import is_available
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="No default controller",
            )
            assert is_available() is False

    def test_is_powered_on(self):
        from cios.skills.bluetooth import is_powered
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="Controller XX:XX\n\tPowered: yes\n",
                stderr="",
            )
            assert is_powered() is True

    def test_is_powered_off(self):
        from cios.skills.bluetooth import is_powered
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout="Controller XX:XX\n\tPowered: no\n",
                stderr="",
            )
            assert is_powered() is False

    def test_power_on(self):
        from cios.skills.bluetooth import power_on
        with patch("subprocess.run") as mock_run:
            # First call: is_powered check (returns off)
            # Second call: power on
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=0, stdout="Powered: no", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ]
            steps, ok, msg = power_on()
            assert ok is True

    def test_power_off(self):
        from cios.skills.bluetooth import power_off
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                subprocess.CompletedProcess(args=[], returncode=0, stdout="Powered: yes", stderr=""),
                subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ]
            steps, ok, msg = power_off()
            assert ok is True

    def test_parse_device_list(self):
        from cios.skills.bluetooth import _parse_device_list
        output = (
            "Device AA:BB:CC:DD:EE:FF JBL Flip 5\n"
            "Device 11:22:33:44:55:66 Galaxy Buds Pro\n"
        )
        devices = _parse_device_list(output)
        assert len(devices) == 2
        assert devices[0].address == "AA:BB:CC:DD:EE:FF"
        assert devices[0].name == "JBL Flip 5"
        assert devices[1].name == "Galaxy Buds Pro"

    def test_humanize_error_not_available(self):
        from cios.skills.bluetooth import _humanize_error
        assert "not available" in _humanize_error("No default controller available").lower()

    def test_humanize_error_pair_failed(self):
        from cios.skills.bluetooth import _humanize_error
        result = _humanize_error("Failed to pair")
        assert "pairing" in result.lower()

    def test_humanize_error_timeout(self):
        from cios.skills.bluetooth import _humanize_error
        result = _humanize_error("Operation timed out")
        assert "timed out" in result.lower()

    def test_humanize_error_not_installed(self):
        from cios.skills.bluetooth import _humanize_error
        result = _humanize_error("bluetoothctl not found — BlueZ not installed")
        assert "not installed" in result.lower() or "not found" in result.lower()

    def test_device_type_icon(self):
        from cios.skills.bluetooth import BluetoothDevice
        dev = BluetoothDevice(address="AA:BB:CC:DD:EE:FF", name="Test", icon="audio-headset")
        assert dev.type_icon == "🎧"

    def test_device_type_icon_unknown(self):
        from cios.skills.bluetooth import BluetoothDevice
        dev = BluetoothDevice(address="AA:BB:CC:DD:EE:FF", name="Test", icon="unknown-type")
        assert dev.type_icon == "📶"

    def test_device_display_name(self):
        from cios.skills.bluetooth import BluetoothDevice
        dev = BluetoothDevice(address="AA:BB:CC:DD:EE:FF", name="JBL Flip")
        assert dev.display_name == "JBL Flip"

    def test_device_display_name_fallback(self):
        from cios.skills.bluetooth import BluetoothDevice
        dev = BluetoothDevice(address="AA:BB:CC:DD:EE:FF", name="AA:BB:CC:DD:EE:FF")
        assert dev.display_name == "AA:BB:CC:DD:EE:FF"
