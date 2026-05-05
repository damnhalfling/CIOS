"""Tests for the Model Router — retry, fallback chain, timeout, circuit breaker."""

from unittest.mock import patch, MagicMock

import pytest

from harmoni.core.model_router import (
    _call_provider,
    _is_transient,
    _retry_call,
    _circuit_is_open,
    _circuit_record_failure,
    _circuit_record_success,
    _circuit_state,
    _provider_is_configured,
    get_fallback_status,
    reset_circuit_breaker,
    route_to_llm,
    resolve_unknown_intent,
    check_provider,
)


class TestTransientDetection:
    """Identify transient vs permanent errors."""

    @pytest.mark.parametrize("error", [
        "Connection timed out",
        "urllib.error.URLError: connection refused",
        "HTTP Error 503: Service Unavailable",
        "HTTP Error 429: Too Many Requests",
        "rate limit exceeded",
        "temporary failure in name resolution",
        "Connection reset by peer",
        "HTTP Error 502: Bad Gateway",
    ])
    def test_transient_errors(self, error):
        assert _is_transient(error) is True

    @pytest.mark.parametrize("error", [
        "Invalid API key",
        "Model not found",
        "Permission denied",
        "HTTP Error 401: Unauthorized",
        "JSON decode error",
    ])
    def test_permanent_errors(self, error):
        assert _is_transient(error) is False


class TestRetryCall:
    """Retry logic with backoff."""

    def test_succeeds_first_try(self):
        fn = MagicMock(return_value="ok")
        result = _retry_call(fn, "prompt", "system", "test")
        assert result == "ok"
        assert fn.call_count == 1

    def test_retries_on_transient_error(self):
        fn = MagicMock(side_effect=[
            ConnectionError("connection refused"),
            "ok",
        ])
        with patch("harmoni.core.model_router.time.sleep"):
            result = _retry_call(fn, "prompt", "system", "test")
        assert result == "ok"
        assert fn.call_count == 2

    def test_gives_up_on_permanent_error(self):
        fn = MagicMock(side_effect=ValueError("Invalid API key"))
        result = _retry_call(fn, "prompt", "system", "test")
        assert result is None
        assert fn.call_count == 1  # no retry for permanent errors

    def test_gives_up_after_max_retries(self):
        fn = MagicMock(side_effect=ConnectionError("connection refused"))
        with patch("harmoni.core.model_router.time.sleep"):
            result = _retry_call(fn, "prompt", "system", "test")
        assert result is None
        assert fn.call_count == 2  # initial + 1 retry

    def test_returns_none_when_fn_returns_none(self):
        fn = MagicMock(return_value=None)
        result = _retry_call(fn, "prompt", "system", "test")
        assert result is None
        assert fn.call_count == 1  # no retry for None (not configured)


class TestFallbackChain:
    """Provider fallback chain: primary → all configured → None."""

    def test_primary_succeeds(self):
        with patch("harmoni.core.model_router.config") as mock_config, \
             patch("harmoni.core.model_router._retry_call") as mock_retry, \
             patch("harmoni.core.model_router._circuit_is_open", return_value=False):
            mock_config.get.return_value = "openai"
            mock_retry.return_value = '{"intent": "status"}'

            result = _call_provider("test prompt", "system")
            assert result == '{"intent": "status"}'
            # Should only call primary, not fallback
            assert mock_retry.call_count == 1

    def test_falls_back_to_ollama(self):
        call_count = {"n": 0}

        def mock_retry(fn, prompt, system, name):
            call_count["n"] += 1
            if name == "openai":
                return None  # primary fails
            if name == "ollama":
                return '{"intent": "status"}'  # fallback succeeds
            return None

        with patch("harmoni.core.model_router.config") as mock_config, \
             patch("harmoni.core.model_router._retry_call", side_effect=mock_retry), \
             patch("harmoni.core.model_router._circuit_is_open", return_value=False), \
             patch("harmoni.core.model_router._provider_is_configured", return_value=True):
            mock_config.get.return_value = "openai"

            result = _call_provider("test prompt", "system")
            assert result == '{"intent": "status"}'
            assert call_count["n"] == 2

    def test_all_providers_fail(self):
        with patch("harmoni.core.model_router.config") as mock_config, \
             patch("harmoni.core.model_router._retry_call", return_value=None), \
             patch("harmoni.core.model_router._circuit_is_open", return_value=False), \
             patch("harmoni.core.model_router._provider_is_configured", return_value=True):
            mock_config.get.return_value = "openai"

            result = _call_provider("test prompt", "system")
            assert result is None

    def test_ollama_primary_no_double_call(self):
        """When Ollama is primary and fails, don't try it again as fallback."""
        call_count = {"n": 0}

        def mock_retry(fn, prompt, system, name):
            call_count["n"] += 1
            return None

        with patch("harmoni.core.model_router.config") as mock_config, \
             patch("harmoni.core.model_router._retry_call", side_effect=mock_retry), \
             patch("harmoni.core.model_router._circuit_is_open", return_value=False), \
             patch("harmoni.core.model_router._provider_is_configured", return_value=False):
            mock_config.get.return_value = "ollama"

            result = _call_provider("test prompt", "system")
            assert result is None
            # Ollama as primary (1) + no other configured providers
            assert call_count["n"] == 1

    def test_skips_providers_with_open_circuit(self):
        """Providers with open circuit breaker are skipped."""
        call_count = {"n": 0}

        def mock_retry(fn, prompt, system, name):
            call_count["n"] += 1
            if name == "anthropic":
                return '{"intent": "status"}'
            return None

        def mock_circuit(provider):
            return provider == "ollama"  # ollama circuit is open

        with patch("harmoni.core.model_router.config") as mock_config, \
             patch("harmoni.core.model_router._retry_call", side_effect=mock_retry), \
             patch("harmoni.core.model_router._circuit_is_open", side_effect=mock_circuit), \
             patch("harmoni.core.model_router._provider_is_configured", return_value=True):
            mock_config.get.return_value = "openai"

            result = _call_provider("test prompt", "system")
            assert result == '{"intent": "status"}'
            # openai (primary, fails) + anthropic (succeeds), ollama skipped
            assert call_count["n"] == 2

    def test_falls_through_full_chain(self):
        """Tests the full fallback order: primary → ollama → openai → anthropic → bedrock."""
        calls = []

        def mock_retry(fn, prompt, system, name):
            calls.append(name)
            if name == "bedrock":
                return '{"intent": "status"}'
            return None

        with patch("harmoni.core.model_router.config") as mock_config, \
             patch("harmoni.core.model_router._retry_call", side_effect=mock_retry), \
             patch("harmoni.core.model_router._circuit_is_open", return_value=False), \
             patch("harmoni.core.model_router._provider_is_configured", return_value=True):
            mock_config.get.return_value = "openai"

            result = _call_provider("test prompt", "system")
            assert result == '{"intent": "status"}'
            # openai (primary) → ollama → anthropic → bedrock
            assert calls == ["openai", "ollama", "anthropic", "bedrock"]


