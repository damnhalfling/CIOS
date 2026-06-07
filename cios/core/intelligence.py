"""Intelligence Client — connects CIOS to the cloud API.

Handles:
- Authentication state (stored locally)
- SSE streaming from /v1/chat/stream
- Conversation continuity (persists conversation_id per session)
- Cognitive state tracking (mood, attention, memory usage)
- Intent forwarding (passes OS-classified intent to API)
- Graceful degradation when offline

Usage:
    from cios.core.intelligence import intelligence
    result = intelligence.query("resuma as notícias do dia", intent="news")

    # Streaming:
    for chunk in intelligence.stream("explica recursão", intent="explain"):
        print(chunk.token, end="")
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from pathlib import Path

from cios.core.config import CIOS_HOME

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

API_BASE = "https://api.cios-ai.com"
AUTH_FILE = CIOS_HOME / "intelligence.json"
SESSION_FILE = CIOS_HOME / "intelligence_session.json"
FACE_PATH = Path.home() / ".face"

_TIMEOUT = 30  # seconds (increased for streaming)
_STREAM_TIMEOUT = 60  # seconds for streaming connections


# ═══════════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class UserProfile:
    """Logged-in user profile."""

    id: int = 0
    email: str = ""
    name: str = ""
    picture: str = ""
    plan: str = "free"
    token: str = ""
    refresh_token: str = ""


@dataclass
class UsageInfo:
    """Current usage state."""

    used_today: int = 0
    limit_today: int = 5
    plan: str = "free"
    last_checked: float = 0.0


@dataclass
class CognitiveState:
    """Cognitive state returned by the API."""

    emotional_tone: float = 0.5
    attention_focus: str = ""
    memory_used: bool = False
    memory_sources: list = field(default_factory=list)
    honesty_check: bool = False


@dataclass
class IntelligenceResult:
    """Result from an Intelligence API call."""

    success: bool = False
    text: str = ""
    error: str = ""
    intent: str = ""
    model: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    conversation_id: int | None = None
    cognitive_state: CognitiveState | None = None
    cached: bool = False
    os_command: dict | None = None  # Executable command from Maestro for OS client


@dataclass
class StreamChunk:
    """A single chunk from SSE streaming."""

    type: str = ""  # "start" | "token" | "done" | "error"
    token: str = ""
    metadata: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════
#  TOKEN OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
#  INTELLIGENCE CLIENT
# ═══════════════════════════════════════════════════════════════════════════


class IntelligenceClient:
    """Client for the CIOS Intelligence API."""

    def __init__(self) -> None:
        self._user: UserProfile | None = None
        self._usage = UsageInfo()
        self._lock = threading.Lock()
        self._conversation_id: int | None = None
        self._last_cognitive_state: CognitiveState | None = None
        self._load_auth()
        self._load_session()

    # ─── Auth State ───────────────────────────────────────────────────

    @property
    def is_logged_in(self) -> bool:
        return self._user is not None and bool(self._user.token)

    @property
    def user(self) -> UserProfile | None:
        return self._user

    @property
    def usage(self) -> UsageInfo:
        return self._usage

    @property
    def conversation_id(self) -> int | None:
        return self._conversation_id

    @property
    def cognitive_state(self) -> CognitiveState | None:
        return self._last_cognitive_state

    def _load_auth(self) -> None:
        """Load saved authentication from disk."""
        if not AUTH_FILE.exists():
            return
        try:
            data = json.loads(AUTH_FILE.read_text())
            self._user = UserProfile(
                id=data.get("id", 0),
                email=data.get("email", ""),
                name=data.get("name", ""),
                picture=data.get("picture", ""),
                plan=data.get("plan", "free"),
                token=data.get("token", ""),
                refresh_token=data.get("refresh_token", ""),
            )
            self._usage.plan = self._user.plan
            self._usage.limit_today = _plan_limit(self._user.plan)
            logger.info("Intelligence auth loaded: %s (%s)", self._user.email, self._user.plan)
        except Exception as e:
            logger.warning("Failed to load intelligence auth: %s", e)

    def _load_session(self) -> None:
        """Start fresh conversation on each OS boot.

        Unlike the web client, the OS starts a new conversation each session.
        This prevents stale context (e.g. previous topic) from polluting responses.
        """
        self._conversation_id = None
        logger.debug("Session: new conversation (OS always starts fresh)")

    def _save_session(self) -> None:
        """Persist conversation session to disk."""
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(
                json.dumps(
                    {
                        "conversation_id": self._conversation_id,
                        "updated_at": time.time(),
                    }
                )
            )
        except Exception:
            pass

    def new_conversation(self) -> None:
        """Start a new conversation (clears conversation_id)."""
        self._conversation_id = None
        self._save_session()
        logger.info("New conversation started")

    def save_auth(self, token: str, user_data: dict, refresh_token: str = "") -> None:
        """Save authentication after successful login."""
        self._user = UserProfile(
            id=user_data.get("id", 0),
            email=user_data.get("email", ""),
            name=user_data.get("name", ""),
            picture=user_data.get("picture", ""),
            plan=user_data.get("plan", "free"),
            token=token,
            refresh_token=refresh_token,
        )
        self._usage.plan = self._user.plan
        self._usage.limit_today = _plan_limit(self._user.plan)

        AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTH_FILE.write_text(
            json.dumps(
                {
                    "id": self._user.id,
                    "email": self._user.email,
                    "name": self._user.name,
                    "picture": self._user.picture,
                    "plan": self._user.plan,
                    "token": token,
                    "refresh_token": refresh_token,
                },
                indent=2,
            )
        )
        os.chmod(AUTH_FILE, 0o600)

        if self._user.picture:
            self._download_face(self._user.picture)

        logger.info("Intelligence auth saved: %s", self._user.email)

    def logout(self) -> None:
        """Clear authentication and session."""
        self._user = None
        self._usage = UsageInfo()
        self._conversation_id = None
        if AUTH_FILE.exists():
            AUTH_FILE.unlink()
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
        logger.info("Intelligence logged out")

    def _download_face(self, url: str) -> None:
        """Download Google profile picture and save as ~/.face for LightDM."""
        try:
            if "googleusercontent.com" in url:
                url = url.split("=")[0] + "=s256-c"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                img_data = resp.read()
            FACE_PATH.write_bytes(img_data)
            os.chmod(FACE_PATH, 0o644)
        except Exception as e:
            logger.debug("Failed to download profile picture: %s", e)

    # ─── API Calls (Synchronous) ──────────────────────────────────────

    def query(self, text: str, intent: str = "chat") -> IntelligenceResult:
        """Send a query to the Intelligence API (synchronous, non-streaming).

        Flow:
        1. Check auth
        2. Check rate limit (local)
        3. Call /v1/chat with intent, client, conversation_id
        5. Parse cognitive_state + memory_sources
        6. Update usage and session
        7. If 401 → auto-refresh token and retry once
        """
        if not self.is_logged_in:
            return IntelligenceResult(
                success=False,
                error="not_logged_in",
                text="Faça login para usar o CIOS Intelligence.",
            )

        if self._usage.used_today >= self._usage.limit_today:
            return IntelligenceResult(
                success=False,
                error="rate_limited",
                text=f"Limite diário atingido ({self._usage.limit_today} consultas). "
                f"Renova amanhã ou faça upgrade.",
            )

        result = self._call_chat(text, intent)

        # Auto-retry after token refresh
        if result.error == "token_refreshed":
            result = self._call_chat(text, intent)

        if result.success:
            self._usage.used_today += 1
            if result.cognitive_state:
                self._last_cognitive_state = result.cognitive_state

        return result

    def _call_chat(self, message: str, intent: str) -> IntelligenceResult:
        """Call /v1/chat with full context."""
        payload = json.dumps(
            {
                "message": message,
                "intent": intent,
                "client": "os",
                "conversation_id": self._conversation_id,
                "system_context": _get_system_context(),
            }
        ).encode()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._user.token}",
        }

        req = urllib.request.Request(
            f"{API_BASE}/v1/chat",
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read())

                # Parse cognitive state
                cog = data.get("cognitive_state", {})
                cognitive_state = CognitiveState(
                    emotional_tone=cog.get("emotional_tone", 0.5),
                    attention_focus=cog.get("attention_focus", ""),
                    memory_used=cog.get("memory_used", False),
                    memory_sources=cog.get("memory_sources", []),
                    honesty_check=cog.get("honesty_check", False),
                )

                return IntelligenceResult(
                    success=True,
                    text=data.get("response", "").strip(),
                    intent=data.get("intent", intent),
                    model=data.get("model", ""),
                    tokens_input=data.get("tokens_input", 0),
                    tokens_output=data.get("tokens_output", 0),
                    conversation_id=data.get("conversation_id"),
                    cognitive_state=cognitive_state,
                    os_command=data.get("os_command"),
                )
        except urllib.error.HTTPError as e:
            return self._handle_http_error(e)
        except urllib.error.URLError as e:
            logger.warning("Intelligence API unreachable: %s", e)
            return IntelligenceResult(
                success=False, error="offline", text="Sem conexão com o CIOS Intelligence."
            )
        except Exception as e:
            logger.warning("Intelligence API unexpected error: %s", e)
            return IntelligenceResult(
                success=False, error="unknown", text="Erro inesperado. Tente novamente."
            )

    # ─── API Calls (Streaming) ────────────────────────────────────────

    def stream(self, text: str, intent: str = "chat") -> Generator[StreamChunk, None, None]:
        """Stream a response from /v1/chat/stream via SSE.

        Yields StreamChunk objects:
        - type="start": conversation started, metadata has conversation_id + model
        - type="token": a text token to display
        - type="done": stream complete, metadata has cognitive_state + token counts
        - type="error": error occurred

        Usage:
            for chunk in intelligence.stream("pergunta densa", intent="opinion"):
                if chunk.type == "token":
                    print(chunk.token, end="", flush=True)
                elif chunk.type == "done":
                    # Access metadata
                    pass
        """
        if not self.is_logged_in:
            yield StreamChunk(type="error", metadata={"message": "not_logged_in"})
            return

        if self._usage.used_today >= self._usage.limit_today:
            yield StreamChunk(type="error", metadata={"message": "rate_limited"})
            return

        payload = json.dumps(
            {
                "message": text,
                "intent": intent,
                "client": "os",
                "conversation_id": self._conversation_id,
                "system_context": _get_system_context(),
                "lang": "pt",
            }
        ).encode()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._user.token}",
            "Accept": "text/event-stream",
        }

        req = urllib.request.Request(
            f"{API_BASE}/v1/chat/stream",
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=_STREAM_TIMEOUT) as resp:
                buffer = ""
                for line_bytes in resp:
                    line = line_bytes.decode("utf-8", errors="replace")
                    buffer += line

                    # SSE format: "data: {...}\n\n"
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        chunk = self._parse_sse_event(event_str)
                        if chunk:
                            yield chunk

                            # Handle metadata updates
                            if chunk.type == "start":
                                # OS: don't persist conversation_id
                                pass
                            elif chunk.type == "done":
                                self._usage.used_today += 1
                                cog = chunk.metadata.get("cognitive_state", {})
                                if cog:
                                    self._last_cognitive_state = CognitiveState(
                                        emotional_tone=cog.get("emotional_tone", 0.5),
                                        attention_focus=cog.get("attention_focus", ""),
                                        memory_used=cog.get("memory_used", False),
                                        memory_sources=cog.get("memory_sources", []),
                                        honesty_check=cog.get("honesty_check", False),
                                    )

        except urllib.error.HTTPError as e:
            result = self._handle_http_error(e)
            yield StreamChunk(type="error", metadata={"message": result.error})
        except urllib.error.URLError:
            yield StreamChunk(type="error", metadata={"message": "offline"})
        except Exception as e:
            logger.warning("Stream error: %s", e)
            yield StreamChunk(type="error", metadata={"message": str(e)})

    def _parse_sse_event(self, event_str: str) -> StreamChunk | None:
        """Parse a single SSE event string into a StreamChunk."""
        for line in event_str.strip().split("\n"):
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    event_type = data.get("type", "")

                    if event_type == "token":
                        return StreamChunk(type="token", token=data.get("token", ""))
                    elif event_type == "start":
                        return StreamChunk(type="start", metadata=data)
                    elif event_type == "done":
                        return StreamChunk(type="done", metadata=data.get("metadata", {}))
                    elif event_type == "error":
                        return StreamChunk(type="error", metadata=data)
                except json.JSONDecodeError:
                    pass
        return None

    # ─── Error Handling ───────────────────────────────────────────────

    def _handle_http_error(self, e: urllib.error.HTTPError) -> IntelligenceResult:
        """Handle HTTP errors from the API."""
        if e.code == 401:
            # Try auto-refresh before giving up
            if self._try_refresh_token():
                logger.info("Token refreshed successfully, retry needed")
                return IntelligenceResult(
                    success=False, error="token_refreshed", text=""
                )
            logger.warning("Intelligence token expired and refresh failed")
            return IntelligenceResult(
                success=False, error="token_expired", text="Sessão expirada. Faça login novamente."
            )
        elif e.code == 429:
            return IntelligenceResult(
                success=False,
                error="rate_limited",
                text="Limite atingido. Tente novamente amanhã ou faça upgrade.",
            )
        else:
            logger.warning("Intelligence API error %d", e.code)
            return IntelligenceResult(
                success=False, error="api_error", text="Erro no serviço. Tente novamente."
            )

    def _try_refresh_token(self) -> bool:
        """Attempt to refresh the access token using the stored refresh_token.

        Returns True if refresh succeeded and self._user.token is updated.
        """
        if not self._user or not self._user.refresh_token:
            return False

        try:
            payload = json.dumps({"refresh_token": self._user.refresh_token}).encode()
            req = urllib.request.Request(
                f"{API_BASE}/v1/auth/refresh",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            new_token = data.get("token", "")
            if not new_token:
                return False

            # Update in-memory and on-disk
            self._user.token = new_token
            self.save_auth(
                new_token,
                {
                    "id": self._user.id,
                    "email": self._user.email,
                    "name": self._user.name,
                    "picture": self._user.picture,
                    "plan": self._user.plan,
                },
                refresh_token=self._user.refresh_token,
            )
            logger.info("Token auto-refreshed for %s", self._user.email)
            return True

        except Exception as e:
            logger.debug("Token refresh failed: %s", e)
            return False

    # ─── Usage Check ──────────────────────────────────────────────────

    def check_usage(self) -> None:
        """Refresh usage info from API (background, non-blocking)."""
        if not self.is_logged_in:
            return

        def _fetch():
            try:
                req = urllib.request.Request(
                    f"{API_BASE}/v1/auth/me",
                    headers={"Authorization": f"Bearer {self._user.token}"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    user = data.get("user", {})
                    if user:
                        self._user.plan = user.get("plan", self._user.plan)
                        self._usage.plan = self._user.plan
                        self._usage.limit_today = _plan_limit(self._user.plan)
            except Exception as e:
                logger.debug("Usage check failed: %s", e)

        threading.Thread(target=_fetch, daemon=True).start()

    def briefing(self) -> dict | None:
        """Fetch the daily briefing from the Intelligence API.

        Returns the briefing dict or None if unavailable.
        """
        if not self.is_logged_in:
            return None

        headers = {
            "Authorization": f"Bearer {self._user.token}",
        }

        req = urllib.request.Request(
            f"{API_BASE}/v1/briefing",
            headers=headers,
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning("Briefing fetch failed: %s", e)
            return None


# ═══════════════════════════════════════════════════════════════════════════
#  SYSTEM CONTEXT (sent with every API call from OS)
# ═══════════════════════════════════════════════════════════════════════════


def _get_system_context() -> dict:
    """Gather current OS context for API escalation."""
    import subprocess

    context = {
        "current_directory": os.getcwd(),
        "client": "os",
    }

    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            context["active_window"] = result.stdout.strip()
    except Exception:
        pass

    return context


# ═══════════════════════════════════════════════════════════════════════════
#  AUTH FLOW (Google OAuth via local HTTP callback)
# ═══════════════════════════════════════════════════════════════════════════


def start_auth_flow(on_complete: Callable[[bool, str], None] | None = None) -> None:
    """Start the authentication flow.

    1. Opens browser to the auth endpoint
    2. Starts a local HTTP server on port 7778 to capture the callback
    3. Saves credentials and user data
    4. Calls on_complete(success, message)
    """
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    auth_url = f"{API_BASE}/v1/auth/google?state=cios&redirect_uri=http://localhost:7778/callback"

    result_holder = {"done": False, "success": False, "message": ""}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)

            if parsed.path == "/callback":
                params = parse_qs(parsed.query)
                token = params.get("token", [""])[0]
                user_json = params.get("user", [""])[0]
                refresh_tok = params.get("refresh_token", [""])[0]

                if token and user_json:
                    try:
                        user_data = json.loads(user_json)
                        intelligence.save_auth(token, user_data, refresh_token=refresh_tok)
                        result_holder["success"] = True
                        result_holder["message"] = f"Bem-vindo, {user_data.get('name', '')}!"

                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(
                            b"<html><body style='background:#0a0a0f;color:#e2e2e8;"
                            b"font-family:sans-serif;text-align:center;padding:60px'>"
                            b"<h1>&#10004; Login realizado!</h1>"
                            b"<p>Pode fechar esta janela e voltar ao CIOS.</p>"
                            b"</body></html>"
                        )
                    except Exception as e:
                        result_holder["message"] = f"Erro no login: {e}"
                        self.send_response(400)
                        self.end_headers()
                else:
                    result_holder["message"] = "Token não recebido"
                    self.send_response(400)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

            result_holder["done"] = True

        def log_message(self, format, *args):
            pass

    def _run_server():
        try:
            server = HTTPServer(("localhost", 7778), CallbackHandler)
            server.timeout = 120
            server.handle_request()
            server.server_close()
        except Exception as e:
            result_holder["message"] = f"Erro no servidor local: {e}"
            result_holder["done"] = True

        if on_complete:
            on_complete(result_holder["success"], result_holder["message"])

    threading.Thread(target=_run_server, daemon=True).start()
    time.sleep(0.2)
    webbrowser.open(auth_url)


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _plan_limit(plan: str) -> int:
    """Get daily request limit for a plan."""
    limits = {
        "free": 5,
        "starter": 50,
        "pro": 200,
    }
    return limits.get(plan, 5)


# ═══════════════════════════════════════════════════════════════════════════
#  SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

intelligence = IntelligenceClient()
