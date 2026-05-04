"""Tests for the Intent Parser module."""

import pytest

from harmoni.core.intent_parser import IntentType, Intent, parse_intent


class TestDevStart:
    """DEV_START intent detection."""

    @pytest.mark.parametrize("input_text,expected_target", [
        ("start my backend", "backend"),
        ("run the server", "server"),
        ("launch the app", "app"),
        ("boot the api", "api"),
        ("npm run dev", "dev"),
        ("yarn start", "start"),
        # PT-BR
        ("iniciar o backend", "backend"),
        ("rodar o servidor", "servidor"),
        ("subir o projeto", "projeto"),
        ("levantar o serviço", "serviço"),
    ])
    def test_dev_start_patterns(self, input_text, expected_target):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.DEV_START
        assert intent.params.get("target") == expected_target
        assert intent.confidence >= 0.90


class TestProcessControl:
    """PROCESS_CONTROL intent detection."""

    @pytest.mark.parametrize("input_text,expected_action,expected_port", [
        ("kill the process on port 3000", "kill", 3000),
        ("stop the server on port 8080", "kill", 8080),
        ("what's using port 5000", "query", 5000),
        ("what is running on port 443", "query", 443),
        # PT-BR
        ("matar o processo na porta 3000", "kill", 3000),
        ("parar o servidor na porta 8080", "kill", 8080),
        ("o que tá usando a porta 5000", "query", 5000),
    ])
    def test_process_control_patterns(self, input_text, expected_action, expected_port):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.PROCESS_CONTROL
        assert intent.params.get("action") == expected_action
        assert intent.params.get("port") == expected_port


class TestFixLastError:
    """FIX_LAST_ERROR intent detection."""

    @pytest.mark.parametrize("input_text", [
        "fix it",
        "fix the error",
        "fix last",
        "it crashed, fix it",
        # PT-BR
        "corrigir isso",
        "consertar o erro",
        "deu erro",
        "não funcionou",
    ])
    def test_fix_patterns(self, input_text):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.FIX_LAST_ERROR
        assert intent.confidence >= 0.85


class TestLogAnalysis:
    """LOG_ANALYSIS intent detection."""

    @pytest.mark.parametrize("input_text", [
        "show the logs",
        "check errors",
        "analyze the output",
        # PT-BR
        "mostrar os logs",
        "ver os erros",
        "o que aconteceu",
        "o que deu errado",
    ])
    def test_log_patterns(self, input_text):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.LOG_ANALYSIS
        assert intent.confidence >= 0.85


class TestFileOrganize:
    """FILE_ORGANIZE intent detection."""

    @pytest.mark.parametrize("input_text,expected_target", [
        ("organize my downloads", "downloads"),
        ("clean the desktop", "desktop"),
        ("sort my documents", "documents"),
        # PT-BR
        ("organizar meus downloads", "downloads"),
        ("arrumar a área de trabalho", "área de trabalho"),
        ("limpar os documentos", "documentos"),
    ])
    def test_file_organize_patterns(self, input_text, expected_target):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.FILE_ORGANIZE
        assert intent.params.get("target") == expected_target


class TestSystemHealth:
    """SYSTEM_HEALTH intent detection."""

    @pytest.mark.parametrize("input_text", [
        "my computer is slow",
        "system is lagging",
        "why is everything so slow",
        "check my system",
        # PT-BR
        "meu computador tá lento",
        "sistema tá travando",
        "porque tá lento",
        "tá pesado",
    ])
    def test_system_health_patterns(self, input_text):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.SYSTEM_HEALTH
        assert intent.confidence >= 0.85


class TestAppLaunch:
    """APP_LAUNCH intent detection."""

    @pytest.mark.parametrize("input_text,expected_app", [
        ("open chrome", "chrome"),
        ("launch firefox", "firefox"),
        ("open the terminal", "terminal"),
        # PT-BR
        ("abrir chrome", "chrome"),
        ("abre o firefox", "firefox"),
        ("abrir o terminal", "terminal"),
    ])
    def test_app_launch_patterns(self, input_text, expected_app):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.APP_LAUNCH
        assert intent.params.get("app") == expected_app


class TestSession:
    """SESSION intent detection."""

    @pytest.mark.parametrize("input_text,expected_action", [
        ("desligar", "shutdown"),
        ("desligar o computador", "shutdown"),
        ("power off", "shutdown"),
        ("restart", "reboot"),
        ("reiniciar", "reboot"),
        ("reiniciar o computador", "reboot"),
        ("suspend", "suspend"),
        ("suspender", "suspend"),
        ("hibernate", "hibernate"),
        ("hibernar", "hibernate"),
        ("logout", "logout"),
        ("sair", "logout"),
        ("lock", "lock"),
        ("bloquear", "lock"),
    ])
    def test_session_patterns(self, input_text, expected_action):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.SESSION
        assert intent.params.get("action") == expected_action


