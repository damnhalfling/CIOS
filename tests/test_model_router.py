"""Tests for the Model Router — retry, circuit breaker, local/external chain."""

from unittest.mock import MagicMock, patch

import pytest

from cios.core.model_router import (
    _call_external,
    _call_local,
    _circuit_is_open,
    _circuit_record_failure,
    _circuit_record_success,
    _circuit_state,
    _is_transient,
    _provider_is_configured,
    _retry_call,
    check_provider,
    get_fallback_status,
    get_no_provider_message,
    has_external_provider,
    request_execution_plan,
    reset_circuit_breaker,
    resolve_unknown_intent,
    route_to_llm,
)


class TestTransientDetection:
    """Identify transient vs permanent errors."""

    @pytest.mark.parametrize(
        "error",
        [
            "Connection timed out",
            "urllib.error.URLError: connection refused",
            "HTTP Error 503: Service Unavailable",
            "HTTP Error 429: Too Many Requests",
            "rate limit exceeded",
            "temporary failure in name resolution",
            "Connection reset by peer",
            "HTTP Error 502: Bad Gateway",
        ],
    )
    def test_transient_errors(self, error):
        assert _is_transient(error) is True

    @pytest.mark.parametrize(
        "error",
        [
            "Invalid API key",
            "Model not found",
            "Permission denied",
            "HTTP Error 401: Unauthorized",
            "JSON decode error",
        ],
    )
    def test_permanent_errors(self, error):
        assert _is_transient(error) is False


class TestRetryCall:
    """Retry logic with backoff."""

    def test_succeeds_first_try(self):
        fn = MagicMock(return_value="ok")
        result = _retry_call(fn, "prompt", "system", "test")
        assert result == "ok"
        assert fn.call_count == 1

    def test_gives_up_on_permanent_error(self):
        fn = MagicMock(side_effect=ValueError("Invalid API key"))
        result = _retry_call(fn, "prompt", "system", "test")
        assert result is None
        assert fn.call_count == 1

    def test_gives_up_after_max_retries(self):
        fn = MagicMock(side_effect=ConnectionError("connection refused"))
        with patch("cios.core.model_router.time.sleep"):
            result = _retry_call(fn, "prompt", "system", "test")
        assert result is None
        assert fn.call_count == 1  # no retries

    def test_returns_none_when_fn_returns_none(self):
        fn = MagicMock(return_value=None)
        result = _retry_call(fn, "prompt", "system", "test")
        assert result is None
        assert fn.call_count == 1


class TestLocalCall:
    """_call_local routes to Ollama."""

    def test_calls_ollama(self):
        with (
            patch("cios.core.model_router._circuit_is_open", return_value=False),
            patch("cios.core.model_router._retry_call", return_value='{"intent": "status"}'),
        ):
            result = _call_local("test prompt", "system")
            assert result == '{"intent": "status"}'

    def test_returns_none_when_circuit_open(self):
        with patch("cios.core.model_router._circuit_is_open", return_value=True):
            result = _call_local("test prompt", "system")
            assert result is None


class TestExternalCall:
    """_call_external routes to configured external providers."""

    def test_uses_openai_first(self):
        calls = []

        def mock_retry(fn, prompt, system, name):
            calls.append(name)
            if name == "openai":
                return '{"steps": ["apt install foo"]}'
            return None

        with (
            patch("cios.core.model_router._circuit_is_open", return_value=False),
            patch("cios.core.model_router._provider_is_configured", return_value=True),
            patch("cios.core.model_router._retry_call", side_effect=mock_retry),
        ):
            result = _call_external("test prompt", "system")
            assert result == '{"steps": ["apt install foo"]}'
            assert calls == ["openai"]

    def test_falls_back_to_cios_api(self):
        calls = []

        def mock_retry(fn, prompt, system, name):
            calls.append(name)
            if name == "cios_api":
                return '{"steps": ["snap install foo"]}'
            return None

        with (
            patch("cios.core.model_router._circuit_is_open", return_value=False),
            patch("cios.core.model_router._provider_is_configured", return_value=True),
            patch("cios.core.model_router._retry_call", side_effect=mock_retry),
        ):
            result = _call_external("test prompt", "system")
            assert result == '{"steps": ["snap install foo"]}'
            assert calls == ["openai", "anthropic", "cios_api"]

    def test_returns_none_when_no_provider_configured(self):
        with (
            patch("cios.core.model_router._circuit_is_open", return_value=False),
            patch("cios.core.model_router._provider_is_configured", return_value=False),
        ):
            result = _call_external("test prompt", "system")
            assert result is None


