"""Tests for the Intelligence Client — E2E flow (mocked API).

Tests the full flow: auth → query → streaming → error handling.
Uses mocked HTTP responses to avoid hitting the real API.
"""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def intelligence_client(tmp_path):
    """Create a fresh IntelligenceClient with isolated state."""
    cios_home = tmp_path / ".cios"
    cios_home.mkdir()

    with (
        patch("cios.core.config.CIOS_HOME", cios_home),
        patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"),
        patch("cios.core.intelligence.SESSION_FILE", cios_home / "intelligence_session.json"),
        patch("cios.core.intelligence.FACE_PATH", tmp_path / ".face"),
    ):
        from cios.core.intelligence import IntelligenceClient

        client = IntelligenceClient()
        yield client


class TestAuthFlow:
    """Test authentication state management."""

    def test_not_logged_in_by_default(self, intelligence_client):
        assert not intelligence_client.is_logged_in
        assert intelligence_client.user is None

    def test_save_and_load_auth(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        auth_file = cios_home / "intelligence.json"

        with patch("cios.core.intelligence.AUTH_FILE", auth_file):
            intelligence_client.save_auth(
                token="test-jwt-token-123",
                user_data={
                    "id": 42,
                    "email": "user@example.com",
                    "name": "Test User",
                    "picture": "",
                    "plan": "starter",
                },
            )

        assert intelligence_client.is_logged_in
        assert intelligence_client.user.email == "user@example.com"
        assert intelligence_client.user.plan == "starter"
        assert intelligence_client.usage.limit_today == 50

    def test_logout_clears_state(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        auth_file = cios_home / "intelligence.json"
        session_file = cios_home / "intelligence_session.json"

        with (
            patch("cios.core.intelligence.AUTH_FILE", auth_file),
            patch("cios.core.intelligence.SESSION_FILE", session_file),
        ):
            intelligence_client.save_auth(
                token="token",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "free"},
            )
            assert intelligence_client.is_logged_in

            intelligence_client.logout()
            assert not intelligence_client.is_logged_in
            assert intelligence_client.user is None


class TestQuery:
    """Test synchronous query flow."""

    def test_query_requires_login(self, intelligence_client):
        result = intelligence_client.query("hello")
        assert not result.success
        assert result.error == "not_logged_in"

    def test_query_rate_limited(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        with patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"):
            intelligence_client.save_auth(
                token="token",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "free"},
            )
        # Exhaust the limit (free = 5)
        intelligence_client._usage.used_today = 5

        result = intelligence_client.query("test")
        assert not result.success
        assert result.error == "rate_limited"

    def test_query_success(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        with patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"):
            intelligence_client.save_auth(
                token="valid-token",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "pro"},
            )

        api_response = json.dumps(
            {
                "response": "As notícias de hoje incluem...",
                "intent": "news",
                "model": "deepseek-r1",
                "tokens_input": 45,
                "tokens_output": 120,
                "conversation_id": 789,
                "cognitive_state": {
                    "emotional_tone": 0.6,
                    "attention_focus": "news",
                    "memory_used": False,
                    "memory_sources": [],
                    "honesty_check": False,
                },
            }
        ).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = api_response
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("urllib.request.urlopen", return_value=mock_response),
            patch("cios.core.intelligence._compress_input", side_effect=lambda x: x),
        ):
            result = intelligence_client.query("resuma as notícias", intent="news")

        assert result.success
        assert "notícias" in result.text
        assert result.intent == "news"
        assert result.model == "deepseek-r1"
        assert result.tokens_input == 45
        assert result.tokens_output == 120
        assert result.conversation_id == 789
        assert result.cognitive_state is not None
        assert result.cognitive_state.attention_focus == "news"
        assert intelligence_client._usage.used_today == 1

    def test_query_offline(self, intelligence_client, tmp_path):
        import urllib.error

        cios_home = tmp_path / ".cios"
        with patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"):
            intelligence_client.save_auth(
                token="token",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "free"},
            )

        with (
            patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("Connection refused"),
            ),
            patch("cios.core.intelligence._compress_input", side_effect=lambda x: x),
        ):
            result = intelligence_client.query("test")

        assert not result.success
        assert result.error == "offline"

    def test_query_token_expired(self, intelligence_client, tmp_path):
        import urllib.error

        cios_home = tmp_path / ".cios"
        with patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"):
            intelligence_client.save_auth(
                token="expired-token",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "free"},
            )

        mock_error = urllib.error.HTTPError(
            url="https://api.cios-ai.com/v1/chat",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )

        with (
            patch("urllib.request.urlopen", side_effect=mock_error),
            patch("cios.core.intelligence._compress_input", side_effect=lambda x: x),
        ):
            result = intelligence_client.query("test")

        assert not result.success
        assert result.error == "token_expired"