class TestNetwork:
    """NETWORK intent detection."""

    @pytest.mark.parametrize("input_text,expected_action", [
        ("conectar no wifi", "connect"),
        ("connect to wifi", "connect"),
        ("desconectar do wifi", "disconnect"),
        ("disconnect from wifi", "disconnect"),
        ("listar redes", "list"),
        ("show networks", "list"),
        ("qual minha rede", "status"),
        ("estou conectado", "status"),
    ])
    def test_network_patterns(self, input_text, expected_action):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.NETWORK
        assert intent.params.get("action") == expected_action

    def test_connect_with_ssid(self):
        intent = parse_intent("conectar na rede MinhaRede")
        assert intent.type == IntentType.NETWORK
        assert intent.params.get("action") == "connect"
        assert "MinhaRede" in intent.params.get("ssid", "")


class TestAudio:
    """AUDIO intent detection."""

    @pytest.mark.parametrize("input_text,expected_action", [
        ("aumentar volume", "up"),
        ("raise volume", "up"),
        ("diminuir volume", "down"),
        ("lower volume", "down"),
        ("silenciar", "mute"),
        ("mute", "mute"),
        ("tirar o mute", "unmute"),
        ("ativar o som", "unmute"),
        ("qual o volume", "status"),
    ])
    def test_audio_patterns(self, input_text, expected_action):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.AUDIO
        assert intent.params.get("action") == expected_action

    def test_set_volume(self):
        intent = parse_intent("volume 75")
        assert intent.type == IntentType.AUDIO
        assert intent.params.get("action") == "set"
        assert intent.params.get("level") == 75


class TestDiskAnalysis:
    """DISK_ANALYSIS intent detection."""

    @pytest.mark.parametrize("input_text", [
        "free up space",
        "liberar espaço",
        "disco cheio",
        "disk full",
        "quanto de espaço",
        "how much space",
        "o que tá ocupando meu disco",
        "limpar cache",
        "clean trash",
    ])
    def test_disk_patterns(self, input_text):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.DISK_ANALYSIS


class TestPower:
    """POWER intent detection."""

    @pytest.mark.parametrize("input_text,expected_action", [
        ("quanta bateria", "battery_status"),
        ("how much battery", "battery_status"),
        ("status da bateria", "battery_status"),
        ("aumentar brilho", "brightness_up"),
        ("diminuir brilho", "brightness_down"),
        ("brilho 50%", "brightness_set"),
        ("qual o brilho", "brightness_status"),
        ("modo economia", "power_saving"),
    ])
    def test_power_patterns(self, input_text, expected_action):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.POWER
        assert intent.params.get("action") == expected_action


class TestUnknown:
    """UNKNOWN intent for unrecognized inputs."""

    @pytest.mark.parametrize("input_text", [
        "",
        "asdfghjkl",
        "tell me a joke",
        "what is the meaning of life",
    ])
    def test_unknown_patterns(self, input_text):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.UNKNOWN

    def test_empty_input(self):
        intent = parse_intent("")
        assert intent.type == IntentType.UNKNOWN
        assert intent.confidence == 0.0

    def test_unknown_flags_complex_reasoning(self):
        intent = parse_intent("do something creative with my files")
        assert intent.type == IntentType.UNKNOWN
        assert intent.requires_complex_reasoning is True


class TestContinueProject:
    """CONTINUE_PROJECT intent detection."""

    @pytest.mark.parametrize("input_text,expected_project", [
        ("continuar projeto fidelidade", "fidelidade"),
        ("continuar no backend", "backend"),
        ("voltar pro frontend", "frontend"),
        ("continue project myapp", "myapp"),
        ("resume dashboard", "dashboard"),
    ])
    def test_continue_project_with_name(self, input_text, expected_project):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.CONTINUE_PROJECT
        assert intent.params.get("project") == expected_project
        assert intent.confidence >= 0.90

    @pytest.mark.parametrize("input_text", [
        "continuar",
        "continue",
    ])
    def test_continue_project_bare(self, input_text):
        intent = parse_intent(input_text)
        assert intent.type == IntentType.CONTINUE_PROJECT
        assert "project" not in intent.params
        assert intent.confidence >= 0.90