class TestHasExternalProvider:
    """Check if any external API is configured."""

    def test_always_true_because_cios_api_is_always_available(self):
        """CIOS API is always available as final fallback (free tier, no key needed)."""
        with patch("cios.core.model_router.config") as mock_config:
            mock_config.get.return_value = ""
            assert has_external_provider() is True

    def test_openai_configured(self):
        with patch("cios.core.model_router.config") as mock_config:
            mock_config.get.side_effect = lambda k: "sk-key" if k == "openai_api_key" else ""
            assert has_external_provider() is True

    def test_cios_api_configured(self):
        with patch("cios.core.model_router.config") as mock_config:
            mock_config.get.side_effect = lambda k: "cios-key" if k == "cios_api_key" else ""
            assert has_external_provider() is True


class TestNoProviderMessage:
    """User-friendly message when no external API is configured."""

    def test_message_contains_guidance(self):
        msg = get_no_provider_message()
        assert "cios --setup" in msg
        assert "conexão" in msg.lower() or "internet" in msg.lower()


class TestCircuitBreaker:
    """Circuit breaker prevents hammering dead providers."""

    def setup_method(self):
        _circuit_state.clear()

    def test_circuit_starts_closed(self):
        assert _circuit_is_open("ollama") is False

    def test_circuit_opens_after_threshold(self):
        _circuit_record_failure("ollama")
        assert _circuit_is_open("ollama") is True

    def test_circuit_stays_closed_before_failure(self):
        assert _circuit_is_open("ollama") is False

    def test_success_resets_circuit(self):
        _circuit_record_failure("ollama")
        _circuit_record_failure("ollama")
        _circuit_record_success("ollama")
        assert _circuit_is_open("ollama") is False
        assert _circuit_state["ollama"]["failures"] == 0

    def test_circuit_resets_after_timeout(self):
        import time as _time

        for _ in range(3):
            _circuit_record_failure("ollama")
        assert _circuit_is_open("ollama") is True

        _circuit_state["ollama"]["last_failure"] = _time.time() - 61
        assert _circuit_is_open("ollama") is False

    def test_manual_reset(self):
        for _ in range(3):
            _circuit_record_failure("ollama")
        assert _circuit_is_open("ollama") is True
        reset_circuit_breaker("ollama")
        assert _circuit_is_open("ollama") is False

    def test_manual_reset_all(self):
        for _ in range(3):
            _circuit_record_failure("ollama")
            _circuit_record_failure("openai")
        reset_circuit_breaker()
        assert _circuit_is_open("ollama") is False
        assert _circuit_is_open("openai") is False


class TestProviderConfigured:
    """Check if providers have necessary credentials."""

    def test_ollama_configured_when_reachable(self):
        with patch("cios.core.model_router._ollama_is_reachable", return_value=True):
            assert _provider_is_configured("ollama") is True

    def test_ollama_not_configured_when_unreachable(self):
        with patch("cios.core.model_router._ollama_is_reachable", return_value=False):
            assert _provider_is_configured("ollama") is False

    def test_openai_needs_key(self):
        with patch("cios.core.model_router.config") as mock_config:
            mock_config.get.return_value = ""
            assert _provider_is_configured("openai") is False

    def test_openai_configured_with_key(self):
        with patch("cios.core.model_router.config") as mock_config:
            mock_config.get.return_value = "sk-test-key"
            assert _provider_is_configured("openai") is True

    def test_cios_api_always_configured(self):
        """CIOS API is always available — no key required for free tier."""
        with patch("cios.core.model_router.config") as mock_config:
            mock_config.get.return_value = ""
            assert _provider_is_configured("cios_api") is True

    def test_cios_api_configured_with_key(self):
        with patch("cios.core.model_router.config") as mock_config:
            mock_config.get.return_value = "cios-test-key"
            assert _provider_is_configured("cios_api") is True


