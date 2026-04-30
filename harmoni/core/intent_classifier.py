"""Intent classifier — LLM-based classification with persistent cache.

This is the "smart fallback" for when regex patterns don't match.
Instead of asking the LLM to generate a full plan, we ask it to
classify the input into one of the known IntentTypes + extract params.

Features:
- Lightweight prompt: classification only, no plan generation (~200ms vs ~2s)
- Persistent cache: SQLite-backed, survives restarts
- Similarity matching: "sobe o som" cached → "sobe o volume" hits cache
- Learning: successful classifications are cached for instant reuse
- Temperature 0: deterministic, same input → same output

Flow:
    1. Check cache (exact match) → instant
    2. Check cache (fuzzy match) → instant
    3. Call LLM with classification prompt → ~200-500ms
    4. Cache the result for next time
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
from typing import Optional

from harmoni.core.config import HARMONI_HOME
from harmoni.core.intent_parser import Intent, IntentType

logger = logging.getLogger(__name__)

_DB_PATH = HARMONI_HOME / "intent_cache.db"

# All valid intent types for the classification prompt
_VALID_INTENTS = [t.value for t in IntentType if t != IntentType.UNKNOWN]

# System prompt — focused on classification only, not plan generation
_CLASSIFY_SYSTEM = (
    "You are an intent classifier for Harmoni OS, a voice-controlled Linux desktop.\n"
    "Given a user request in Portuguese or English, respond ONLY with a JSON object:\n"
    '{"intent": "<type>", "params": {}}\n\n'
    "Valid intent types:\n"
    "- dev_start: start/run a development project (params: target)\n"
    "- process_control: kill/check processes on ports (params: action, port)\n"
    "- log_analysis: read/check logs or errors\n"
    "- fix_last_error: fix/retry the last failed command\n"
    "- command_exec: run a shell command (params: command)\n"
    "- status: check running services\n"
    "- file_organize: organize files in a folder (params: target)\n"
    "- system_health: check CPU/memory/disk, diagnose slowness\n"
    "- app_launch: open an application (params: app)\n"
    "- session: shutdown/reboot/suspend/lock/logout (params: action)\n"
    "- network: wifi connect/disconnect/list/status (params: action, ssid)\n"
    "- audio: volume up/down/mute/unmute/set (params: action, level, delta)\n"
    "- disk_analysis: check disk space, clean cache (params: action)\n"
    "- power: battery status, brightness, power saving (params: action)\n"
    "- package: install/remove/search/update packages (params: action, package)\n"
    "- clipboard: clipboard history/current/paste/clear (params: action)\n"
    "- window: list/focus/close/tile windows (params: action, target)\n"
    "- bluetooth: connect/scan/pair/status bluetooth (params: action, device)\n"
    "- self_update: check/install Harmoni updates (params: action)\n"
    "- explore_system: show capabilities, help (no params)\n"
    "- list_apps: list installed applications (no params)\n"
    "- workflow_start: open dev workspace for a project (params: project)\n"
    "- intent_media: watch video/listen to music (params: media_type)\n"
    "- intent_browse: browse the web/search online (no params)\n"
    "- intent_write: write a document/text (params: doc_type)\n"
    "- files_search: find/locate a file (params: query)\n"
    "- files_open: open a specific file (params: query)\n\n"
    "Rules:\n"
    "- Respond ONLY with the JSON object, nothing else\n"
    "- If you cannot classify, use: {\"intent\": \"unknown\", \"params\": {}}\n"
    "- Extract relevant params from the user input\n"
    "- For audio: action can be up/down/mute/unmute/set/status\n"
    "- For network: action can be connect/disconnect/list/status\n"
    "- For session: action can be shutdown/reboot/suspend/hibernate/lock/logout\n"
)


class IntentCache:
    """SQLite-backed cache for LLM intent classifications."""

    def __init__(self) -> None:
        HARMONI_HOME.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS intent_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_normalized TEXT NOT NULL UNIQUE,
                intent TEXT NOT NULL,
                params TEXT NOT NULL DEFAULT '{}',
                confidence REAL NOT NULL DEFAULT 0.8,
                hit_count INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                last_hit REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'llm'
            );
            CREATE INDEX IF NOT EXISTS idx_cache_input ON intent_cache(input_normalized);
            CREATE INDEX IF NOT EXISTS idx_cache_intent ON intent_cache(intent);
        """)

    def get(self, user_input: str) -> Optional[Intent]:
        """Look up a cached classification (exact match on normalized input)."""
        normalized = _normalize(user_input)
        with self._lock:
            row = self._conn.execute(
                "SELECT intent, params, confidence FROM intent_cache WHERE input_normalized = ?",
                (normalized,),
            ).fetchone()
        if row:
            try:
                intent_type = IntentType(row["intent"])
                params = json.loads(row["params"])
                # Update hit count
                self._record_hit(normalized)
                logger.debug("Cache HIT (exact): '%s' → %s", user_input, row["intent"])
                return Intent(
                    type=intent_type,
                    confidence=row["confidence"],
                    params=params,
                    raw_input=user_input,
                )
            except (ValueError, json.JSONDecodeError):
                pass
        return None

    def get_fuzzy(self, user_input: str) -> Optional[Intent]:
        """Look up a cached classification using word-overlap similarity."""
        normalized = _normalize(user_input)
        words = set(normalized.split())
        if not words or len(words) < 2:
            return None

        with self._lock:
            rows = self._conn.execute(
                "SELECT input_normalized, intent, params, confidence FROM intent_cache "
                "WHERE hit_count > 0 ORDER BY hit_count DESC LIMIT 200",
            ).fetchall()

        best_match = None
        best_score = 0.0

        for row in rows:
            cached_words = set(row["input_normalized"].split())
            if not cached_words:
                continue
            # Jaccard similarity
            intersection = words & cached_words
            union = words | cached_words
            score = len(intersection) / len(union) if union else 0.0

            if score > best_score and score >= 0.5:
                best_score = score
                best_match = row

        if best_match:
            try:
                intent_type = IntentType(best_match["intent"])
                params = json.loads(best_match["params"])
                self._record_hit(best_match["input_normalized"])
                logger.debug(
                    "Cache HIT (fuzzy %.2f): '%s' → %s (via '%s')",
                    best_score, user_input, best_match["intent"],
                    best_match["input_normalized"],
                )
                return Intent(
                    type=intent_type,
                    confidence=best_match["confidence"] * best_score,
                    params=params,
                    raw_input=user_input,
                )
            except (ValueError, json.JSONDecodeError):
                pass

        return None

    def store(self, user_input: str, intent: Intent, source: str = "llm") -> None:
        """Cache a classification result."""
        normalized = _normalize(user_input)
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO intent_cache
                   (input_normalized, intent, params, confidence, hit_count, created_at, last_hit, source)
                   VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                   ON CONFLICT(input_normalized) DO UPDATE SET
                   intent = excluded.intent,
                   params = excluded.params,
                   confidence = excluded.confidence,
                   hit_count = hit_count + 1,
                   last_hit = excluded.last_hit""",
                (normalized, intent.type.value, json.dumps(intent.params),
                 intent.confidence, now, now, source),
            )
            self._conn.commit()
        logger.debug("Cache STORE: '%s' → %s (source: %s)", user_input, intent.type.value, source)

    def _record_hit(self, normalized: str) -> None:
        """Increment hit count and update last_hit timestamp."""
        with self._lock:
            self._conn.execute(
                "UPDATE intent_cache SET hit_count = hit_count + 1, last_hit = ? WHERE input_normalized = ?",
                (time.time(), normalized),
            )
            self._conn.commit()

    @property
    def size(self) -> int:
        """Number of cached classifications."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM intent_cache").fetchone()
            return row[0] if row else 0

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  CLASSIFIER
# ═══════════════════════════════════════════════════════════════════════════

