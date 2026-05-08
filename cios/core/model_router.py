"""Model router — routes LLM calls to the configured provider.

Resolution chain:
1. Intent Parser (regex hardcoded, 180+ patterns) — handles 80%+
2. Ollama (local LLM) — classifies intent + resolves local commands
3. External API (only when local can't resolve) — generates execution plans
   - OpenAI (client's own key)
   - Anthropic (client's own key)
   - CIOS API (paid service, Bedrock behind the scenes)

The external API is ONLY called when:
- The intent requires knowledge the local model doesn't have
- Example: installing software that needs external sources, complex configs

Retry with exponential backoff on transient failures.
Circuit breaker prevents hammering dead providers.
"""

from __future__ import annotations

import json
import logging
import time

from cios.core import config
from cios.core.intent_parser import Intent, IntentType

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  RETRY / TIMEOUT CONFIG
# ═══════════════════════════════════════════════════════════════════════════

_MAX_RETRIES = 1
_RETRY_BACKOFF = [0.5]  # seconds between retries
_PROVIDER_TIMEOUTS = {
    "ollama": 15,
    "openai": 15,
    "anthropic": 15,
    "cios_api": 15,
}

# Transient errors worth retrying
_TRANSIENT_ERRORS = (
    "timed out",
    "timeout",
    "connection refused",
    "connection reset",
    "temporary failure",
    "503",
    "502",
    "429",
    "rate limit",
)

# ═══════════════════════════════════════════════════════════════════════════
#  CIRCUIT BREAKER — avoid hammering dead providers
# ═══════════════════════════════════════════════════════════════════════════

_CIRCUIT_BREAKER_THRESHOLD = 3  # failures before opening circuit
_CIRCUIT_BREAKER_RESET_TIME = 60  # seconds before retrying a broken provider

# State: {provider_name: {"failures": int, "last_failure": float, "open": bool}}
_circuit_state: dict[str, dict] = {}


def _circuit_is_open(provider: str) -> bool:
    """Check if circuit breaker is open (provider is considered dead)."""
    state = _circuit_state.get(provider)
    if not state or not state.get("open"):
        return False
    elapsed = time.time() - state.get("last_failure", 0)
    if elapsed >= _CIRCUIT_BREAKER_RESET_TIME:
        state["open"] = False
        state["failures"] = 0
        logger.info("Circuit breaker for %s reset (%.0fs elapsed)", provider, elapsed)
        return False
    return True


def _circuit_record_failure(provider: str) -> None:
    """Record a failure for circuit breaker tracking."""
    state = _circuit_state.setdefault(provider, {"failures": 0, "last_failure": 0, "open": False})
    state["failures"] += 1
    state["last_failure"] = time.time()
    if state["failures"] >= _CIRCUIT_BREAKER_THRESHOLD:
        state["open"] = True
        logger.warning(
            "Circuit breaker OPEN for %s (%d consecutive failures)", provider, state["failures"]
        )


def _circuit_record_success(provider: str) -> None:
    """Record a success — resets the circuit breaker."""
    if provider in _circuit_state:
        _circuit_state[provider] = {"failures": 0, "last_failure": 0, "open": False}


def _is_transient(error: str) -> bool:
    """Check if an error is transient and worth retrying."""
    lower = error.lower()
    return any(t in lower for t in _TRANSIENT_ERRORS)


def _retry_call(fn, prompt: str, system: str, provider_name: str) -> str | None:
    """Call a provider function with retry + exponential backoff."""
    last_error = ""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = fn(prompt, system)
            if result:
                if attempt > 0:
                    logger.info("Provider %s succeeded on attempt %d", provider_name, attempt + 1)
                _circuit_record_success(provider_name)
                return result
            return None
        except Exception as e:
            last_error = str(e)
            if attempt < _MAX_RETRIES and _is_transient(last_error):
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                logger.info(
                    "Provider %s attempt %d failed (%s), retrying in %.1fs",
                    provider_name,
                    attempt + 1,
                    last_error[:80],
                    wait,
                )
                time.sleep(wait)
            else:
                logger.warning(
                    "Provider %s failed after %d attempts: %s",
                    provider_name,
                    attempt + 1,
                    last_error[:120],
                )
                _circuit_record_failure(provider_name)
                return None
    _circuit_record_failure(provider_name)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  PROVIDER IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════