class TestFallbackStatus:
    """Diagnostics for provider health."""

    def setup_method(self):
        _circuit_state.clear()

    def test_returns_all_providers(self):
        with patch("cios.core.model_router._provider_is_configured", return_value=False):
            status = get_fallback_status()
            assert "ollama" in status["providers"]
            assert "openai" in status["providers"]
            assert "anthropic" in status["providers"]
            assert "cios_api" in status["providers"]

    def test_shows_circuit_state(self):
        for _ in range(3):
            _circuit_record_failure("openai")
        with patch("cios.core.model_router._provider_is_configured", return_value=True):
            status = get_fallback_status()
            assert status["providers"]["openai"]["circuit_open"] is True
            assert status["providers"]["openai"]["failures"] == 3


class TestRouteToLLM:
    """JSON parsing from local LLM responses."""

    def test_parses_clean_json(self):
        with patch(
            "cios.core.model_router._call_local",
            return_value='{"intent": "status", "params": {}, "plan": ["check"]}',
        ):
            result = route_to_llm("test")
            assert result["intent"] == "status"

    def test_extracts_json_from_text(self):
        with patch(
            "cios.core.model_router._call_local",
            return_value='Here is the result: {"intent": "status"} hope that helps',
        ):
            result = route_to_llm("test")
            assert result["intent"] == "status"

    def test_returns_none_on_no_json(self):
        with patch("cios.core.model_router._call_local", return_value="I don't understand"):
            result = route_to_llm("test")
            assert result is None

    def test_returns_none_when_provider_fails(self):
        with patch("cios.core.model_router._call_local", return_value=None):
            result = route_to_llm("test")
            assert result is None


class TestRequestExecutionPlan:
    """External API execution plan requests."""

    def test_returns_plan(self):
        plan_json = '{"explanation": "Instalando Docker", "steps": ["apt install docker.io"], "confirm": true}'
        with (
            patch("cios.core.model_router.has_external_provider", return_value=True),
            patch("cios.core.model_router._call_external", return_value=plan_json),
        ):
            result = request_execution_plan("instalar docker")
            assert result["explanation"] == "Instalando Docker"
            assert result["steps"] == ["apt install docker.io"]
            assert result["confirm"] is True

    def test_returns_none_when_no_provider(self):
        with patch("cios.core.model_router.has_external_provider", return_value=False):
            result = request_execution_plan("instalar docker")
            assert result is None

    def test_returns_none_when_external_fails(self):
        with (
            patch("cios.core.model_router.has_external_provider", return_value=True),
            patch("cios.core.model_router._call_external", return_value=None),
        ):
            result = request_execution_plan("instalar docker")
            assert result is None


class TestResolveUnknownIntent:
    """LLM-based intent resolution (local only)."""

    def test_resolves_valid_intent(self):
        with patch(
            "cios.core.model_router.route_to_llm",
            return_value={"intent": "system_health", "params": {}},
        ):
            intent = resolve_unknown_intent("my laptop feels warm")
            assert intent is not None
            assert intent.type.value == "system_health"
            assert intent.confidence == 0.7

    def test_returns_none_on_invalid_intent(self):
        with patch(
            "cios.core.model_router.route_to_llm",
            return_value={"intent": "nonexistent_intent"},
        ):
            intent = resolve_unknown_intent("do something weird")
            assert intent is None

    def test_returns_none_when_llm_fails(self):
        with patch("cios.core.model_router.route_to_llm", return_value=None):
            intent = resolve_unknown_intent("gibberish")
            assert intent is None


class TestCheckProvider:
    """Provider connectivity test."""

    def test_unknown_provider(self):
        ok, msg = check_provider("nonexistent")
        assert ok is False
        assert "Unknown" in msg
