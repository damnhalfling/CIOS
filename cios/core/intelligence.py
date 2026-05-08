"""Intelligence Client — connects CIOS to the cloud API.

Handles:
- Authentication state (JWT stored locally)
- Token optimization (compress input via Ollama before sending)
- API calls to api.cios-ia.com
- Usage tracking (local cache of remaining requests)
- Graceful degradation when offline

Usage:
    from cios.core.intelligence import intelligence
    result = intelligence.query("resuma as notícias do dia", intent="news")
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cios.core.config import CIOS_HOME

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

API_BASE = "https://api.cios-ia.com"
AUTH_FILE = CIOS_HOME / "intelligence.json"
FACE_PATH = Path.home() / ".face"

_TIMEOUT = 15  # seconds


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


@dataclass
class UsageInfo:
    """Current usage state."""

    used_today: int = 0
    limit_today: int = 5
    plan: str = "free"
    last_checked: float = 0.0


@dataclass
class IntelligenceResult:
    """Result from an Intelligence API call."""

    success: bool = False
    text: str = ""
    error: str = ""
    tokens_used: int = 0
    cached: bool = False


# ═══════════════════════════════════════════════════════════════════════════
#  TOKEN OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════


def _compress_input(text: str) -> str:
    """Compress verbose user input using local Ollama.

    Reduces ~300 tokens to ~50 tokens before sending to cloud API.
    If Ollama is unavailable, returns original text (graceful degradation).
    """
    from cios.core.config import get
    from cios.core.ollama_manager import is_ollama_healthy

    if not is_ollama_healthy():
        return text

    # Short inputs don't need compression
    if len(text.split()) <= 15:
        return text

    url = get("ollama_url")
    model = get("ollama_model")

    prompt = (
        f"Compress this user request into a minimal, clear instruction. "
        f"Keep the core intent and key details. Remove filler words. "
        f"Output ONLY the compressed version, nothing else.\n\n"
        f"Input: {text}\n"
        f"Compressed:"
    )

    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 60},
        }
    ).encode()

    try:
        req = urllib.request.Request(
            f"{url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            compressed = data.get("response", "").strip()
            if compressed and len(compressed) < len(text):
                logger.debug("Token Optimizer: %d→%d chars", len(text), len(compressed))
                return compressed
    except Exception as e:
        logger.debug("Token Optimizer failed (using original): %s", e)

    return text


# ═══════════════════════════════════════════════════════════════════════════
#  INTELLIGENCE CLIENT
# ═══════════════════════════════════════════════════════════════════════════


class IntelligenceClient:
    """Client for the CIOS Intelligence API."""

    def __init__(self) -> None:
        self._user: UserProfile | None = None
        self._usage = UsageInfo()
        self._lock = threading.Lock()
        self._load_auth()

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
            )
            self._usage.plan = self._user.plan
            self._usage.limit_today = _plan_limit(self._user.plan)
            logger.info("Intelligence auth loaded: %s (%s)", self._user.email, self._user.plan)
        except Exception as e:
            logger.warning("Failed to load intelligence auth: %s", e)

    def save_auth(self, token: str, user_data: dict) -> None:
        """Save authentication after successful login."""
        self._user = UserProfile(
            id=user_data.get("id", 0),
            email=user_data.get("email", ""),
            name=user_data.get("name", ""),
            picture=user_data.get("picture", ""),
            plan=user_data.get("plan", "free"),
            token=token,
        )
        self._usage.plan = self._user.plan
        self._usage.limit_today = _plan_limit(self._user.plan)

        # Save to disk
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
                },
                indent=2,
            )
        )
        # Restrict permissions (contains JWT)
        os.chmod(AUTH_FILE, 0o600)

        # Download profile picture for LightDM
        if self._user.picture:
            self._download_face(self._user.picture)

        logger.info("Intelligence auth saved: %s", self._user.email)

    def logout(self) -> None:
        """Clear authentication."""
        self._user = None
        self._usage = UsageInfo()
        if AUTH_FILE.exists():
            AUTH_FILE.unlink()
        logger.info("Intelligence logged out")

    def _download_face(self, url: str) -> None:
        """Download Google profile picture and save as ~/.face for LightDM."""
        try:
            # Google picture URLs often have =s96-c suffix, get larger version
            if "googleusercontent.com" in url:
                url = url.split("=")[0] + "=s256-c"

            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                img_data = resp.read()

            FACE_PATH.write_bytes(img_data)
            os.chmod(FACE_PATH, 0o644)
            logger.info("Profile picture saved to %s", FACE_PATH)
        except Exception as e:
            logger.debug("Failed to download profile picture: %s", e)

    # ─── API Calls ────────────────────────────────────────────────────

    def query(self, text: str, intent: str = "chat") -> IntelligenceResult:
        """Send a query to the Intelligence API.

        Flow:
        1. Check auth
        2. Check rate limit (local)
        3. Compress input (Token Optimizer)
        4. Call API
        5. Update usage
        """
        if not self.is_logged_in:
            return IntelligenceResult(
                success=False,
                error="not_logged_in",
                text="Faça login para usar o CIOS Intelligence.",
            )

        # Local rate limit check
        if self._usage.used_today >= self._usage.limit_today:
            return IntelligenceResult(
                success=False,
                error="rate_limited",
                text=f"Limite diário atingido ({self._usage.limit_today} consultas). "
                f"Renova amanhã ou faça upgrade.",
            )

        # Compress input
        compressed = _compress_input(text)

        # Call API
        result = self._call_api(compressed, intent)

        # Update local usage on success
        if result.success:
            self._usage.used_today += 1

        return result

    def _call_api(self, message: str, intent: str) -> IntelligenceResult:
        """Make the actual API call."""
        payload = json.dumps(
            {
                "message": message,
                "intent": intent,
            }
        ).encode()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._user.token}",
        }

        req = urllib.request.Request(
            f"{API_BASE}/chat",
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read())
                # The Maestro API returns the response text directly or in a structured format
                text = data.get("response", data.get("message", ""))
                if isinstance(text, dict):
                    text = text.get("content", str(text))
                return IntelligenceResult(
                    success=True,
                    text=str(text).strip(),
                    tokens_used=data.get("tokens", 0),
                )
        except urllib.error.HTTPError as e:
            if e.code == 401:
                logger.warning("Intelligence token expired")
                return IntelligenceResult(
                    success=False,
                    error="token_expired",
                    text="Sessão expirada. Faça login novamente.",
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
                    success=False,
                    error="api_error",
                    text="Erro no serviço. Tente novamente.",
                )
        except urllib.error.URLError as e:
            logger.warning("Intelligence API unreachable: %s", e)
            return IntelligenceResult(
                success=False,
                error="offline",
                text="Sem conexão com o CIOS Intelligence.",
            )
        except Exception as e:
            logger.warning("Intelligence API unexpected error: %s", e)
            return IntelligenceResult(
                success=False,
                error="unknown",
                text="Erro inesperado. Tente novamente.",
            )

    def check_usage(self) -> None:
        """Refresh usage info from API (background, non-blocking)."""
        if not self.is_logged_in:
            return

        def _fetch():
            try:
                req = urllib.request.Request(
                    f"{API_BASE}/auth/me",
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


# ═══════════════════════════════════════════════════════════════════════════
#  AUTH FLOW (Google OAuth via local HTTP callback)
# ═══════════════════════════════════════════════════════════════════════════


def start_auth_flow(on_complete: Callable[[bool, str], None] | None = None) -> None:
    """Start the Google OAuth flow.

    1. Opens browser to api.cios-ia.com/auth/google
    2. Starts a local HTTP server on port 7778 to capture the callback
    3. Saves JWT and user data
    4. Calls on_complete(success, message)
    """
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    auth_url = f"{API_BASE}/auth/google?state=cios&redirect_uri=http://localhost:7778/callback"

    result_holder = {"done": False, "success": False, "message": ""}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(self.path)

            if parsed.path == "/callback":
                params = parse_qs(parsed.query)
                token = params.get("token", [""])[0]
                user_json = params.get("user", [""])[0]

                if token and user_json:
                    try:
                        user_data = json.loads(user_json)
                        intelligence.save_auth(token, user_data)
                        result_holder["success"] = True
                        result_holder["message"] = f"Bem-vindo, {user_data.get('name', '')}!"

                        # Success page
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
            pass  # Suppress HTTP server logs

    def _run_server():
        try:
            server = HTTPServer(("localhost", 7778), CallbackHandler)
            server.timeout = 120  # 2 min timeout
            server.handle_request()  # Handle single request then stop
            server.server_close()
        except Exception as e:
            result_holder["message"] = f"Erro no servidor local: {e}"
            result_holder["done"] = True

        if on_complete:
            on_complete(result_holder["success"], result_holder["message"])

    # Start callback server in background
    threading.Thread(target=_run_server, daemon=True).start()

    # Open browser
    time.sleep(0.2)  # Give server time to start
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
