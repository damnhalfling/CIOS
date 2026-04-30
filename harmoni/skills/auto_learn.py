"""Auto-Learning Engine — detect repetition, save patterns, reuse.

Watches memory for repeated intents and commands. When a pattern is
detected (same intent + similar params executed N times), it saves
a "learned shortcut" that can be triggered faster next time.

Features:
- Detect repeated patterns (same intent, similar params, same outcome)
- Save learned shortcuts to ~/.harmoni/learned.json
- Suggest shortcuts when similar input is detected
- Allow user to name shortcuts ("always do X when I say Y")
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from harmoni.core.config import HARMONI_HOME

logger = logging.getLogger(__name__)

_LEARNED_PATH = HARMONI_HOME / "learned.json"
_MIN_REPETITIONS = 3  # times before suggesting a shortcut
_SIMILARITY_THRESHOLD = 0.7  # how similar inputs must be to count as "same"


@dataclass
class LearnedPattern:
    """A learned shortcut from repeated behavior."""
    id: str
    name: str  # user-friendly name
    trigger_phrases: list[str]  # inputs that trigger this pattern
    intent: str  # IntentType value
    params: dict  # default params
    times_used: int = 0
    created_at: float = 0.0
    last_used: float = 0.0
    auto_confirm: bool = False  # skip confirmation for this pattern


@dataclass
class PatternSuggestion:
    """A suggestion to create a shortcut."""
    intent: str
    params: dict
    example_inputs: list[str]
    count: int
    suggested_name: str


class AutoLearner:
    """Detects patterns and manages learned shortcuts."""

    def __init__(self) -> None:
        self._patterns: list[LearnedPattern] = []
        self._load()

    def _load(self) -> None:
        """Load learned patterns from disk."""
        if _LEARNED_PATH.exists():
            try:
                data = json.loads(_LEARNED_PATH.read_text())
                self._patterns = [
                    LearnedPattern(**p) for p in data.get("patterns", [])
                ]
            except Exception as e:
                logger.warning("Could not load learned patterns: %s", e)
                self._patterns = []

    def _save(self) -> None:
        """Persist learned patterns to disk."""
        try:
            HARMONI_HOME.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "patterns": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "trigger_phrases": p.trigger_phrases,
                        "intent": p.intent,
                        "params": p.params,
                        "times_used": p.times_used,
                        "created_at": p.created_at,
                        "last_used": p.last_used,
                        "auto_confirm": p.auto_confirm,
                    }
                    for p in self._patterns
                ],
            }
            _LEARNED_PATH.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning("Could not save learned patterns: %s", e)

    def find_shortcut(self, user_input: str) -> Optional[LearnedPattern]:
        """Check if user input matches a learned pattern."""
        lower = user_input.lower().strip()
        for pattern in self._patterns:
            for trigger in pattern.trigger_phrases:
                if _similarity(lower, trigger.lower()) >= _SIMILARITY_THRESHOLD:
                    pattern.times_used += 1
                    pattern.last_used = time.time()
                    self._save()
                    return pattern
        return None

    def record_execution(self, user_input: str, intent: str, params: dict, outcome: str) -> None:
        """Record an execution for pattern detection. Called after every successful command."""
        if outcome != "success":
            return  # only learn from successes

        # Check if this matches an existing pattern
        for pattern in self._patterns:
            if pattern.intent == intent and _params_similar(pattern.params, params):
                if user_input.lower().strip() not in [t.lower() for t in pattern.trigger_phrases]:
                    pattern.trigger_phrases.append(user_input.strip())
                    # Keep only last 10 triggers
                    pattern.trigger_phrases = pattern.trigger_phrases[-10:]
                pattern.times_used += 1
                pattern.last_used = time.time()
                self._save()
                return

    def detect_suggestions(self, memory_records: list) -> list[PatternSuggestion]:
        """Analyze memory for repeated patterns that could become shortcuts."""
        # Group by intent + params
        groups: dict[str, list] = {}
        for record in memory_records:
            if record.outcome != "success":
                continue
            key = f"{record.intent}:{json.dumps(record.context, sort_keys=True)}"
            groups.setdefault(key, []).append(record)

        suggestions = []
        for key, records in groups.items():
            if len(records) < _MIN_REPETITIONS:
                continue
            # Check if already learned
            intent = records[0].intent
            params = records[0].context
            already_learned = any(
                p.intent == intent and _params_similar(p.params, params)
                for p in self._patterns
            )
            if already_learned:
                continue

            examples = list(set(r.user_input for r in records))[:5]
            suggested_name = _suggest_name(intent, params)
            suggestions.append(PatternSuggestion(
                intent=intent,
                params=params,
                example_inputs=examples,
                count=len(records),
                suggested_name=suggested_name,
            ))

        return suggestions

    def create_shortcut(
        self,
        name: str,
        trigger_phrases: list[str],
        intent: str,
        params: dict,
        auto_confirm: bool = False,
    ) -> LearnedPattern:
        """Create a new learned shortcut."""
        pattern = LearnedPattern(
            id=f"learned_{int(time.time())}_{len(self._patterns)}",
            name=name,
            trigger_phrases=trigger_phrases,
            intent=intent,
            params=params,
            times_used=0,
            created_at=time.time(),
            last_used=0.0,
            auto_confirm=auto_confirm,
        )
        self._patterns.append(pattern)
        self._save()
        logger.info("Created learned shortcut: %s", name)
        return pattern

    def remove_shortcut(self, pattern_id: str) -> bool:
        """Remove a learned shortcut by ID."""
        before = len(self._patterns)
        self._patterns = [p for p in self._patterns if p.id != pattern_id]
        if len(self._patterns) < before:
            self._save()
            return True
        return False

    def list_shortcuts(self) -> list[LearnedPattern]:
        """Return all learned shortcuts."""
        return list(self._patterns)

    @property
    def count(self) -> int:
        return len(self._patterns)


def _similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity (Jaccard)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 1.0 if a == b else 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def _params_similar(a: dict, b: dict) -> bool:
    """Check if two param dicts are similar enough to be the same pattern."""
    if not a and not b:
        return True
    if set(a.keys()) != set(b.keys()):
        return False
    # All keys must match or be close
    for key in a:
        if a[key] != b[key]:
            # Allow some flexibility for string values
            if isinstance(a[key], str) and isinstance(b[key], str):
                if _similarity(a[key], b[key]) < 0.5:
                    return False
            else:
                return False
    return True


def _suggest_name(intent: str, params: dict) -> str:
    """Generate a suggested name for a pattern."""
    name_map = {
        "app_launch": lambda p: f"Abrir {p.get('app', 'app')}",
        "network": lambda p: f"Wi-Fi {p.get('action', '')}",
        "audio": lambda p: f"Volume {p.get('action', '')}",
        "file_organize": lambda p: f"Organizar {p.get('target', 'arquivos')}",
        "system_health": lambda p: "Verificar sistema",
        "dev_start": lambda p: f"Iniciar {p.get('target', 'projeto')}",
        "session": lambda p: p.get("action", "sessão").capitalize(),
        "disk_analysis": lambda p: "Analisar disco",
        "power": lambda p: f"Energia {p.get('action', '')}",
    }
    fn = name_map.get(intent)
    if fn:
        return fn(params)
    return f"Atalho {intent}"
