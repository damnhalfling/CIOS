"""Model router — routes LLM calls to the configured provider.

Supports:
- Ollama (local, free, fast)
- OpenAI (GPT-4o-mini, GPT-4o)
- Anthropic (Claude direct API)
- AWS Bedrock (Claude via AWS)

The provider is configured in ~/.cios/settings.json.
Pattern matching handles 80%+ of intents without any LLM.

Fallback chain: primary → all configured providers → graceful error.
Retry with exponential backoff on transient failures.
Circuit breaker prevents hammering dead providers.
"""

import json
import logging
import time
from typing import Optional

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
    "bedrock": 15,
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
    # Check if enough time has passed to retry
    elapsed = time.time() - state.get("last_failure", 0)
    if elapsed >= _CIRCUIT_BREAKER_RESET_TIME:
        # Half-open: allow one attempt
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
        logger.warning("Circuit breaker OPEN for %s (%d consecutive failures)",
                       provider, state["failures"])


def _circuit_record_success(provider: str) -> None:
    """Record a success — resets the circuit breaker."""
    if provider in _circuit_state:
        _circuit_state[provider] = {"failures": 0, "last_failure": 0, "open": False}


def _is_transient(error: str) -> bool:
    """Check if an error is transient and worth retrying."""
    lower = error.lower()
    return any(t in lower for t in _TRANSIENT_ERRORS)


def _retry_call(fn, prompt: str, system: str, provider_name: str) -> Optional[str]:
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
            # None result = provider not configured or empty response
            return None
        except Exception as e:
            last_error = str(e)
            if attempt < _MAX_RETRIES and _is_transient(last_error):
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                logger.info("Provider %s attempt %d failed (%s), retrying in %.1fs",
                            provider_name, attempt + 1, last_error[:80], wait)
                time.sleep(wait)
            else:
                logger.warning("Provider %s failed after %d attempts: %s",
                               provider_name, attempt + 1, last_error[:120])
                _circuit_record_failure(provider_name)
                return None
    _circuit_record_failure(provider_name)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  PROVIDER IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════

def _call_ollama(prompt: str, system: str = "") -> Optional[str]:
    """Call local Ollama model."""
    import urllib.request
    import urllib.error

    url = config.get("ollama_url")
    model = config.get("ollama_model")
    timeout = _PROVIDER_TIMEOUTS["ollama"]

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 256},
    }).encode()

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


def _call_openai(prompt: str, system: str = "") -> Optional[str]:
    """Call OpenAI API (GPT-4o-mini, GPT-4o, etc.)."""
    import urllib.request
    import urllib.error

    api_key = config.get("openai_api_key")
    if not api_key:
        return None

    model = config.get("openai_model")
    timeout = _PROVIDER_TIMEOUTS["openai"]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 512,
    }).encode()

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