# Module-level cache singleton
_cache: Optional[IntentCache] = None


def _get_cache() -> IntentCache:
    """Get or create the cache singleton."""
    global _cache
    if _cache is None:
        _cache = IntentCache()
    return _cache


def classify_intent(user_input: str) -> Optional[Intent]:
    """Classify user input using cache + LLM fallback.

    Flow:
        1. Exact cache match → instant (<1ms)
        2. Fuzzy cache match → instant (<5ms)
        3. LLM classification → ~200-500ms
        4. Cache the result

    Returns None if classification fails entirely.
    """
    cache = _get_cache()

    # 1. Exact cache match
    cached = cache.get(user_input)
    if cached:
        return cached

    # 2. Fuzzy cache match
    fuzzy = cache.get_fuzzy(user_input)
    if fuzzy:
        return fuzzy

    # 3. LLM classification
    intent = _classify_via_llm(user_input)
    if intent and intent.type != IntentType.UNKNOWN:
        # 4. Cache successful classification
        cache.store(user_input, intent, source="llm")
        return intent

    return None


def _classify_via_llm(user_input: str) -> Optional[Intent]:
    """Call LLM with the lightweight classification prompt."""
    from harmoni.core.model_router import _call_provider

    prompt = f'Classify this user request: "{user_input}"'

    try:
        raw = _call_provider(prompt, system=_CLASSIFY_SYSTEM)
    except Exception as e:
        logger.warning("LLM classification failed: %s", e)
        return None

    if not raw:
        return None

    # Parse JSON response
    parsed = _parse_classification(raw)
    if not parsed:
        return None

    intent_str, params = parsed

    try:
        intent_type = IntentType(intent_str)
    except ValueError:
        logger.debug("LLM returned unknown intent type: %s", intent_str)
        return None

    if intent_type == IntentType.UNKNOWN:
        return None

    return Intent(
        type=intent_type,
        confidence=0.75,
        params=params,
        raw_input=user_input,
    )