def _call_ollama(prompt: str, system: str = "") -> str | None:
    """Call local Ollama model."""
    import urllib.error
    import urllib.request

    url = config.get("ollama_url")
    model = config.get("ollama_model")
    timeout = _PROVIDER_TIMEOUTS["ollama"]

    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 256},
        }
    ).encode()

    req = urllib.request.Request(
        f"{url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip() or None
    except urllib.error.URLError as e:
        raise ConnectionError(f"Ollama connection failed: {e}") from e
    except TimeoutError:
        raise TimeoutError(f"Ollama timed out after {timeout}s") from None


def _call_openai(prompt: str, system: str = "") -> str | None:
    """Call OpenAI API (client's own key)."""
    import urllib.error
    import urllib.request

    api_key = config.get("openai_api_key")
    if not api_key:
        return None

    model = config.get("openai_model")
    timeout = _PROVIDER_TIMEOUTS["openai"]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 512,
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip() or None
    except urllib.error.HTTPError as e:
        raise ConnectionError(f"OpenAI HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"OpenAI connection failed: {e}") from e
    except TimeoutError:
        raise TimeoutError(f"OpenAI timed out after {timeout}s") from None


def _call_anthropic(prompt: str, system: str = "") -> str | None:
    """Call Anthropic API (client's own key)."""
    import urllib.error
    import urllib.request

    api_key = config.get("anthropic_api_key")
    if not api_key:
        return None

    model = config.get("anthropic_model")
    timeout = _PROVIDER_TIMEOUTS["anthropic"]

    payload = json.dumps(
        {
            "model": model,
            "max_tokens": 512,
            "temperature": 0.1,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"].strip() or None
    except urllib.error.HTTPError as e:
        raise ConnectionError(f"Anthropic HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"Anthropic connection failed: {e}") from e
    except TimeoutError:
        raise TimeoutError(f"Anthropic timed out after {timeout}s") from None


def _call_cios_api(prompt: str, system: str = "") -> str | None:
    """Call CIOS API (paid service — powered by Bedrock behind the scenes).

    This is the official CIOS cloud API. Users subscribe at ciosia.com
    and get an API key. No AWS credentials needed on their end.
    """
    import urllib.error
    import urllib.request

    api_key = config.get("cios_api_key")
    if not api_key:
        return None

    api_url = config.get("cios_api_url")
    timeout = _PROVIDER_TIMEOUTS["cios_api"]

    payload = json.dumps(
        {
            "prompt": prompt,
            "system": system,
            "max_tokens": 512,
            "temperature": 0.1,
        }
    ).encode()

    req = urllib.request.Request(
        f"{api_url}/v1/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("content", "").strip() or None
    except urllib.error.HTTPError as e:
        raise ConnectionError(f"CIOS API HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise ConnectionError(f"CIOS API connection failed: {e}") from e
    except TimeoutError:
        raise TimeoutError(f"CIOS API timed out after {timeout}s") from None


# ═══════════════════════════════════════════════════════════════════════════
#  EXTERNAL API AVAILABILITY CHECK
# ═══════════════════════════════════════════════════════════════════════════


def has_external_provider() -> bool:
    """Check if any external API provider is configured."""
    return bool(
        config.get("openai_api_key")
        or config.get("anthropic_api_key")
        or config.get("cios_api_key")
    )


def get_no_provider_message() -> str:
    """Return a user-friendly message when no external API is configured.

    This is shown when the system needs external knowledge (e.g., how to
    install something that requires adding sources, complex configurations).
    """
    return (
        "Preciso de acesso a uma API externa para resolver isso, "
        "mas nenhuma está configurada.\n\n"
        "Opções:\n"
        "  1. CIOS API (assinatura em ciosia.com) — mais simples\n"
        "  2. Sua própria chave OpenAI ou Anthropic\n\n"
        "Configure com: cios --setup\n"
        "Ou defina a variável: CIOS_API_KEY, OPENAI_API_KEY ou ANTHROPIC_API_KEY"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  ROUTER
# ═══════════════════════════════════════════════════════════════════════════

_PROVIDERS = {
    "ollama": _call_ollama,
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "cios_api": _call_cios_api,
}

# System prompt for intent resolution (Ollama — local classification)
_SYSTEM_CLASSIFY = (
    "You are the reasoning engine of CIOS. "
    "Given a user request and optional context (logs, errors, memory), "
    "respond ONLY with a JSON object: "
    '{"intent": "<intent_type>", "params": {}, "plan": ["step1", "step2"]}. '
    "Valid intents: dev_start, process_control, log_analysis, fix_last_error, "
    "command_exec, status, app_launch, session, bluetooth. "
    "Keep plans to 2-5 steps max. Be precise."
)

# System prompt for execution plan (External API — complex tasks)
_SYSTEM_PLAN = (
    "You are the execution planner of CIOS, a Linux intent-based OS. "
    "The user needs something that requires external knowledge (installing "
    "software, adding repositories, complex configurations). "
    "Respond ONLY with a JSON object:\n"
    '{"explanation": "brief explanation of what will be done", '
    '"steps": ["shell command 1", "shell command 2", ...], '
    '"confirm": true}\n'
    "Rules:\n"
    "- Use apt, snap, flatpak, or curl as appropriate for the distro (Debian/Ubuntu)\n"
    "- Include adding GPG keys and sources when needed\n"
    "- Always use -y flag for non-interactive installs\n"
    "- If unsure, set confirm: true so the user approves\n"
    "- Keep explanations short (1-2 sentences, Portuguese)\n"
    "- Never include dangerous commands (rm -rf /, dd, etc.)\n"
    "- Max 10 steps"
)


def _call_local(prompt: str, system: str = "") -> str | None:
    """Call Ollama (local LLM). First choice after regex."""
    if _circuit_is_open("ollama"):
        return None
    return _retry_call(_call_ollama, prompt, system, "ollama")


def _call_external(prompt: str, system: str = "") -> str | None:
    """Call external API provider (only when local can't resolve).

    Priority: client's own key first, CIOS API as fallback.
    Returns None if no provider is configured (caller should show message).
    """
    # Priority order for external providers
    _EXTERNAL_ORDER = ["openai", "anthropic", "cios_api"]

    for provider in _EXTERNAL_ORDER:
        if _circuit_is_open(provider):
            continue
        if not _provider_is_configured(provider):
            continue
        call_fn = _PROVIDERS[provider]
        result = _retry_call(call_fn, prompt, system, provider)
        if result:
            logger.info("External provider '%s' resolved the request", provider)
            return result

    return None


def _provider_is_configured(provider: str) -> bool:
    """Check if a provider has the necessary credentials configured."""
    if provider == "ollama":
        return _ollama_is_reachable()
    if provider == "openai":
        return bool(config.get("openai_api_key"))
    if provider == "anthropic":
        return bool(config.get("anthropic_api_key"))
    if provider == "cios_api":
        return bool(config.get("cios_api_key"))
    return False


# Cache Ollama reachability for 30s to avoid repeated socket checks
_ollama_cache: dict = {"reachable": False, "checked_at": 0.0}


def _ollama_is_reachable() -> bool:
    """Quick check if Ollama is running (cached for 30s)."""
    now = time.time()
    if now - _ollama_cache["checked_at"] < 30:
        return _ollama_cache["reachable"]

    import urllib.error
    import urllib.request

    url = config.get("ollama_url")
    try:
        req = urllib.request.Request(f"{url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1):
            _ollama_cache.update(reachable=True, checked_at=now)
            return True
    except Exception:
        _ollama_cache.update(reachable=False, checked_at=now)
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════


def route_to_llm(prompt: str, complex: bool = False) -> dict | None:
    """Route a prompt to the local LLM and parse the JSON response.

    This is for intent classification — always uses Ollama first.
    """
    raw = _call_local(prompt, system=_SYSTEM_CLASSIFY)

    if raw is None:
        return None

    return _parse_json_response(raw)


def request_execution_plan(user_input: str, context: str = "") -> dict | None:
    """Request an execution plan from an external API.

    Called when the local LLM can't resolve something that needs
    external knowledge (e.g., installing software with custom sources).

    Returns:
        {"explanation": str, "steps": [str], "confirm": bool}
        or None if no external provider is available.
    """
    if not has_external_provider():
        return None

    prompt = f'User request: "{user_input}"\n'
    if context:
        prompt += f"System context: {context}\n"
    prompt += "Generate an execution plan."

    raw = _call_external(prompt, system=_SYSTEM_PLAN)
    if raw is None:
        return None

    return _parse_json_response(raw)


def resolve_unknown_intent(user_input: str, context: str = "") -> Intent | None:
    """Use local LLM to resolve an intent that pattern matching couldn't handle.

    Only uses Ollama. If Ollama can't resolve, returns None.
    The caller decides whether to escalate to external API.
    """
    prompt = f'User said: "{user_input}"\n'
    if context:
        prompt += f"Context: {context}\n"
    prompt += "Determine the intent and create a plan."

    result = route_to_llm(prompt, complex=True)
    if result and "intent" in result:
        try:
            intent_type = IntentType(result["intent"])
        except ValueError:
            return None
        return Intent(
            type=intent_type,
            confidence=0.7,
            params=result.get("params", {}),
            raw_input=user_input,
        )
    return None


def is_any_provider_available() -> bool:
    """Quick check if any LLM provider is likely available (no network call).

    Returns True if Ollama or any external provider is configured.
    """
    if _provider_is_configured("ollama") and not _circuit_is_open("ollama"):
        return True
    return has_external_provider()


def check_provider(provider: str) -> tuple[bool, str]:
    """Check if a provider is reachable. Returns (success, message)."""
    call_fn = _PROVIDERS.get(provider)
    if not call_fn:
        return False, f"Unknown provider: {provider}"

    try:
        result = call_fn("Say 'ok' and nothing else.", system="Respond with exactly 'ok'.")
        if result:
            _circuit_record_success(provider)
            return True, f"{provider} is working"
    except Exception as e:
        return False, f"{provider} error: {e}"
    return False, f"{provider} is not reachable"


def get_fallback_status() -> dict:
    """Return the health status of all providers for diagnostics."""
    providers = {}
    for name in _PROVIDERS:
        state = _circuit_state.get(name, {})
        providers[name] = {
            "configured": _provider_is_configured(name),
            "circuit_open": _circuit_is_open(name),
            "failures": state.get("failures", 0),
        }
    return {"providers": providers}


def reset_circuit_breaker(provider: str = "") -> None:
    """Manually reset circuit breaker for a provider (or all if empty)."""
    if provider:
        if provider in _circuit_state:
            _circuit_state[provider] = {"failures": 0, "last_failure": 0, "open": False}
            logger.info("Circuit breaker manually reset for %s", provider)
    else:
        _circuit_state.clear()
        logger.info("All circuit breakers reset")


def _parse_json_response(raw: str) -> dict | None:
    """Extract JSON from an LLM response."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

    logger.warning("Could not parse LLM response: %s", raw[:200])
    return None