class TestStreaming:
    """Test SSE streaming flow."""

    def test_stream_requires_login(self, intelligence_client):
        chunks = list(intelligence_client.stream("hello"))
        assert len(chunks) == 1
        assert chunks[0].type == "error"
        assert chunks[0].metadata["message"] == "not_logged_in"

    def test_stream_rate_limited(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        with patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"):
            intelligence_client.save_auth(
                token="token",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "free"},
            )
        intelligence_client._usage.used_today = 5

        chunks = list(intelligence_client.stream("test"))
        assert len(chunks) == 1
        assert chunks[0].type == "error"
        assert chunks[0].metadata["message"] == "rate_limited"

    def test_stream_success(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        with patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"):
            intelligence_client.save_auth(
                token="valid-token",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "pro"},
            )

        # Simulate SSE stream
        sse_data = (
            b'data: {"type":"start","conversation_id":100,"model":"deepseek-r1"}\n\n'
            b'data: {"type":"token","token":"Ol\\u00e1"}\n\n'
            b'data: {"type":"token","token":" mundo"}\n\n'
            b'data: {"type":"done","metadata":{"cognitive_state":{"emotional_tone":0.7,"attention_focus":"greeting","memory_used":false,"memory_sources":[],"honesty_check":false},"tokens_input":10,"tokens_output":2}}\n\n'
        )

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.__iter__ = MagicMock(
            return_value=iter([line + b"\n" for line in sse_data.split(b"\n")])
        )

        with (
            patch("urllib.request.urlopen", return_value=mock_response),
            patch("cios.core.intelligence._compress_input", side_effect=lambda x: x),
        ):
            chunks = list(intelligence_client.stream("olá", intent="chat"))

        types = [c.type for c in chunks]
        assert "start" in types
        assert "token" in types
        assert "done" in types

        tokens = [c.token for c in chunks if c.type == "token"]
        assert "Olá" in tokens
        assert " mundo" in tokens

        # Usage should be incremented
        assert intelligence_client._usage.used_today == 1
        # Conversation ID should be set
        assert intelligence_client._conversation_id == 100


class TestTokenOptimizer:
    """Test input compression via Ollama."""

    def test_short_input_not_compressed(self):
        from cios.core.intelligence import _compress_input

        with patch("cios.core.ollama_manager.is_ollama_healthy", return_value=True):
            result = _compress_input("abrir terminal")
            # Short inputs (<=15 words) pass through unchanged
            assert result == "abrir terminal"

    def test_compression_when_ollama_unavailable(self):
        from cios.core.intelligence import _compress_input

        long_text = "eu gostaria que você por favor pudesse me ajudar a entender como funciona o sistema de arquivos do linux incluindo permissões e ownership"
        with patch("cios.core.ollama_manager.is_ollama_healthy", return_value=False):
            result = _compress_input(long_text)
            # Returns original when Ollama is down
            assert result == long_text


class TestConversationContinuity:
    """Test conversation session persistence."""

    def test_new_conversation_clears_id(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        session_file = cios_home / "intelligence_session.json"

        with patch("cios.core.intelligence.SESSION_FILE", session_file):
            intelligence_client._conversation_id = 42
            intelligence_client.new_conversation()

        assert intelligence_client._conversation_id is None

    def test_conversation_id_persists_across_queries(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        with (
            patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"),
            patch("cios.core.intelligence.SESSION_FILE", cios_home / "intelligence_session.json"),
        ):
            intelligence_client.save_auth(
                token="token",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "pro"},
            )

        api_response = json.dumps(
            {
                "response": "Resposta 1",
                "intent": "chat",
                "model": "deepseek-r1",
                "tokens_input": 10,
                "tokens_output": 5,
                "conversation_id": 555,
                "cognitive_state": {},
            }
        ).encode()

        mock_response = MagicMock()
        mock_response.read.return_value = api_response
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("urllib.request.urlopen", return_value=mock_response),
            patch("cios.core.intelligence._compress_input", side_effect=lambda x: x),
        ):
            intelligence_client.query("primeira pergunta")

        assert intelligence_client._conversation_id == 555


class TestUsageLimits:
    """Test plan-based rate limiting."""

    def test_free_plan_limit(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        with patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"):
            intelligence_client.save_auth(
                token="t",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "free"},
            )
        assert intelligence_client.usage.limit_today == 5

    def test_starter_plan_limit(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        with patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"):
            intelligence_client.save_auth(
                token="t",
                user_data={
                    "id": 1,
                    "email": "a@b.com",
                    "name": "A",
                    "picture": "",
                    "plan": "starter",
                },
            )
        assert intelligence_client.usage.limit_today == 50

    def test_pro_plan_limit(self, intelligence_client, tmp_path):
        cios_home = tmp_path / ".cios"
        with patch("cios.core.intelligence.AUTH_FILE", cios_home / "intelligence.json"):
            intelligence_client.save_auth(
                token="t",
                user_data={"id": 1, "email": "a@b.com", "name": "A", "picture": "", "plan": "pro"},
            )
        assert intelligence_client.usage.limit_today == 200