def _parse_classification(raw: str) -> Optional[tuple[str, dict]]:
    """Parse LLM classification response into (intent_str, params)."""
    # Try direct JSON parse
    try:
        data = json.loads(raw.strip())
        return data.get("intent", "unknown"), data.get("params", {})
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from response
    match = re.search(r"\{[^}]+\}", raw)
    if match:
        try:
            data = json.loads(match.group())
            return data.get("intent", "unknown"), data.get("params", {})
        except json.JSONDecodeError:
            pass

    logger.debug("Could not parse LLM classification: %s", raw[:200])
    return None


def learn_from_success(user_input: str, intent: Intent) -> None:
    """Cache a successful intent execution for future reuse.

    Called by the bridge after a successful command execution.
    This means the regex-matched intent was correct, so we cache it
    to help fuzzy matching for similar future inputs.
    """
    cache = _get_cache()
    cache.store(user_input, intent, source="learned")


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    """Normalize text for cache matching: lowercase, strip accents, stem verbs, collapse spaces."""
    text = text.lower().strip()
    # Remove accents
    _ACCENTS = {
        "á": "a", "à": "a", "ã": "a", "â": "a",
        "é": "e", "ê": "e", "è": "e",
        "í": "i", "ì": "i",
        "ó": "o", "ô": "o", "õ": "o", "ò": "o",
        "ú": "u", "ü": "u", "ù": "u",
        "ç": "c", "ñ": "n",
    }
    for old, new in _ACCENTS.items():
        text = text.replace(old, new)
    # Remove punctuation
    text = re.sub(r"[^\w\s]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Light Portuguese/English stemming — normalize verb conjugations
    # This helps "aumenta" match "aumentar", "abre" match "abrir", etc.
    words = text.split()
    stemmed = []
    for w in words:
        stemmed.append(_light_stem(w))
    return " ".join(stemmed)


def _light_stem(word: str) -> str:
    """Very light stemming: strip common PT/EN verb suffixes.

    Not a full stemmer — just enough to match conjugation variants.
    'aumentar' → 'aument', 'aumenta' → 'aument', 'aumentei' → 'aument'
    'abrir' → 'abr', 'abre' → 'abr', 'abri' → 'abr'
    """
    if len(word) <= 3:
        return word
    # Words that should never be stemmed (proper nouns, tech terms, etc.)
    _NO_STEM = {
        "wifi", "bluetooth", "chrome", "firefox", "spotify", "vlc",
        "terminal", "volume", "desktop", "linux", "harmoni",
        "projeto", "arquivo", "sistema", "computador", "navegador",
    }
    if word in _NO_STEM:
        return word
    # Portuguese verb endings (most common conjugations)
    # Order matters: longer suffixes first
    _PT_SUFFIXES = (
        "ando", "endo", "indo",          # gerund
        "aram", "eram", "iram",           # past plural
        "amos", "emos", "imos",           # present plural
        "ava", "evo", "ivo",              # imperfect
        "ar", "er", "ir",                 # infinitive
        "ou", "ei", "eu", "iu",           # past singular
        "am", "em",                       # present plural
        "as", "es", "is", "os",           # plural / 2nd person
        "a", "e", "i", "o",              # present singular
    )
    for suffix in _PT_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


def get_cache_stats() -> dict:
    """Return cache statistics for diagnostics."""
    cache = _get_cache()
    with cache._lock:
        total = cache._conn.execute("SELECT COUNT(*) FROM intent_cache").fetchone()[0]
        from_llm = cache._conn.execute(
            "SELECT COUNT(*) FROM intent_cache WHERE source = 'llm'"
        ).fetchone()[0]
        from_learned = cache._conn.execute(
            "SELECT COUNT(*) FROM intent_cache WHERE source = 'learned'"
        ).fetchone()[0]
        total_hits = cache._conn.execute(
            "SELECT SUM(hit_count) FROM intent_cache"
        ).fetchone()[0] or 0
    return {
        "total_cached": total,
        "from_llm": from_llm,
        "from_learned": from_learned,
        "total_hits": total_hits,
    }