class TestCircuitBreaker:
    """Circuit breaker prevents hammering dead providers."""

    def setup_method(self):
        """Reset circuit state before each test."""
        _circuit_state.clear()

    def test_circuit_starts_closed(self):
        assert _circuit_is_open("ollama") is False

    def test_circuit_opens_after_threshold(self):
        for _ in range(3):
            _circuit_record_failure("ollama")
        assert _circuit_is_open("ollama") is True

    def test_circuit_stays_closed_below_threshold(self):
        _circuit_record_failure("ollama")
        _circuit_record_failure("ollama")
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

        # Simulate time passing
        _circuit_state["ollama"]["last_failure"] = _time.time() - 61
        assert _circuit_is_open("ollama") is False  # half-open

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
        with patch("harmoni.core.model_router._ollama_is_reachable", return_value=True):
            assert _provider_is_configured("ollama") is True

    def test_ollama_not_configured_when_unreachable(self):
        with patch("harmoni.core.model_router._ollama_is_reachable", return_value=False):
            assert _provider_is_configured("ollama") is False

    def test_openai_needs_key(self):
        with patch("harmoni.core.model_router.config") as mock_config:
            mock_config.get.return_value = ""
            assert _provider_is_configured("openai") is False

    def test_openai_configured_with_key(self):
        with patch("harmoni.core.model_router.config") as mock_config:
            mock_config.get.return_value = "sk-test-key"
            assert _provider_is_configured("openai") is True

    def test_anthropic_needs_key(self):
        with patch("harmoni.core.model_router.config") as mock_config:
            mock_config.get.return_value = ""
            assert _provider_is_configured("anthropic") is False


class TestFallbackStatus:
    """Diagnostics for provider health."""

    def setup_method(self):
        _circuit_state.clear()

    def test_returns_all_providers(self):
        with patch("harmoni.core.model_router.config") as mock_config:
            mock_config.get.return_value = "ollama"
            status = get_fallback_status()
            assert status["primary"] == "ollama"
            assert "ollama" in status["providers"]
            assert "openai" in status["providers"]
            assert "anthropic" in status["providers"]
            assert "bedrock" in status["providers"]

    def test_shows_circuit_state(self):
        for _ in range(3):
            _circuit_record_failure("openai")
        with patch("harmoni.core.model_router.config") as mock_config:
            mock_config.get.return_value = "ollama"
            status = get_fallback_status()
            assert status["providers"]["openai"]["circuit_open"] is True
            assert status["providers"]["openai"]["failures"] == 3


class TestRouteToLLM:
    """JSON parsing from LLM responses."""

    def test_parses_clean_json(self):
        with patch("harmoni.core.model_router._call_provider",
                    return_value='{"intent": "status", "params": {}, "plan": ["check"]}'):
            result = route_to_llm("test")
            assert result["intent"] == "status"

    def test_extracts_json_from_text(self):
        with patch("harmoni.core.model_router._call_provider",
                    return_value='Here is the result: {"intent": "status"} hope that helps'):
            result = route_to_llm("test")
            assert result["intent"] == "status"

    def test_returns_none_on_no_json(self):
        with patch("harmoni.core.model_router._call_provider",
                    return_value="I don't understand"):
            result = route_to_llm("test")
            assert result is None

    def test_returns_none_when_provider_fails(self):
        with patch("harmoni.core.model_router._call_provider", return_value=None):
            result = route_to_llm("test")
            assert result is None


class TestResolveUnknownIntent:
    """LLM-based intent resolution."""

    def test_resolves_valid_intent(self):
        with patch("harmoni.core.model_router.route_to_llm",
                    return_value={"intent": "system_health", "params": {}}):
            intent = resolve_unknown_intent("my laptop feels warm")
            assert intent is not None
            assert intent.type.value == "system_health"
            assert intent.confidence == 0.7

    def test_returns_none_on_invalid_intent(self):
        with patch("harmoni.core.model_router.route_to_llm",
                    return_value={"intent": "nonexistent_intent"}):
            intent = resolve_unknown_intent("do something weird")
            assert intent is None

    def test_returns_none_when_llm_fails(self):
        with patch("harmoni.core.model_router.route_to_llm", return_value=None):
            intent = resolve_unknown_intent("gibberish")
            assert intent is None


class TestCheckProvider:
    """Provider connectivity test."""

    def test_unknown_provider(self):
        ok, msg = check_provider("nonexistent")
        assert ok is False
        assert "Unknown" in msg