def _call_anthropic(prompt: str, system: str = "") -> Optional[str]:
    """Call Anthropic API directly (not via Bedrock)."""
    import urllib.request
    import urllib.error

    api_key = config.get("anthropic_api_key")
    if not api_key:
        return None

    model = config.get("anthropic_model")
    timeout = _PROVIDER_TIMEOUTS["anthropic"]

    payload = json.dumps({
        "model": model,
        "max_tokens": 512,
        "temperature": 0.1,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

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


def _call_bedrock(prompt: str, system: str = "") -> Optional[str]:
    """Call Amazon Bedrock (Claude via AWS credentials)."""
    import boto3
    from botocore.exceptions import ClientError, ReadTimeoutError, ConnectTimeoutError

    region = config.get("bedrock_region")
    model_id = config.get("bedrock_model_id")
    timeout = _PROVIDER_TIMEOUTS["bedrock"]

    # Use explicit credentials if configured, otherwise boto3 default chain
    aws_key = config.get("aws_access_key_id")
    aws_secret = config.get("aws_secret_access_key")

    boto_config = boto3.session.Config(
        read_timeout=timeout,
        connect_timeout=10,
        retries={"max_attempts": 0},  # we handle retries ourselves
    )

    if aws_key and aws_secret:
        client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            config=boto_config,
        )
    else:
        client = boto3.client("bedrock-runtime", region_name=region, config=boto_config)

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "temperature": 0.1,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    })

    try:
        response = client.invoke_model(
            modelId=model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"].strip() or None
    except (ReadTimeoutError, ConnectTimeoutError):
        raise TimeoutError(f"Bedrock timed out after {timeout}s") from None
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        raise ConnectionError(f"Bedrock error ({code}): {e}") from e


# ═══════════════════════════════════════════════════════════════════════════
#  ROUTER
# ═══════════════════════════════════════════════════════════════════════════

_PROVIDERS = {
    "ollama": _call_ollama,
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "bedrock": _call_bedrock,
}

# System prompt for intent resolution
_SYSTEM = (
    "You are the reasoning engine of CIOS. "
    "Given a user request and optional context (logs, errors, memory), "
    "respond ONLY with a JSON object: "
    '{"intent": "<intent_type>", "params": {}, "plan": ["step1", "step2"]}. '
    "Valid intents: dev_start, process_control, log_analysis, fix_last_error, "
    "command_exec, status, app_launch, session, bluetooth. "
    "Keep plans to 2-5 steps max. Be precise."
)


def _call_provider(prompt: str, system: str = "") -> Optional[str]:
    """Call the configured provider with retry + full fallback chain.

    Chain: primary provider (with retry) → each other configured provider → None.
    Circuit breaker prevents hammering dead providers.
    """
    provider = config.get("llm_provider")
    call_fn = _PROVIDERS.get(provider)

    # 1. Try primary provider with retry (if circuit is closed)
    if call_fn and not _circuit_is_open(provider):
        result = _retry_call(call_fn, prompt, system, provider)
        if result:
            return result
        logger.info("Primary provider '%s' failed, trying fallback chain", provider)
    elif _circuit_is_open(provider):
        logger.info("Primary provider '%s' circuit is open, skipping to fallback", provider)

    # 2. Fallback chain: try all other providers in priority order
    _FALLBACK_ORDER = ["ollama", "openai", "anthropic", "bedrock"]
    for fallback in _FALLBACK_ORDER:
        if fallback == provider:
            continue  # already tried
        if _circuit_is_open(fallback):
            continue  # circuit open, skip
        fallback_fn = _PROVIDERS.get(fallback)
        if not fallback_fn:
            continue
        # Check if provider is configured (has credentials or is ollama)
        if fallback != "ollama" and not _provider_is_configured(fallback):
            continue
        result = _retry_call(fallback_fn, prompt, system, fallback)
        if result:
            logger.info("Fallback provider '%s' succeeded", fallback)
            return result

    # 3. All providers exhausted
    logger.warning("All LLM providers failed for prompt: %s", prompt[:80])
    return None


def _provider_is_configured(provider: str) -> bool:
    """Check if a provider has the necessary credentials configured."""
    if provider == "ollama":
        return _ollama_is_reachable()
    if provider == "openai":
        return bool(config.get("openai_api_key"))
    if provider == "anthropic":
        return bool(config.get("anthropic_api_key"))
    if provider == "bedrock":
        # Bedrock uses AWS credential chain, consider configured if region is set
        return bool(config.get("bedrock_region"))
    return False


# Cache Ollama reachability for 30s to avoid repeated socket checks
_ollama_cache: dict = {"reachable": False, "checked_at": 0.0}


def _ollama_is_reachable() -> bool:
    """Quick check if Ollama is running (cached for 30s)."""
    now = time.time()
    if now - _ollama_cache["checked_at"] < 30:
        return _ollama_cache["reachable"]

    import urllib.request
    import urllib.error
    url = config.get("ollama_url")
    try:
        req = urllib.request.Request(f"{url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1):
            _ollama_cache.update(reachable=True, checked_at=now)
            return True
    except Exception:
        _ollama_cache.update(reachable=False, checked_at=now)
        return False


def route_to_llm(prompt: str, complex: bool = False) -> Optional[dict]:
    """Route a prompt to the LLM and parse the JSON response."""
    raw = _call_provider(prompt, system=_SYSTEM)

    if raw is None:
        return None

    # Extract JSON from response
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


def is_any_provider_available() -> bool:
    """Quick check if any LLM provider is likely available (no network call).

    Returns True if at least one provider is configured and its circuit is closed.
    This avoids waiting 30s for a timeout when no LLM is set up.
    """
    primary = config.get("llm_provider")

    # Check primary first
    if primary and _provider_is_configured(primary) and not _circuit_is_open(primary):
        return True

    # Check fallbacks
    for name in _PROVIDERS:
        if name == primary:
            continue
        if _provider_is_configured(name) and not _circuit_is_open(name):
            return True

    return False


def resolve_unknown_intent(user_input: str, context: str = "") -> Optional[Intent]:
    """Use LLM to resolve an intent that pattern matching couldn't handle."""
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


def check_provider(provider: str) -> tuple[bool, str]:
    """Check if a provider is reachable. Returns (success, message)."""
    call_fn = _PROVIDERS.get(provider)
    if not call_fn:
        return False, f"Unknown provider: {provider}"

    result = call_fn("Say 'ok' and nothing else.", system="Respond with exactly 'ok'.")
    if result:
        _circuit_record_success(provider)
        return True, f"{provider} is working"
    return False, f"{provider} is not reachable"


def get_fallback_status() -> dict:
    """Return the health status of all providers for diagnostics.

    Returns:
        {
            "primary": str,
            "providers": {name: {"configured": bool, "circuit_open": bool, "failures": int}}
        }
    """
    primary = config.get("llm_provider")
    providers = {}
    for name in _PROVIDERS:
        state = _circuit_state.get(name, {})
        providers[name] = {
            "configured": _provider_is_configured(name),
            "circuit_open": _circuit_is_open(name),
            "failures": state.get("failures", 0),
            "is_primary": name == primary,
        }
    return {"primary": primary, "providers": providers}


def reset_circuit_breaker(provider: str = "") -> None:
    """Manually reset circuit breaker for a provider (or all if empty)."""
    if provider:
        if provider in _circuit_state:
            _circuit_state[provider] = {"failures": 0, "last_failure": 0, "open": False}
            logger.info("Circuit breaker manually reset for %s", provider)
    else:
        _circuit_state.clear()
        logger.info("All circuit breakers reset")
