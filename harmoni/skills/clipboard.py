"""Skill: Smart Clipboard — smart clipboard with history and actions.

Features:
- Clipboard history (last N items)
- Content-aware actions (detect URLs, code, paths, etc.)
- Quick paste from history
- Clipboard search
- Auto-detect and suggest actions based on content type

Uses xclip/xsel for X11 clipboard access.
"""

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from harmoni.core.config import HARMONI_HOME

logger = logging.getLogger(__name__)

_HISTORY_PATH = HARMONI_HOME / "clipboard_history.json"
_MAX_HISTORY = 50
_MAX_ITEM_SIZE = 10000  # chars


@dataclass
class ClipboardItem:
    content: str
    content_type: str  # "text", "url", "path", "code", "email", "number"
    timestamp: float
    source: str = ""  # app that copied it (if detectable)

    @property
    def preview(self) -> str:
        """Short preview of content."""
        text = self.content.strip().replace("\n", " ")
        return text[:60] + "…" if len(text) > 60 else text


@dataclass
class ClipboardAction:
    """A suggested action based on clipboard content."""
    label: str
    command: str  # internal command to execute
    icon: str


class CognitiveClipboard:
    """Smart clipboard manager with history and content detection."""

    def __init__(self) -> None:
        self._history: list[ClipboardItem] = []
        self._last_content: str = ""
        self._monitoring = False
        self._load_history()

    def _load_history(self) -> None:
        """Load clipboard history from disk."""
        if _HISTORY_PATH.exists():
            try:
                import json
                data = json.loads(_HISTORY_PATH.read_text())
                self._history = [
                    ClipboardItem(**item) for item in data.get("items", [])
                ]
            except Exception as e:
                logger.debug("Could not load clipboard history: %s", e)

    def _save_history(self) -> None:
        """Save clipboard history to disk."""
        try:
            import json
            HARMONI_HOME.mkdir(parents=True, exist_ok=True)
            data = {
                "items": [
                    {
                        "content": item.content,
                        "content_type": item.content_type,
                        "timestamp": item.timestamp,
                        "source": item.source,
                    }
                    for item in self._history[-_MAX_HISTORY:]
                ]
            }
            _HISTORY_PATH.write_text(json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.debug("Could not save clipboard history: %s", e)

    def get_current(self) -> Optional[str]:
        """Get current clipboard content."""
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                return result.stdout
        except FileNotFoundError:
            # Try xsel as fallback
            try:
                result = subprocess.run(
                    ["xsel", "--clipboard", "--output"],
                    capture_output=True, text=True, timeout=3,
                )
                if result.returncode == 0:
                    return result.stdout
            except FileNotFoundError:
                pass
        except Exception:
            pass
        return None

    def set_clipboard(self, content: str) -> bool:
        """Set clipboard content."""
        try:
            proc = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE, timeout=3,
            )
            proc.communicate(input=content.encode("utf-8"), timeout=3)
            return proc.returncode == 0
        except FileNotFoundError:
            try:
                proc = subprocess.Popen(
                    ["xsel", "--clipboard", "--input"],
                    stdin=subprocess.PIPE, timeout=3,
                )
                proc.communicate(input=content.encode("utf-8"), timeout=3)
                return proc.returncode == 0
            except FileNotFoundError:
                pass
        except Exception:
            pass
        return False

    def poll(self) -> Optional[ClipboardItem]:
        """Check for new clipboard content. Returns new item or None."""
        content = self.get_current()
        if not content or content == self._last_content:
            return None
        if len(content) > _MAX_ITEM_SIZE:
            return None

        self._last_content = content
        item = ClipboardItem(
            content=content,
            content_type=detect_content_type(content),
            timestamp=time.time(),
        )
        self._history.append(item)
        # Trim history
        if len(self._history) > _MAX_HISTORY:
            self._history = self._history[-_MAX_HISTORY:]
        self._save_history()
        return item

    def get_history(self, limit: int = 10) -> list[ClipboardItem]:
        """Get recent clipboard history."""
        return list(reversed(self._history[-limit:]))

    def search_history(self, query: str) -> list[ClipboardItem]:
        """Search clipboard history."""
        query_lower = query.lower()
        return [
            item for item in reversed(self._history)
            if query_lower in item.content.lower()
        ][:10]

    def paste_from_history(self, index: int) -> bool:
        """Paste an item from history (0 = most recent)."""
        items = self.get_history()
        if 0 <= index < len(items):
            return self.set_clipboard(items[index].content)
        return False

    def suggest_actions(self, content: Optional[str] = None) -> list[ClipboardAction]:
        """Suggest actions based on clipboard content."""
        if content is None:
            content = self.get_current()
        if not content:
            return []

        content_type = detect_content_type(content)
        actions = []

        if content_type == "url":
            actions.append(ClipboardAction("Open in browser", f"open_url:{content}", "🌐"))
            actions.append(ClipboardAction("Download", f"download:{content}", "📥"))

        elif content_type == "path":
            path = Path(content.strip()).expanduser()
            if path.is_file():
                actions.append(ClipboardAction("Open file", f"open_file:{content}", "📄"))
                actions.append(ClipboardAction("Copy to Downloads", f"copy_file:{content}", "📋"))
            elif path.is_dir():
                actions.append(ClipboardAction("Open folder", f"open_dir:{content}", "📂"))
                actions.append(ClipboardAction("Organize folder", f"organize:{content}", "🗂️"))

        elif content_type == "code":
            actions.append(ClipboardAction("Run command", f"exec:{content}", "▶️"))
            actions.append(ClipboardAction("Save as script", f"save_script:{content}", "💾"))

        elif content_type == "email":
            actions.append(ClipboardAction("Compose email", f"email:{content}", "✉️"))

        # Universal actions
        actions.append(ClipboardAction("Save to notes", f"save_note:{content[:200]}", "📝"))

        return actions

    def clear_history(self) -> None:
        """Clear clipboard history."""
        self._history = []
        self._save_history()

    @property
    def history_count(self) -> int:
        return len(self._history)


def detect_content_type(content: str) -> str:
    """Detect the type of clipboard content."""
    text = content.strip()

    # URL
    if re.match(r'https?://\S+', text):
        return "url"

    # Email
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', text):
        return "email"

    # File path
    if text.startswith("/") or text.startswith("~/") or text.startswith("./"):
        if not " " in text.split("\n")[0]:  # single path, no spaces in first line
            return "path"

    # Code (heuristic: contains common code patterns)
    code_indicators = [
        r'^\s*(def |class |function |const |let |var |import |from |#include)',
        r'[{}\[\]();]',
        r'^\s*(if|for|while|return|try|catch)\s*[\(:]',
        r'^\$\s',  # shell prompt
        r'^(sudo|apt|pip|npm|git|docker|kubectl)\s',
    ]
    lines = text.splitlines()
    code_score = sum(
        1 for line in lines[:10]
        for pattern in code_indicators
        if re.search(pattern, line)
    )
    if code_score >= 2 or (len(lines) == 1 and re.match(r'^(sudo|apt|pip|npm|git)\s', text)):
        return "code"

    # Number
    if re.match(r'^[\d.,]+$', text):
        return "number"

    return "text"
